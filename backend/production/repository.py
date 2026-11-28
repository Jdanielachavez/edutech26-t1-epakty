from contextlib import contextmanager
from uuid import uuid4
from psycopg import errors as pg_errors
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

# Datos personales que salen de las tablas analíticas y solo viven en la bóveda con fecha de vencimiento.
PII_COLUMNS = {'estudiantes': ('nombre_ficticio',), 'docentes': ('nombre_ficticio',)}
REDACTED = 'REDACTED_LOPDP'


def _without(row, keys):
    return {k: v for k, v in row.items() if k not in keys}


class Repository:
    def __init__(self, settings):
        self.settings = settings
        if settings.database_url:
            self.pool = ConnectionPool(settings.database_url, min_size=1, max_size=8, open=False,
                                       kwargs={'row_factory': dict_row, 'connect_timeout': 8, 'prepare_threshold': None})
        else:
            self.pool = None

    def open(self):
        if self.pool: self.pool.open(wait=True, timeout=15)
    def close(self):
        if self.pool: self.pool.close()

    @contextmanager
    def transaction(self):
        with self.pool.connection() as c, c.transaction():
            c.execute('SET LOCAL ROLE paktai_service')
            c.execute("SELECT set_config('paktai.institution_id',%s,true)", (self.settings.institution,))
            c.execute("SET LOCAL statement_timeout='15s'")
            yield c

    def health(self):
        # El TLS se consulta ANTES de cambiar de rol: tras SET ROLE paktai_service, pg_stat_ssl oculta la fila
        # de la propia sesión (pertenece al login) y el estado salía siempre como "sin cifrado" (503 permanente).
        with self.pool.connection() as c:
            ssl = c.execute('SELECT ssl,version FROM pg_stat_ssl WHERE pid=pg_backend_pid()').fetchone()
            # Los poolers (Supabase) ocultan esa fila: se le pregunta a la propia conexión (libpq) si usa TLS.
            in_use = bool(ssl and ssl['ssl']) or bool(c.pgconn.ssl_in_use)
            version = (ssl['version'] if ssl and ssl['ssl'] else None) or ('TLS (pooler)' if in_use else None)
        with self.transaction() as c:
            c.execute('SELECT count(*) FROM paktai_edu.gold_estudiantes').fetchone()
        return {'ssl': in_use, 'tls_version': version}

    def audit(self, c, event, details):
        c.execute('INSERT INTO paktai_edu.audit_events(institution_id,event,details) VALUES(%s,%s,%s)',
                  (self.settings.institution, event, Jsonb(details)))

    def enqueue(self, c, key, kind, payload):
        return c.execute('''INSERT INTO paktai_edu.outbox(id,institution_id,event_key,kind,payload)
            VALUES(%s,%s,%s,%s,%s) ON CONFLICT(institution_id,event_key) DO NOTHING RETURNING id''',
                         (uuid4(), self.settings.institution, key, kind, Jsonb(payload))).fetchone()

    # ================= Carga del colegio =================
    def save_pipeline(self, run_id, hashes, tables, silver, gold, model):
        tenant = self.settings.institution
        days = self.settings.pii_retention_days
        # LOPDP: los nombres van a la bóveda; Bronze, Silver y Gold quedan seudonimizados (código EST-xxx).
        vault = [(tenant, r['codigo'], r.get('representante_codigo') or '', r.get('nombre_ficticio'), days)
                 for r in tables['estudiantes']]
        bronze = [(tenant, run_id, t, i, Jsonb(_without(row, PII_COLUMNS.get(t, ()))))
                  for t, rows in tables.items() for i, row in enumerate(rows, 1)]
        silver_rows = [_without(r, ('name',)) for r in silver['students']]
        gold_rows = [_without(r, ('name',)) for r in gold['students']]
        with self.transaction() as c:
            # Serialize a tenant's batch loads so an older batch cannot partially overwrite a newer one.
            c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', (tenant,))
            inserted = c.execute('''INSERT INTO paktai_edu.pipeline_runs(institution_id,run_id,data_mode,model,source_hashes,summary)
                VALUES(%s,%s,'synthetic_official',%s,%s,%s) ON CONFLICT DO NOTHING RETURNING run_id''',
                                 (tenant, run_id, Jsonb(model), Jsonb(hashes), Jsonb(gold['summary']))).fetchone()
            if not inserted:
                return {'run_id': run_id, 'replayed': True, 'students': len(gold_rows)}
            with c.cursor() as cur:
                cur.executemany('''INSERT INTO paktai_edu.student_pii_vault(institution_id,student_pseudonym_id,
                    representative_pseudonym_id,full_name,retention_policy_days,pii_retention_expires_at)
                    VALUES(%s,%s,%s,%s,%s,now()+make_interval(days=>%s))
                    ON CONFLICT(institution_id,student_pseudonym_id) DO UPDATE SET full_name=excluded.full_name,
                    representative_pseudonym_id=excluded.representative_pseudonym_id,
                    pii_retention_expires_at=CASE WHEN student_pii_vault.pii_purged_at IS NULL
                        THEN student_pii_vault.pii_retention_expires_at ELSE excluded.pii_retention_expires_at END,
                    pii_purged_at=NULL''', [(*v, v[-1]) for v in vault])
                cur.executemany('INSERT INTO paktai_edu.bronze_rows VALUES(%s,%s,%s,%s,%s)', bronze)
                cur.executemany('INSERT INTO paktai_edu.silver_estudiantes VALUES(%s,%s,%s,%s)',
                                [(tenant, run_id, r['id'], Jsonb(r)) for r in silver_rows])
                cur.executemany('''INSERT INTO paktai_edu.gold_estudiantes
                    (institution_id,id_estudiante,run_id,nivel_riesgo,grado_curso,paralelo,probabilidad,saldo_mora,payload)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(institution_id,id_estudiante) DO UPDATE SET
                    run_id=excluded.run_id,nivel_riesgo=excluded.nivel_riesgo,grado_curso=excluded.grado_curso,
                    paralelo=excluded.paralelo,probabilidad=excluded.probabilidad,saldo_mora=excluded.saldo_mora,
                    payload=excluded.payload,updated_at=now()''',
                                [(tenant, r['id'], run_id, r['riskLabel'], r['course'], r['parallel'], r['risk'] / 100, r['debt'], Jsonb(r))
                                 for r in gold_rows])
            # Cada estudiante en alerta queda «Identificado» la primera vez que aparece (la fecha no cambia en cargas siguientes).
            c.execute('''INSERT INTO paktai_edu.seguimiento_etapas(institution_id,id_estudiante)
                SELECT institution_id,id_estudiante FROM paktai_edu.gold_estudiantes WHERE institution_id=%s AND run_id=%s AND nivel_riesgo<>'Bajo'
                ON CONFLICT DO NOTHING''', (tenant, run_id))
            critical = []
            for r in gold_rows:
                c.execute('''UPDATE paktai_edu.intervenciones_dece SET probabilidad=%s,updated_at=now()
                   WHERE institution_id=%s AND id_estudiante=%s AND estado_caso IN ('ABIERTA','EN_SEGUIMIENTO')''',
                          (r['risk'] / 100, tenant, r['id']))
                if r['riskLabel'] == 'Crítico':
                    case, new = self._case(c, r)
                    if new: critical.append(self.case_payload(r, case['id']))
            if critical:
                self.enqueue(c, 'batch:' + run_id, 'N8N', {'run_id': run_id, 'estudiantes': critical})
            self.audit(c, 'pipeline_committed', {'run_id': run_id, 'counts': gold['summary']['riskCounts'], 'students': len(gold_rows)})
        return {'run_id': run_id, 'replayed': False, 'students': len(gold_rows), 'critical_queued': len(critical)}

    NAME_SQL = "coalesce(v.full_name,'" + REDACTED + "')"

    def students(self, course=None, parallel=None):
        with self.transaction() as c:
            return [r['payload'] for r in c.execute(f'''SELECT g.payload||jsonb_build_object('name',{self.NAME_SQL}) AS payload
                FROM paktai_edu.gold_estudiantes g LEFT JOIN paktai_edu.student_pii_vault v
                  ON v.institution_id=g.institution_id AND v.student_pseudonym_id=g.id_estudiante
                WHERE g.institution_id=%s AND (%s::text IS NULL OR g.grado_curso=%s)
                AND (%s::text IS NULL OR g.paralelo=%s) ORDER BY g.probabilidad DESC''',
                                                    (self.settings.institution, course, course, parallel, parallel)).fetchall()]

    def student(self, student_id):
        """Expediente seudonimizado (sin nombre): es lo que viaja a n8n y al motor."""
        with self.transaction() as c:
            row = c.execute('SELECT payload FROM paktai_edu.gold_estudiantes WHERE institution_id=%s AND id_estudiante=%s',
                            (self.settings.institution, student_id)).fetchone()
            return row['payload'] if row else None

    def latest_model(self):
        """Modelo (coeficientes, intercepto y umbrales) de la última carga procesada del colegio."""
        with self.transaction() as c:
            row = c.execute('SELECT model FROM paktai_edu.pipeline_runs WHERE institution_id=%s ORDER BY created_at DESC LIMIT 1',
                            (self.settings.institution,)).fetchone()
            return row['model'] if row else None

    def latest_run(self):
        with self.transaction() as c:
            return c.execute('''SELECT run_id,created_at,data_mode,summary,source_hashes FROM paktai_edu.pipeline_runs
                WHERE institution_id=%s ORDER BY created_at DESC LIMIT 1''', (self.settings.institution,)).fetchone()

    def recent_jobs(self, limit=8):
        with self.transaction() as c:
            return c.execute('''SELECT job_id,source,status,attempts,duration_ms,error_message,result,created_at,updated_at
                FROM paktai_edu.ingestion_jobs ORDER BY created_at DESC LIMIT %s''', (limit,)).fetchall()

    def recent_audit(self, limit=25):
        with self.transaction() as c:
            return c.execute('SELECT created_at,event,details FROM paktai_edu.audit_events ORDER BY id DESC LIMIT %s', (limit,)).fetchall()

    def student_ids(self):
        with self.transaction() as c:
            return {r['id_estudiante'] for r in c.execute('SELECT id_estudiante FROM paktai_edu.gold_estudiantes WHERE institution_id=%s',
                                                          (self.settings.institution,)).fetchall()}

    # ================= Casos e intervenciones =================
    def _case(self, c, student):
        candidate = uuid4()
        case = c.execute('''INSERT INTO paktai_edu.intervenciones_dece
            (id,institution_id,id_estudiante,probabilidad,value_risk_usd) VALUES(%s,%s,%s,%s,%s)
            ON CONFLICT(institution_id,id_estudiante) WHERE estado_caso IN ('ABIERTA','EN_SEGUIMIENTO')
            DO UPDATE SET probabilidad=excluded.probabilidad,updated_at=now() RETURNING *''',
                         (candidate, self.settings.institution, student['id'], student['risk'] / 100, student['value_risk_usd'])).fetchone()
        return case, case['id'] == candidate

    @staticmethod
    def case_payload(student, case_id):
        allowed = ('id', 'driver_principal', 'risk', 'causas_pct', 'materia_critica', 'overdueMonths', 'tiene_nee')
        return {**{k: student.get(k) for k in allowed}, 'intervention_id': str(case_id)}

    def intervene(self, student_id):
        student = self.student(student_id)
        if not student: return None
        with self.transaction() as c:
            case, new = self._case(c, student)
            if new:
                self.enqueue(c, 'case:' + str(case['id']), 'N8N', {'estudiantes': [self.case_payload(student, case['id'])]})
            self.audit(c, 'intervention_requested', {'case_id': str(case['id']), 'created': new})
            return {'id': str(case['id']), 'created': new, 'state': case['estado_caso']}

    def complete_draft(self, case_id, agent, lease_token):
        with self.transaction() as c:
            # El borrador solo se acepta mientras la reserva siga vigente.
            case = c.execute('''UPDATE paktai_edu.intervenciones_dece SET agent=%s,updated_at=now()
                WHERE id=%s AND institution_id=%s AND draft_lease=%s AND draft_lease_until>now()
                AND agent IS NULL AND estado_caso IN ('ABIERTA','EN_SEGUIMIENTO') RETURNING id''',
                             (Jsonb(agent), case_id, self.settings.institution, lease_token)).fetchone()
            return bool(case)

    def case(self, case_id):
        with self.transaction() as c:
            return c.execute('''SELECT i.*,EXISTS(SELECT 1 FROM paktai_edu.outbox o WHERE o.institution_id=i.institution_id
                            AND o.event_key='delivery:'||i.id::text) AS entrega_en_cola
                            FROM paktai_edu.intervenciones_dece i WHERE i.id=%s AND i.institution_id=%s''',
                             (case_id, self.settings.institution)).fetchone()

    def list_cases(self):
        """Casos del colegio, del más reciente al más antiguo (para el tablero de intervenciones)."""
        with self.transaction() as c:
            return c.execute(f'''SELECT i.id,i.id_estudiante,{self.NAME_SQL} AS nombre,g.grado_curso AS curso,g.paralelo,
                g.nivel_riesgo,i.estado_caso,i.delivery_state,(i.agent IS NOT NULL) AS tiene_borrador,
                i.probabilidad,i.created_at,i.updated_at,
                EXISTS(SELECT 1 FROM paktai_edu.outbox o WHERE o.institution_id=i.institution_id AND o.event_key='delivery:'||i.id::text) AS entrega_en_cola
                FROM paktai_edu.intervenciones_dece i
                JOIN paktai_edu.gold_estudiantes g ON g.institution_id=i.institution_id AND g.id_estudiante=i.id_estudiante
                LEFT JOIN paktai_edu.student_pii_vault v ON v.institution_id=i.institution_id AND v.student_pseudonym_id=i.id_estudiante
                WHERE i.institution_id=%s ORDER BY i.updated_at DESC LIMIT 500''', (self.settings.institution,)).fetchall()

    def asistencia(self, student_id):
        """Asistencia día por día del estudiante, tal como se cargó en el último archivo de asistencia del colegio."""
        with self.transaction() as c:
            run = c.execute('SELECT run_id FROM paktai_edu.pipeline_runs WHERE institution_id=%s ORDER BY created_at DESC LIMIT 1', (self.settings.institution,)).fetchone()
            if not run: return []
            return c.execute("""SELECT payload->>'fecha' AS fecha, payload->>'estado' AS estado FROM paktai_edu.bronze_rows
                WHERE institution_id=%s AND run_id=%s AND source_table='asistencia' AND payload->>'codigo_estudiante'=%s ORDER BY 1""",
                             (self.settings.institution, run['run_id'], student_id)).fetchall()

    # ================= Tracking por etapas =================
    ETAPAS = ('IDENTIFICADO', 'DOCENTE_AVISADO', 'REUNION_FAMILIA', 'CERRADO')

    def etapas(self):
        with self.transaction() as c:
            fecha = c.execute('SELECT created_at FROM paktai_edu.pipeline_runs WHERE institution_id=%s ORDER BY created_at DESC LIMIT 1', (self.settings.institution,)).fetchone()
            rows = c.execute('SELECT * FROM paktai_edu.seguimiento_etapas WHERE institution_id=%s', (self.settings.institution,)).fetchall()
        return {'fecha_carga': fecha['created_at'] if fecha else None, 'etapas': rows}

    def set_etapa(self, student_id, etapa, docente_nombre, docente_correo, user, back_ok, informe=None):
        """Mueve al estudiante de etapa. Hacia atrás solo si se permite (administración, DECE, Rectoría). Al avisar al docente se encola el correo."""
        new = self.ETAPAS.index(etapa)
        with self.transaction() as c:
            inst = self.settings.institution
            c.execute('INSERT INTO paktai_edu.seguimiento_etapas(institution_id,id_estudiante) VALUES(%s,%s) ON CONFLICT DO NOTHING', (inst, student_id))
            cur = c.execute('SELECT * FROM paktai_edu.seguimiento_etapas WHERE institution_id=%s AND id_estudiante=%s FOR UPDATE', (inst, student_id)).fetchone()
            old = self.ETAPAS.index(cur['etapa'])
            if new < old and not back_ok: return None, 'Solo Administración, DECE o Rectoría pueden devolver una etapa'
            if new == old and etapa != 'DOCENTE_AVISADO': return cur, None
            if etapa == 'DOCENTE_AVISADO' and not (docente_nombre and docente_correo): return None, 'Para avisar al docente escribe su nombre y su correo'
            stamps = {'DOCENTE_AVISADO': 'docente_avisado_at', 'REUNION_FAMILIA': 'reunion_familia_at', 'CERRADO': 'cerrado_at'}
            sets, vals = ['etapa=%s', 'updated_at=now()', 'actualizado_por=%s'], [etapa, user]
            if new > 0: sets.append(stamps[etapa] + '=now()')
            for later in self.ETAPAS[new + 1:]:   # al devolver una etapa se borran las fechas posteriores
                if later in stamps: sets.append(stamps[later] + '=NULL')
            if etapa == 'DOCENTE_AVISADO': sets += ['docente_nombre=%s', 'docente_correo=%s']; vals += [docente_nombre, docente_correo]
            row = c.execute('UPDATE paktai_edu.seguimiento_etapas SET ' + ','.join(sets) + ' WHERE institution_id=%s AND id_estudiante=%s RETURNING *', (*vals, inst, student_id)).fetchone()
            if etapa == 'DOCENTE_AVISADO':
                st = c.execute('SELECT grado_curso,paralelo,payload FROM paktai_edu.gold_estudiantes WHERE institution_id=%s AND id_estudiante=%s', (inst, student_id)).fetchone() or {}
                pay = st.get('payload') or {}
                driver = pay.get('driver_principal') or ''
                self.enqueue(c, f"docente:{student_id}:{row['docente_avisado_at'].timestamp():.0f}", 'AVISO_DOCENTE',
                             {'id_estudiante': student_id, 'curso': st.get('grado_curso'), 'paralelo': st.get('paralelo'), 'prioridad': round((pay.get('risk') or 0)),
                              'foco': 'Seguimiento académico' if 'finan' in driver.lower() or not driver else driver, 'materia': pay.get('materia_critica'),
                              'docente_nombre': docente_nombre, 'recipient': docente_correo, 'enviado_por': user, 'environment': self.settings.environment,
                              **({'informe': informe} if informe else {})})
            self.audit(c, 'etapa_seguimiento', {'estudiante': student_id, 'etapa': etapa, 'por': user})
            return row, None

    # ================= Seguimiento en el tiempo =================
    def add_followup(self, student_id, tipo, nota, user, role):
        with self.transaction() as c:
            row = c.execute('''INSERT INTO paktai_edu.seguimiento(institution_id,id_estudiante,tipo,nota,autor_usuario,autor_rol,retention_expires_at)
                VALUES(%s,%s,%s,%s,%s,%s,now()+make_interval(days=>%s)) RETURNING id,tipo,nota,autor_usuario,autor_rol,created_at''',
                            (self.settings.institution, student_id, tipo, nota, user, role, self.settings.pii_retention_days)).fetchone()
            self.audit(c, 'followup_added', {'estudiante': student_id, 'tipo': tipo, 'por': user, 'rol': role})
            return row

    def timeline(self, student_id):
        """Línea de tiempo del estudiante: notas de acompañamiento, apertura y estado del caso e intervenciones registradas."""
        with self.transaction() as c:
            inst = self.settings.institution
            events = [{'cuando': r['created_at'], 'tipo': r['tipo'], 'texto': r['nota'], 'autor': r['autor_usuario'], 'rol': r['autor_rol'], 'origen': 'nota'}
                      for r in c.execute('SELECT tipo,nota,autor_usuario,autor_rol,created_at FROM paktai_edu.seguimiento WHERE institution_id=%s AND id_estudiante=%s',
                                         (inst, student_id)).fetchall()]
            et = c.execute('SELECT * FROM paktai_edu.seguimiento_etapas WHERE institution_id=%s AND id_estudiante=%s', (inst, student_id)).fetchone()
            if et:
                events.append({'cuando': et['identificado_at'], 'tipo': 'ETAPA', 'texto': 'Etapa: identificado como estudiante a acompañar.', 'origen': 'sistema'})
                if et['docente_avisado_at']: events.append({'cuando': et['docente_avisado_at'], 'tipo': 'ETAPA', 'texto': f"Etapa: se avisó por correo a {et['docente_nombre'] or 'el docente'}.", 'origen': 'sistema'})
                if et['reunion_familia_at']: events.append({'cuando': et['reunion_familia_at'], 'tipo': 'ETAPA', 'texto': 'Etapa: el docente se reunió con la familia.', 'origen': 'sistema'})
                if et['cerrado_at']: events.append({'cuando': et['cerrado_at'], 'tipo': 'ETAPA', 'texto': 'Etapa: seguimiento cerrado.', 'origen': 'sistema'})
            for r in c.execute('SELECT estado_caso,delivery_state,created_at,updated_at,(agent IS NOT NULL) AS borrador FROM paktai_edu.intervenciones_dece WHERE institution_id=%s AND id_estudiante=%s',
                               (inst, student_id)).fetchall():
                events.append({'cuando': r['created_at'], 'tipo': 'CASO_ABIERTO', 'texto': 'Se abrió el caso de acompañamiento.', 'origen': 'sistema'})
                if r['borrador']:
                    events.append({'cuando': r['updated_at'], 'tipo': 'BORRADOR', 'texto': 'La IA preparó un borrador para la familia; una persona debe revisarlo.', 'origen': 'sistema'})
                if r['delivery_state'] == 'ENVIADA':
                    events.append({'cuando': r['updated_at'], 'tipo': 'MENSAJE_ENVIADO', 'texto': 'Se envió a la familia el mensaje aprobado.', 'origen': 'sistema'})
                if r['estado_caso'] != 'ABIERTA':
                    events.append({'cuando': r['updated_at'], 'tipo': 'ESTADO', 'texto': 'Estado del caso: ' + r['estado_caso'].replace('_', ' ').lower() + '.', 'origen': 'sistema'})
            for r in c.execute('SELECT rol_ejecutor,tipo_intervencion,canal,fecha_ejecucion FROM paktai_edu.intervention_outcomes WHERE institution_id=%s AND codigo_estudiante=%s',
                               (inst, student_id)).fetchall():
                events.append({'cuando': r['fecha_ejecucion'], 'tipo': 'INTERVENCION', 'texto': f"Intervención registrada: {r['tipo_intervencion'].replace('_', ' ').lower()} ({r['canal']}).", 'rol': r['rol_ejecutor'], 'origen': 'motor'})
            return sorted(events, key=lambda e: e['cuando'], reverse=True)

    def recent_followups(self, limit=60):
        with self.transaction() as c:
            return c.execute(f'''SELECT s.id,s.id_estudiante,{self.NAME_SQL} AS nombre,g.grado_curso AS curso,g.paralelo,s.tipo,s.nota,s.autor_usuario,s.autor_rol,s.created_at
                FROM paktai_edu.seguimiento s
                LEFT JOIN paktai_edu.gold_estudiantes g ON g.institution_id=s.institution_id AND g.id_estudiante=s.id_estudiante
                LEFT JOIN paktai_edu.student_pii_vault v ON v.institution_id=s.institution_id AND v.student_pseudonym_id=s.id_estudiante
                WHERE s.institution_id=%s ORDER BY s.created_at DESC LIMIT %s''', (self.settings.institution, limit)).fetchall()

    # ================= Análisis de evaluaciones =================
    def create_evaluacion(self, d, user, origen, imagenes=None):
        eid = uuid4()
        with self.transaction() as c:
            c.execute('''INSERT INTO paktai_edu.evaluaciones(id,institution_id,titulo,materia,curso,paralelo,fecha,origen,n_hojas,creado_por,retention_expires_at)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now()+make_interval(days=>%s))''',
                      (eid, self.settings.institution, d['titulo'], d['materia'], d['curso'], d['paralelo'], d.get('fecha') or None, origen,
                       len(imagenes or []), user, self.settings.pii_retention_days))
            if imagenes:   # las fotos viajan a n8n por la cola y se borran del registro apenas se entregan
                self.enqueue(c, f'examen:{eid}', 'EXAMEN', {'evaluacion_id': str(eid), 'curso': d['curso'], 'paralelo': d['paralelo'],
                                                           'materia': d['materia'], 'imagenes': imagenes})
            self.audit(c, 'evaluacion_creada', {'id': str(eid), 'origen': origen, 'por': user, 'hojas': len(imagenes or [])})
        return str(eid)

    def evaluacion(self, eid):
        with self.transaction() as c:
            return c.execute('SELECT * FROM paktai_edu.evaluaciones WHERE id=%s AND institution_id=%s', (eid, self.settings.institution)).fetchone()

    def save_resultados(self, eid, hojas, user):
        with self.transaction() as c:
            ev = c.execute('SELECT estado FROM paktai_edu.evaluaciones WHERE id=%s AND institution_id=%s FOR UPDATE', (eid, self.settings.institution)).fetchone()
            if not ev or ev['estado'] == 'CONFIRMADA': return False
            inst = self.settings.institution
            c.execute('DELETE FROM paktai_edu.evaluacion_resultados WHERE evaluacion_id=%s', (eid,))
            nums = set()
            for i, h in enumerate(hojas, 1):
                for r in h['respuestas']:
                    nums.add(r['pregunta'])
                    c.execute('''INSERT INTO paktai_edu.evaluacion_resultados(institution_id,evaluacion_id,hoja,codigo_estudiante,pregunta,correcta,puntaje,puntaje_max)
                        VALUES(%s,%s,%s,%s,%s,%s,%s,%s)''', (inst, eid, i, h.get('codigo'), r['pregunta'], r.get('correcta'), r.get('puntaje'), r.get('puntaje_max')))
            for n in sorted(nums):
                c.execute('INSERT INTO paktai_edu.evaluacion_preguntas(evaluacion_id,institution_id,numero) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING', (eid, inst, n))
            c.execute("UPDATE paktai_edu.evaluaciones SET estado='POR_REVISAR',n_hojas=%s,error=NULL,updated_at=now() WHERE id=%s", (len(hojas), eid))
            self.audit(c, 'evaluacion_resultados', {'id': str(eid), 'hojas': len(hojas), 'por': user})
            return True

    def evaluacion_error(self, eid, msg):
        with self.transaction() as c:
            c.execute("UPDATE paktai_edu.evaluaciones SET estado='ERROR',error=%s,updated_at=now() WHERE id=%s AND institution_id=%s AND estado='PROCESANDO'",
                      (msg[:300], eid, self.settings.institution))

    def list_evaluaciones(self, course=None, parallel=None):
        with self.transaction() as c:
            rows = c.execute('''SELECT id,titulo,materia,curso,paralelo,fecha,estado,origen,n_hojas,error,creado_por,created_at FROM paktai_edu.evaluaciones
                WHERE institution_id=%s ORDER BY created_at DESC LIMIT 100''', (self.settings.institution,)).fetchall()
        if course:
            from .privacy import norm_course
            rows = [r for r in rows if norm_course(r['curso']) == norm_course(course) and r['paralelo'] == parallel]
        return rows

    def evaluacion_detalle(self, eid):
        """Resultado por pregunta (% de aciertos), agrupado por tema. Una pregunta cuenta como acierto si 'correcta' es verdadera o si el puntaje llega al 60 % del máximo."""
        with self.transaction() as c:
            ev = c.execute('SELECT * FROM paktai_edu.evaluaciones WHERE id=%s AND institution_id=%s', (eid, self.settings.institution)).fetchone()
            if not ev: return None
            preguntas = c.execute('''SELECT p.numero,p.tema,
                count(r.id) FILTER (WHERE r.correcta IS NOT NULL OR r.puntaje IS NOT NULL) AS total,
                count(r.id) FILTER (WHERE coalesce(r.correcta,(r.puntaje_max>0 AND r.puntaje>=r.puntaje_max*0.6))) AS aciertos
                FROM paktai_edu.evaluacion_preguntas p LEFT JOIN paktai_edu.evaluacion_resultados r ON r.evaluacion_id=p.evaluacion_id AND r.pregunta=p.numero
                WHERE p.evaluacion_id=%s GROUP BY p.numero,p.tema ORDER BY p.numero''', (eid,)).fetchall()
        for p in preguntas: p['pct'] = round(100 * p['aciertos'] / p['total'], 1) if p['total'] else None
        temas = {}
        for p in preguntas:
            if p['total']:
                t = temas.setdefault(p['tema'] or 'Sin tema asignado', {'tema': p['tema'] or 'Sin tema asignado', 'total': 0, 'aciertos': 0, 'preguntas': []})
                t['total'] += p['total']; t['aciertos'] += p['aciertos']; t['preguntas'].append(p['numero'])
        resumen = sorted(({**t, 'pct': round(100 * t['aciertos'] / t['total'], 1)} for t in temas.values()), key=lambda t: t['pct'])
        return {'evaluacion': ev, 'preguntas': preguntas, 'temas': resumen}

    def set_temas(self, eid, temas):
        with self.transaction() as c:
            ev = c.execute('SELECT estado FROM paktai_edu.evaluaciones WHERE id=%s AND institution_id=%s', (eid, self.settings.institution)).fetchone()
            if not ev: return False
            for n, t in temas.items():
                c.execute('UPDATE paktai_edu.evaluacion_preguntas SET tema=%s WHERE evaluacion_id=%s AND numero=%s', (t or None, eid, int(n)))
            c.execute('UPDATE paktai_edu.evaluaciones SET updated_at=now() WHERE id=%s', (eid,))
            return True

    def confirm_evaluacion(self, eid, user):
        with self.transaction() as c:
            row = c.execute("UPDATE paktai_edu.evaluaciones SET estado='CONFIRMADA',updated_at=now() WHERE id=%s AND institution_id=%s AND estado='POR_REVISAR' RETURNING id",
                            (eid, self.settings.institution)).fetchone()
            if row: self.audit(c, 'evaluacion_confirmada', {'id': str(eid), 'por': user})
            return bool(row)

    def edit_draft_message(self, case_id, message, role):
        """Corrección humana del mensaje. No se permite una vez aprobado el envío: el texto ya está en la cola."""
        with self.transaction() as c:
            row = c.execute('''UPDATE paktai_edu.intervenciones_dece i
                SET agent=jsonb_set(i.agent,'{mensaje_representante}',to_jsonb(%s::text)),updated_at=now()
                WHERE i.id=%s AND i.institution_id=%s AND i.agent IS NOT NULL
                AND i.delivery_state='PENDIENTE_REVISION_HUMANA' AND i.estado_caso IN ('ABIERTA','EN_SEGUIMIENTO')
                AND NOT EXISTS(SELECT 1 FROM paktai_edu.outbox o WHERE o.institution_id=i.institution_id AND o.event_key='delivery:'||i.id::text)
                RETURNING i.id''', (message, case_id, self.settings.institution)).fetchone()
            if row: self.audit(c, 'draft_edited', {'case_id': str(case_id), 'role': role})
            return bool(row)

    def update_case(self, case_id, state):
        with self.transaction() as c:
            row = c.execute('''UPDATE paktai_edu.intervenciones_dece SET estado_caso=%s,updated_at=now()
                WHERE id=%s AND institution_id=%s AND estado_caso IN ('ABIERTA','EN_SEGUIMIENTO') RETURNING id''',
                            (state, case_id, self.settings.institution)).fetchone()
            if row: self.audit(c, 'case_status', {'id': str(case_id), 'state': state})
            return bool(row)

    def claim_draft(self, case_id):
        lease = uuid4()
        with self.transaction() as c:
            case = c.execute("""UPDATE paktai_edu.intervenciones_dece SET draft_lease=%s,draft_lease_until=now()+interval '5 minutes'
                WHERE id=%s AND institution_id=%s AND agent IS NULL AND estado_caso IN ('ABIERTA','EN_SEGUIMIENTO')
                AND (draft_lease_until IS NULL OR draft_lease_until<now()) RETURNING id_estudiante""",
                             (lease, case_id, self.settings.institution)).fetchone()
            if not case: return {'claimed': False}
            student = c.execute('SELECT payload FROM paktai_edu.gold_estudiantes WHERE id_estudiante=%s', (case['id_estudiante'],)).fetchone()
        return {'claimed': True, 'lease_token': str(lease), **self.case_payload(student['payload'], case_id)}

    def log_outcome(self, o, role):
        with self.transaction() as c:
            row = c.execute('''INSERT INTO paktai_edu.intervention_outcomes(institution_id,codigo_estudiante,rol_ejecutor,
                tipo_intervencion,canal,aplicada,fecha_ejecucion,compromiso) VALUES(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id''',
                            (self.settings.institution, o.codigo_estudiante, o.rol_ejecutor, o.tipo_intervencion, o.canal_n8n,
                             bool(o.intervencion_aplicada), o.fecha_ejecucion, o.compromiso_representante)).fetchone()
            moved = c.execute('''UPDATE paktai_edu.intervenciones_dece SET estado_caso='EN_SEGUIMIENTO',updated_at=now()
                WHERE institution_id=%s AND id_estudiante=%s AND estado_caso='ABIERTA' AND %s RETURNING id''',
                              (self.settings.institution, o.codigo_estudiante, bool(o.intervencion_aplicada))).fetchone()
            # Retroalimentación al motor (candado MLOps), asíncrona y solo con el seudónimo.
            self.enqueue(c, f"outcome:{row['id']}", 'ENGINE_OUTCOME', {**o.model_dump(mode='json'), 'compromiso_representante': None})
            self.audit(c, 'intervention_outcome', {'id': row['id'], 'estudiante': o.codigo_estudiante, 'tipo': o.tipo_intervencion, 'role': role})
            return {'registrado': True, 'id': row['id'], 'caso_en_seguimiento': bool(moved)}

    # ================= Ingesta asíncrona (EP-02 / EP-02B) =================
    def create_job(self, key, source, tables, hashes):
        with self.transaction() as c:
            row = c.execute('''INSERT INTO paktai_edu.ingestion_jobs(job_id,institution_id,idempotency_key,source,status,payload,hashes,max_attempts)
                VALUES(%s,%s,%s,%s,'QUEUED',%s,%s,%s) ON CONFLICT(institution_id,idempotency_key) DO NOTHING RETURNING job_id''',
                            ('JOB-' + uuid4().hex[:12].upper(), self.settings.institution, key, source, Jsonb(tables), Jsonb(hashes),
                             self.settings.worker_max_attempts)).fetchone()
            if row:
                self.audit(c, 'ingestion_queued', {'job_id': row['job_id'], 'source': source})
                return row['job_id'], True
            return c.execute('SELECT job_id FROM paktai_edu.ingestion_jobs WHERE idempotency_key=%s', (key,)).fetchone()['job_id'], False

    def job(self, job_id):
        with self.transaction() as c:
            return c.execute('''SELECT job_id,source,status,attempts,max_attempts,next_retry_at,duration_ms,error_message,result,
                created_at,updated_at FROM paktai_edu.ingestion_jobs WHERE job_id=%s''', (job_id,)).fetchone()

    def claim_job(self):
        with self.transaction() as c:
            return c.execute('''UPDATE paktai_edu.ingestion_jobs SET status='PROCESSING',attempts=attempts+1,updated_at=now()
                WHERE job_id=(SELECT job_id FROM paktai_edu.ingestion_jobs
                  WHERE status='QUEUED' OR (status='FAILED_RETRYABLE' AND next_retry_at<=now())
                     OR (status='PROCESSING' AND updated_at<now()-interval '10 minutes')
                  ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING *''').fetchone()

    def finish_job(self, job_id, status, *, result=None, error=None, retry_in_s=None, duration_ms=None):
        with self.transaction() as c:
            # Al completar, se borran los datos crudos del trabajo (minimización); quedan en Bronze, ya seudonimizados.
            c.execute('''UPDATE paktai_edu.ingestion_jobs SET status=%s,result=%s,error_message=%s,duration_ms=%s,updated_at=now(),
                next_retry_at=CASE WHEN %s::float IS NULL THEN NULL ELSE now()+make_interval(secs=>%s::float) END,
                payload=CASE WHEN %s='COMPLETED' THEN NULL ELSE payload END WHERE job_id=%s''',
                      (status, Jsonb(result) if result is not None else None, error, duration_ms, retry_in_s, retry_in_s, status, job_id))
            self.audit(c, 'ingestion_' + status.lower(), {'job_id': job_id, 'error': error})

    def retry_job(self, job_id, role):
        with self.transaction() as c:
            row = c.execute('''UPDATE paktai_edu.ingestion_jobs SET status='QUEUED',attempts=0,next_retry_at=NULL,error_message=NULL,
                updated_at=now() WHERE job_id=%s AND status IN ('DEAD_LETTER','FAILED_RETRYABLE') AND payload IS NOT NULL
                RETURNING job_id''', (job_id,)).fetchone()
            if row: self.audit(c, 'ingestion_retry', {'job_id': job_id, 'role': role})
            return bool(row)

    # ================= Usuarios con contraseña =================
    USER_COLS = 'username,role,display_name,course,parallel,active,must_change_password,created_by,created_at,last_login_at'

    def get_user(self, username):
        try:
            with self.transaction() as c:
                return c.execute('SELECT username,password_hash,role,display_name,course,parallel,active,must_change_password '
                                 'FROM paktai_edu.app_users WHERE institution_id=%s AND username=%s',
                                 (self.settings.institution, username)).fetchone()
        except pg_errors.UndefinedTable:   # base sin migrar: solo existen los usuarios del servidor
            return None

    def list_users(self):
        try:
            with self.transaction() as c:
                return c.execute(f'SELECT {self.USER_COLS} FROM paktai_edu.app_users WHERE institution_id=%s ORDER BY created_at',
                                 (self.settings.institution,)).fetchall()
        except pg_errors.UndefinedTable:
            return []

    def create_user(self, username, password_hash, role, name, course, parallel, created_by, must_change=True):
        with self.transaction() as c:
            row = c.execute('''INSERT INTO paktai_edu.app_users(institution_id,username,password_hash,role,display_name,course,parallel,
                created_by,must_change_password) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING username''',
                            (self.settings.institution, username, password_hash, role, name, course, parallel, created_by, must_change)).fetchone()
            if row: self.audit(c, 'user_created', {'usuario': username, 'rol': role, 'por': created_by})
            return bool(row)

    def update_user(self, username, *, active=None, password_hash=None, must_change=None, by=None):
        with self.transaction() as c:
            row = c.execute('''UPDATE paktai_edu.app_users SET active=coalesce(%s,active),password_hash=coalesce(%s,password_hash),
                must_change_password=coalesce(%s,must_change_password),updated_at=now()
                WHERE institution_id=%s AND username=%s RETURNING username''',
                            (active, password_hash, must_change, self.settings.institution, username)).fetchone()
            if row: self.audit(c, 'user_updated', {'usuario': username, 'activo': active, 'clave_cambiada': password_hash is not None, 'por': by})
            return bool(row)

    def delete_user(self, username, *, by=None):
        """None si la base aún no da permiso de borrar (falta sql/08_eliminar_usuarios.sql)."""
        try:
            with self.transaction() as c:
                row = c.execute('DELETE FROM paktai_edu.app_users WHERE institution_id=%s AND username=%s RETURNING username',
                                (self.settings.institution, username)).fetchone()
                if row: self.audit(c, 'user_deleted', {'usuario': username, 'por': by})
                return bool(row)
        except pg_errors.InsufficientPrivilege:
            return None

    def touch_login(self, username):
        try:
            with self.transaction() as c:
                c.execute('UPDATE paktai_edu.app_users SET last_login_at=now() WHERE institution_id=%s AND username=%s',
                          (self.settings.institution, username))
        except pg_errors.UndefinedTable:
            pass

    def user_active(self, username):
        """True/False si el usuario está en la base; None si no está (usuario definido solo en el servidor)."""
        try:
            with self.transaction() as c:
                row = c.execute('SELECT active FROM paktai_edu.app_users WHERE institution_id=%s AND username=%s',
                                (self.settings.institution, username)).fetchone()
                return None if row is None else row['active']
        except pg_errors.UndefinedTable:
            return None

    # ================= LOPDP: retención y contacto =================
    def purge_expired_pii(self):
        with self.transaction() as c:
            return c.execute('SELECT paktai_edu.epakti_purge_expired_pii() n').fetchone()['n']

    def contact_lead(self, lead):
        with self.transaction() as c:
            row = c.execute('''INSERT INTO paktai_edu.public_contact_leads(nombre_contacto,institucion,ciudad,correo,whatsapp_e164,
                n_estudiantes_aprox,erp_actual,mensaje,retention_expires_at)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,now()+make_interval(days=>%s)) RETURNING id''',
                            (lead.nombre_contacto, lead.institucion, lead.ciudad, lead.correo, lead.whatsapp_e164,
                             lead.n_estudiantes_aprox, lead.erp_actual, lead.mensaje, self.settings.pii_retention_days)).fetchone()
            self.enqueue(c, f"lead:{row['id']}", 'LEAD', {'lead_id': str(row['id']), **lead.model_dump(exclude={'sitio_web'})})
            self.audit(c, 'contact_lead', {'lead_id': str(row['id'])})
            return str(row['id'])

    def retry_outbox(self, event_id, role):
        with self.transaction() as c:
            row = c.execute('''UPDATE paktai_edu.outbox SET state='PENDING',attempts=0,available_at=now()
                WHERE id=%s AND state='FAILED' RETURNING id''', (event_id,)).fetchone()
            if row: self.audit(c, 'outbox_retry', {'event_id': str(event_id), 'role': role})
            return bool(row)

    # ================= Observabilidad del backend (se suma a la del motor en EP-18) =================
    def outbox_stats(self):
        with self.transaction() as c:
            return {'por_tipo_y_estado': c.execute('SELECT kind,state,count(*) n FROM paktai_edu.outbox GROUP BY 1,2 ORDER BY 1,2').fetchall(),
                    'ultimos_intentos': c.execute('''SELECT created_at,details FROM paktai_edu.audit_events WHERE event='outbox_attempt'
                        ORDER BY id DESC LIMIT 20''').fetchall(),
                    'requieren_revision': c.execute('''SELECT id,kind,state,attempts,last_status,created_at FROM paktai_edu.outbox
                        WHERE state='FAILED' ORDER BY created_at DESC LIMIT 20''').fetchall(),
                    'trabajos_ingesta': c.execute('SELECT status,count(*) n FROM paktai_edu.ingestion_jobs GROUP BY 1').fetchall()}
