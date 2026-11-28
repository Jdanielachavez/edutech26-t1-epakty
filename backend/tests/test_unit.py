"""Current pipeline acceptance tests (replaces obsolete blocked-demo assertions)."""
import csv
import json
import shutil
from pathlib import Path
import pytest
from pydantic import ValidationError
from backend.production.validation import validate_source,DataValidationError
from backend.production.contracts import AgentDraft,enforce_draft
from backend.production.config import Settings
from backend.production.delivery import recipient_for,DeliveryConfigurationError
from backend.reference_model import fit_reference,predict_reference
from scripts.build_dashboard_data import build,ROOT,SOURCE

@pytest.fixture
def source(tmp_path):
    for path in SOURCE.glob('*.csv'):shutil.copy(path,tmp_path/path.name)
    return tmp_path

def edit(path,table,change):
    target=path/(table+'.csv')
    with target.open() as f:reader=csv.DictReader(f);fields=reader.fieldnames;rows=list(reader)
    change(rows)
    with target.open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)

@pytest.mark.parametrize('table,field,value',[('notas','nota',''),('notas','nota','nan'),('notas','nota','11'),('pensiones','valor','-1'),('asistencia','codigo_estudiante','NO-EXISTE')])
def test_invalid_source(source,table,field,value):
    edit(source,table,lambda rows:rows[0].update({field:value}))
    with pytest.raises(DataValidationError):validate_source(source)

def test_duplicate_key(source):
    edit(source,'estudiantes',lambda rows:rows.append(rows[0].copy()))
    with pytest.raises(DataValidationError,match='duplicada'):validate_source(source)

def test_unknown_teacher(source):
    edit(source,'horarios',lambda rows:rows[0].update(docente_codigo='UNKNOWN'))
    with pytest.raises(DataValidationError,match='docente'):validate_source(source)

def test_no_history_and_zero_money(source):
    edit(source,'notas',lambda rows:rows.__setitem__(slice(None),[r for r in rows if r['codigo_estudiante']!='EST-001']))
    edit(source,'asistencia',lambda rows:rows.__setitem__(slice(None),[r for r in rows if r['codigo_estudiante']!='EST-001']))
    edit(source,'pensiones',lambda rows:[r.update(valor='0') for r in rows])
    silver,gold,_=build(source,write_outputs=False)
    row=next(r for r in gold['students'] if r['id']=='EST-001')
    assert row['history_missing'] and row['average'] is None and row['unjustifiedAbsence'] is None
    assert row['debt']==0 and row['financialRisk']==0
    assert 0<=row['risk']<=100

def test_pipeline_and_model_are_honest():
    silver,gold,model=build(write_outputs=False)
    assert len(silver['students'])==len(gold['students'])==240
    assert all('risk' not in r for r in silver['students'])
    assert gold['meta']['dataStatus']=='synthetic_official'
    assert model['status']=='reference_not_trained'
    assert not model['training']['real_outcomes']
    assert all(r['score_bienestar'] is None and r['ausentismo_primera_hora'] is None for r in gold['students'])
    assert any(r['tiene_nee']==1 for r in gold['students'])
    predictions=[predict_reference(model,r)[0] for r in silver['students']]
    assert abs(sum(predictions)/len(predictions)-model['reference']['target_rate'])<1e-10

def test_nee_and_output_contract():
    draft=AgentDraft(mensaje_representante='Acompañamos.',accion_interna_colegio='Refuerzo.',responsable_asignado='DECE',plan_3_pasos=['Uno','Dos','Tres'])
    result=enforce_draft(draft,{'driver_principal':'ACADEMICO','tiene_nee':1})
    assert result['responsable_asignado']=='Docente Tutor'
    assert 'adaptación curricular' in result['accion_interna_colegio']
    assert 'especialista psicopedagógico' in result['accion_interna_colegio']
    assert result['human_review_required'] is True
    with pytest.raises(ValidationError):AgentDraft.model_validate({**draft.model_dump(),'plan_3_pasos':['solo uno']})

def test_staging_cannot_deliver_to_family(monkeypatch):
    monkeypatch.setenv('STAGING_EMAIL','test@example.org');monkeypatch.setenv('STAGING_ALLOWLIST','test@example.org')
    assert recipient_for('email','family@example.org','staging')=='test@example.org'
    monkeypatch.setenv('STAGING_ALLOWLIST','')
    with pytest.raises(DeliveryConfigurationError):recipient_for('email','family@example.org','staging')

def test_reject_insecure_config():
    with pytest.raises(ValueError,match='verify-full'):Settings(database_url='postgresql://localhost/postgres').validate()

def test_workflow_security():
    w=json.loads((ROOT/'n8n/paktai_alerta_temprana.json').read_text())
    nodes={n['name']:n for n in w['nodes']}
    assert nodes['Webhook Gold']['parameters']['authentication']=='headerAuth'
    assert nodes['Procesar uno']['parameters']['batchSize']==1
    assert nodes['Pausa 1.5 segundos']['parameters']['amount']==1.5
    assert nodes['AI Agent · borrador']['parameters']['hasOutputParser']
    assert not w['active'] # Export is not a claim of live deployment.
    assert 'name' not in json.loads(nodes['Validador JSON']['parameters']['inputSchema'])['properties']

def test_invalid_nee_and_wellbeing(source):
    path=source/'estudiantes.csv'
    with path.open() as f:reader=csv.DictReader(f);fields=reader.fieldnames+['tiene_nee'];rows=list(reader)
    for r in rows:r['tiene_nee']='0'
    rows[0]['tiene_nee']='2'
    with path.open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
    with pytest.raises(DataValidationError,match='tiene_nee'):validate_source(source)
    rows[0]['tiene_nee']='1'
    with path.open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
    (source/'bienestar.csv').write_text('codigo_estudiante,fecha_corte,score_bienestar\nEST-001,2025-12-01,6\n')
    with pytest.raises(DataValidationError,match='rango'):validate_source(source)

def test_bedrock_minimization_and_validation():
    from backend.production.bedrock import generate
    class FakeBedrock:
        def converse(self,**kwargs):
            text=kwargs['messages'][0]['content'][0]['text']
            assert 'nombre-secreto' not in text and 'telefono' not in text and 'EST-001' not in text
            assert kwargs['modelId']=='amazon.nova-lite-v1:0'
            payload={'mensaje_representante':'Apoyo','accion_interna_colegio':'Revisar','responsable_asignado':'DECE','plan_3_pasos':['a','b','c']}
            return {'output':{'message':{'content':[{'text':'```json\n'+json.dumps(payload)+'\n```'}]}}}
    result=generate({'id':'EST-001','name':'nombre-secreto','telefono':'0990000000','driver_principal':'ACADEMICO','tiene_nee':1},FakeBedrock())
    assert result['human_review_required'] is True
    assert 'psicopedagógico' in result['accion_interna_colegio']


def test_risk_levels_are_relative_so_alerts_exist():
    """Con la media calibrada a AMIE (~0,8 %) los umbrales fijos 35/65 % nunca se alcanzan."""
    from backend.reference_model import cohort_thresholds
    silver,gold,model=build(write_outputs=False)
    th=model['thresholds']
    assert th['method']=='cohort_percentile' and 0<th['moderate']<th['critical']<1
    counts={}
    for r in gold['students']:counts[r['riskLabel']]=counts.get(r['riskLabel'],0)+1
    n=len(gold['students'])
    assert counts.get('Crítico',0)>=1, 'sin casos críticos no se crea ninguna intervención'
    assert counts.get('Crítico',0)<=round(n*0.06) and counts.get('Moderado',0)>=1
    # El ranking manda: todo Crítico tiene más riesgo que cualquier Moderado o Bajo.
    crit=min(r['risk'] for r in gold['students'] if r['riskLabel']=='Crítico')
    rest=max(r['risk'] for r in gold['students'] if r['riskLabel']!='Crítico')
    assert crit>=rest
    # Cohortes muy pequeñas: los percentiles no son estables, se usa el umbral absoluto.
    assert cohort_thresholds([.1,.2,.3])['method']=='absolute_fallback'
    assert cohort_thresholds([.5]*50)['method']=='absolute_fallback'
