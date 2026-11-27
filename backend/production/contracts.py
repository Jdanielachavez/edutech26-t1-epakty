from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

class AgentDraft(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    mensaje_representante: str=Field(min_length=1,max_length=3000)
    accion_interna_colegio: str=Field(min_length=1,max_length=4000)
    responsable_asignado: Literal['Colecturía','Docente Tutor','DECE']
    plan_3_pasos: list[str]=Field(min_length=3,max_length=3)
    @field_validator('plan_3_pasos')
    @classmethod
    def steps(cls,steps):
        if any(not x.strip() or len(x)>1000 for x in steps):raise ValueError('Plan requiere tres pasos no vacíos')
        return [x.strip() for x in steps]

class LoginRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')   # sin recortar espacios: la contraseña se usa tal cual
    usuario: str=Field(min_length=2,max_length=60)
    clave: str=Field(min_length=1,max_length=200)

ASSIGNABLE_ROLES=('admin','rectoria','dece','tutor','inspeccion','colecturia','admisiones')

class UserCreate(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    usuario: str=Field(pattern=r'^[a-z0-9._-]{3,40}$')
    nombre: str=Field(min_length=2,max_length=120)
    rol: Literal['admin','rectoria','dece','tutor','inspeccion','colecturia','admisiones']
    curso: str|None=Field(default=None,max_length=40)
    paralelo: str|None=Field(default=None,max_length=4)
    clave: str|None=Field(default=None,min_length=10,max_length=200)   # si se omite, se genera una temporal

class UserPatch(BaseModel):
    model_config=ConfigDict(extra='forbid')
    activo: bool|None=None
    restablecer_clave: Literal[True]|None=None

class ChangePassword(BaseModel):
    model_config=ConfigDict(extra='forbid')
    clave_actual: str=Field(min_length=1,max_length=200)
    clave_nueva: str=Field(min_length=10,max_length=200)

class SimulationRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    acciones: list[Literal['tutoria_academica','seguimiento_asistencia','apoyo_socioemocional','convenio_pago']]=Field(min_length=1,max_length=4)

class StateUpdate(BaseModel):
    model_config=ConfigDict(extra='forbid')
    estado_caso: Literal['EN_SEGUIMIENTO','RETENIDO','RETIRO']

class DraftEdit(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    mensaje_representante: str=Field(min_length=1,max_length=3000)

class DispatchRequest(BaseModel):
    """EP-10: una persona aprueba enviar las alertas priorizadas del motor al flujo n8n."""
    model_config=ConfigDict(extra='forbid')
    cupo: int=Field(default=40,ge=1,le=40)
    approved: Literal[True]
    dry_run: bool=False   # simulacro: el motor calcula qué enviaría, sin disparar el webhook

class OutcomeLog(BaseModel):
    """EP-11: registro de la intervención aplicada (retorno desde n8n o desde la interfaz)."""
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    school_id: str|None=Field(default=None,max_length=60)
    codigo_estudiante: str=Field(pattern=r'^EST-[0-9]{1,6}$')
    rol_ejecutor: Literal['DOCENTE_TUTOR','DECE','INSPECCION','COLECTURIA','RECTORADO']
    tipo_intervencion: Literal['PLAN_ASISTENCIA','TUTORIA_Y_ADAPTACION_NEE','CONVENIO_PAGO','PAQUETE_INTEGRAL_360','OTRA']
    canal_n8n: str=Field(min_length=1,max_length=80)
    intervencion_aplicada: Literal[0,1]
    fecha_ejecucion: datetime
    compromiso_representante: str|None=Field(default=None,max_length=1000)

class Onboard(BaseModel):
    """EP-01: alta de una unidad educativa."""
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    codigo_amie: str=Field(pattern=r'^[0-9]{2}[A-Z][0-9]{5}$')
    nombre_institucion: str=Field(min_length=3,max_length=200)
    dpa_parroquia_plantel: str=Field(pattern=r'^[0-9]{6}$')
    regimen: Literal['Sierra-Amazonía','Costa-Galápagos']
    sostenimiento: Literal['Fiscal','Fiscomisional','Particular','Municipal']
    sistema_origen_erp: str=Field(min_length=1,max_length=80)

class BatchSync(BaseModel):
    """EP-02: los seis cuadros del colegio en JSON (lo que enviaría un ERP o n8n)."""
    model_config=ConfigDict(extra='forbid')
    synthetic_declaration: Literal[True]
    tablas: dict[Literal['estudiantes','docentes','asistencia','notas','pensiones','horarios'],list[dict[str,str|int|float|None]]]

class ContactLead(BaseModel):
    """EP-19: formulario público de contacto comercial."""
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    nombre_contacto: str=Field(min_length=2,max_length=120)
    institucion: str=Field(min_length=2,max_length=200)
    correo: str=Field(max_length=254,pattern=r'^[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+$')
    whatsapp_e164: str|None=Field(default=None,pattern=r'^\+?[1-9][0-9]{7,14}$')
    ciudad: str|None=Field(default=None,max_length=80)
    n_estudiantes_aprox: int|None=Field(default=None,ge=1,le=100000)
    erp_actual: str|None=Field(default=None,max_length=80)
    mensaje: str|None=Field(default=None,max_length=2000)
    sitio_web: str|None=Field(default=None,max_length=200)   # trampa para bots: una persona nunca lo llena

class DeliveryRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    channel: Literal['email','whatsapp']
    recipient: str=Field(min_length=3,max_length=254)
    approved: Literal[True]

class WorkflowError(BaseModel):
    model_config=ConfigDict(extra='forbid')
    execution_id: str=Field(max_length=100)
    workflow_id: str=Field(max_length=100)
    node: str=Field(max_length=120)
    code: str=Field(max_length=80,pattern=r'^[A-Za-z0-9_.-]+$')

def enforce_draft(draft: AgentDraft, student: dict):
    value=draft.model_dump()
    value['responsable_asignado']={'FINANCIERO':'Colecturía','ACADEMICO':'Docente Tutor','SOCIOEMOCIONAL_CONDUCTUAL':'DECE'}[student['driver_principal']]
    if student.get('tiene_nee')==1:
        value['accion_interna_colegio']+=' Aplicar adaptación curricular definida por la institución y notificar al especialista psicopedagógico del DECE.'
    value['human_review_required']=True
    return value

from uuid import UUID
class DraftCallback(BaseModel):
    model_config=ConfigDict(extra='forbid')
    lease_token: UUID
    draft: AgentDraft


class SeguimientoCreate(BaseModel):
    """Nota de acompañamiento sobre un estudiante. Solo se agrega: queda quién la escribió y cuándo."""
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    tipo: Literal['NOTA','LLAMADA','REUNION','TUTORIA','ACOMPANAMIENTO']='NOTA'
    nota: str=Field(min_length=3,max_length=1000)


class RespuestaHoja(BaseModel):
    model_config=ConfigDict(extra='forbid')
    pregunta: int=Field(ge=1,le=300)
    correcta: bool|None=None
    puntaje: float|None=Field(default=None,ge=0,le=1000)
    puntaje_max: float|None=Field(default=None,gt=0,le=1000)

class HojaExamen(BaseModel):
    model_config=ConfigDict(extra='forbid')
    codigo: str|None=Field(default=None,pattern=r'^[A-Za-z0-9-]{1,24}$')   # solo el código del estudiante, nunca su nombre
    respuestas: list[RespuestaHoja]=Field(min_length=1,max_length=300)

class ResultadoExamen(BaseModel):
    """Lo que devuelve el lector de exámenes (n8n + Amazon Nova Lite) o lo que se carga por CSV. Una persona lo revisa antes de confirmarlo."""
    model_config=ConfigDict(extra='forbid')
    hojas: list[HojaExamen]=Field(default_factory=list,max_length=60)
    error: str|None=Field(default=None,max_length=300)

class TemasExamen(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    temas: dict[str,str]=Field(max_length=300)


class EtapaUpdate(BaseModel):
    """Mueve a un estudiante entre las etapas del seguimiento. Para avisar al docente se pide su nombre y correo."""
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    etapa: Literal['IDENTIFICADO','DOCENTE_AVISADO','REUNION_FAMILIA','CERRADO']
    docente_nombre: str|None=Field(default=None,min_length=2,max_length=120)
    docente_correo: str|None=Field(default=None,max_length=254,pattern=r'^[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+$')
