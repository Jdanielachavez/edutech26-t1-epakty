"""Configuración por servicio con mínimo privilegio.

Cada proceso solo recibe los secretos que usa (ver env/*.env.example):
- api (BFF): base de datos con el rol de ejecución (RLS), tokens de la API, motor (URL + clave).
- worker: base de datos, motor y firma HMAC hacia n8n.
- n8n: Bedrock, WhatsApp y correo. Ninguno de esos secretos puede estar en la api ni en el worker.
Si un proceso arranca con un secreto que no le corresponde, se niega a arrancar.
"""
import json
import os
from dataclasses import dataclass, field
from urllib.parse import urlparse
from psycopg.conninfo import conninfo_to_dict

ROLES = ('admin', 'dece', 'rectoria', 'tutor', 'worker', 'inspeccion', 'colecturia', 'admisiones', 'n8n_callback',
         'epakti_ceo', 'epakti_mlops', 'epakti_ds', 'epakti_cs')
# Secretos que solo pueden vivir en n8n (o en la migración), nunca en estos procesos.
FORBIDDEN = {
    'api': ('SUPABASE_SERVICE_ROLE_KEY', 'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_SESSION_TOKEN',
            'WHATSAPP_ACCESS_TOKEN', 'WHATSAPP_META_TOKEN', 'SMTP_PASSWORD', 'SMTP_APP_PASSWORD', 'MIGRATION_DATABASE_URL'),
    'worker': ('AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_SESSION_TOKEN', 'WHATSAPP_ACCESS_TOKEN',
               'WHATSAPP_META_TOKEN', 'SMTP_PASSWORD', 'SMTP_APP_PASSWORD', 'MIGRATION_DATABASE_URL'),
}


def forbidden_present(service, environ=None):
    environ = os.environ if environ is None else environ
    return [k for k in FORBIDDEN[service] if environ.get(k)]


def _https_or_local(url, name):
    u = urlparse(url)
    local = u.hostname in ('localhost', '127.0.0.1', '::1')
    if not u.hostname or u.username or u.password or not (u.scheme == 'https' or (u.scheme == 'http' and local)):
        raise ValueError(f'{name} debe ser HTTPS sin credenciales (http solo en localhost)')


@dataclass
class Settings:
    database_url: str = field(default_factory=lambda: os.getenv('DATABASE_URL', ''))
    institution: str = field(default_factory=lambda: os.getenv('PAKTAI_INSTITUTION_ID', 'hackathon-colegio'))
    environment: str = field(default_factory=lambda: os.getenv('ENVIRONMENT', 'staging'))
    tokens: dict = field(default_factory=lambda: json.loads(os.getenv('PAKTAI_AUTH_TOKENS', '{}')))
    engine_base_url: str = field(default_factory=lambda: os.getenv('EPAKTI_ENGINE_BASE_URL', ''))
    engine_api_key: str = field(default_factory=lambda: os.getenv('EPAKTI_ENGINE_API_KEY', ''))
    engine_school_id: str = field(default_factory=lambda: os.getenv('EPAKTI_SCHOOL_ID', ''))
    engine_school_name: str = field(default_factory=lambda: os.getenv('EPAKTI_SCHOOL_NAME', 'UE Piloto Ficticio Cuenca'))
    engine_school_dpa: str = field(default_factory=lambda: os.getenv('EPAKTI_SCHOOL_DPA', '010150'))
    engine_school_regime: str = field(default_factory=lambda: os.getenv('EPAKTI_SCHOOL_REGIME', 'Sierra-Amazonía'))
    engine_cutoff: str = field(default_factory=lambda: os.getenv('EPAKTI_FECHA_CORTE', '2025-10-31'))
    engine_jwt_secret: str = field(default_factory=lambda: os.getenv('EPAKTI_ENGINE_JWT_SECRET', ''))
    engine_timeout_s: float = field(default_factory=lambda: int(os.getenv('WORKER_ENGINE_TIMEOUT_MS', '5000')) / 1000)
    n8n_base_url: str = field(default_factory=lambda: os.getenv('N8N_WEBHOOK_BASE_URL', ''))
    n8n_hmac_secret: str = field(default_factory=lambda: os.getenv('N8N_WEBHOOK_HMAC_SECRET', ''))
    worker_max_attempts: int = field(default_factory=lambda: int(os.getenv('WORKER_MAX_ATTEMPTS', '3')))
    worker_backoff_base_s: float = field(default_factory=lambda: int(os.getenv('WORKER_BACKOFF_BASE_MS', '2000')) / 1000)
    pii_retention_days: int = field(default_factory=lambda: int(os.getenv('PII_RETENTION_DAYS', '365')))
    contact_rate_limit: int = field(default_factory=lambda: int(os.getenv('CONTACT_RATE_LIMIT_PER_MIN', '5')))
    trust_proxy_headers: bool = field(default_factory=lambda: os.getenv('TRUST_PROXY_HEADERS', '') == '1')
    users: dict = field(default_factory=lambda: json.loads(os.getenv('PAKTAI_USERS', '{}')))
    session_secret: str = field(default_factory=lambda: os.getenv('SESSION_SECRET', ''))
    session_ttl_s: int = field(default_factory=lambda: int(os.getenv('SESSION_TTL_MINUTES', '480')) * 60)
    login_rate_limit: int = field(default_factory=lambda: int(os.getenv('LOGIN_RATE_LIMIT_PER_MIN', '8')))
    max_upload_bytes: int = 20 * 1024 * 1024

    def validate(self, service='api'):
        leaked = forbidden_present(service)
        if leaked:
            raise ValueError(f'El servicio {service} no puede tener estos secretos (van en n8n): {", ".join(leaked)}')
        if self.environment not in ('staging', 'production'):
            raise ValueError('ENVIRONMENT debe ser staging o production')
        if self.database_url:
            db = conninfo_to_dict(self.database_url)
            if not db.get('host'):
                raise ValueError('DATABASE_URL necesita host')
            sslmode = db.get('sslmode', '')
            if sslmode not in ('verify-full', 'require', 'verify-ca'):
                raise ValueError('DATABASE_URL necesita sslmode=verify-full (o require para poolers)')
        if service == 'api' and self.tokens:
            if any(len(k) < 32 for k in self.tokens):
                raise ValueError('Configura tokens aleatorios de al menos 32 caracteres')
            for value in self.tokens.values():
                if value.get('role') not in ROLES:
                    raise ValueError('Rol API inválido')
                if value['role'] == 'tutor' and (not value.get('course') or not value.get('parallel')):
                    raise ValueError('Tutor necesita curso y paralelo')
        if service == 'api' and self.users:
            if len(self.session_secret) < 32:
                raise ValueError('SESSION_SECRET necesita al menos 32 caracteres para iniciar sesión con contraseña')
            for name, record in self.users.items():
                if name != name.strip().lower() or not str(record.get('hash', '')).startswith('scrypt$'):
                    raise ValueError(f'Usuario {name!r}: nombre en minúsculas y contraseña con hash scrypt')
                if record.get('role') not in ROLES or record.get('role') in ('worker', 'n8n_callback'):
                    raise ValueError(f'Usuario {name!r}: rol no permitido para contraseña')
                if record['role'] == 'tutor' and (not record.get('course') or not record.get('parallel')):
                    raise ValueError(f'Usuario {name!r}: tutor necesita curso y paralelo')
        if self.engine_jwt_secret and len(self.engine_jwt_secret) < 32:
            raise ValueError('EPAKTI_ENGINE_JWT_SECRET necesita al menos 32 caracteres')
        if self.engine_base_url:
            _https_or_local(self.engine_base_url, 'EPAKTI_ENGINE_BASE_URL')
            if len(self.engine_api_key) < 16:
                raise ValueError('Falta EPAKTI_ENGINE_API_KEY (mínimo 16 caracteres)')
        if self.n8n_base_url:
            _https_or_local(self.n8n_base_url, 'N8N_WEBHOOK_BASE_URL')
            if len(self.n8n_hmac_secret) < 32:
                raise ValueError('Falta N8N_WEBHOOK_HMAC_SECRET (mínimo 32 caracteres)')
        if not 1 <= self.pii_retention_days <= 3650:
            raise ValueError('PII_RETENTION_DAYS fuera de rango (1 a 3650)')
