"""Machine-readable readiness evidence. Missing credentials are pending, never PASS."""
import json
import os
from pathlib import Path
from dotenv import load_dotenv
from backend.production.config import Settings
from backend.production.repository import Repository
ROOT=Path(__file__).resolve().parents[1]
def main():
    load_dotenv(ROOT/'.env');report={}
    config=Settings()
    try:config.validate();report['configuration']='PASS'
    except Exception:report['configuration']='PENDING: configure .env and verified PostgreSQL TLS'
    if report['configuration']=='PASS':
        repo=Repository(config)
        try:
            repo.open();report['database']=repo.health()
            report['database']['status']='PASS' if report['database']['ssl'] else 'FAIL'
        except Exception:report['database']={'status':'PENDING: unable to connect with supplied configuration'}
        finally:repo.close()
    else:report['database']={'status':'PENDING'}
    for name,keys in {
        # Variables que sí consume la arquitectura actual. La instancia de n8n
        # conserva las credenciales de AWS, correo y WhatsApp; este chequeo solo
        # evidencia que fueron configuradas, no que una entrega haya funcionado.
        'n8n':['N8N_WEBHOOK_BASE_URL','N8N_WEBHOOK_HMAC_SECRET'],
        'bedrock':['AWS_REGION','AWS_BEDROCK_MODEL_ID','AWS_ACCESS_KEY_ID','AWS_SECRET_ACCESS_KEY'],
        'smtp':['SMTP_HOST','SMTP_PORT','SMTP_USER','SMTP_PASSWORD'],
        'whatsapp':['WHATSAPP_PHONE_NUMBER_ID','WHATSAPP_ACCESS_TOKEN'],
        'staging':['STAGING_ALLOWLIST','STAGING_EMAIL']}.items():
        missing=[k for k in keys if not os.getenv(k)]
        report[name]={'status':'PENDING' if missing else 'CONFIGURED_NOT_VERIFIED','missing':missing}
    # No lanzamos una petición sin firmar contra un webhook de producción: podría
    # activar un workflow. La autenticación se confirma en la prueba controlada
    # de n8n con una firma HMAC válida y un payload sintético.
    report['webhook_auth'] = ('CONFIGURED_NOT_VERIFIED'
                              if os.getenv('N8N_WEBHOOK_BASE_URL') and os.getenv('N8N_WEBHOOK_HMAC_SECRET')
                              else 'PENDING')
    report['aws_iam']='PENDING: inspect effective permissions and successful invocation'
    report['aws_budget']='PENDING: create stack with actual budget and administrator email'
    report['spf_dkim']='PENDING: verify domain DNS and provider status'
    report['backup_restore']='PENDING: daily schedule and restore drill on managed service'
    report['predictive_model']='REFERENCE_IMPLEMENTED_NOT_TRAINED_ON_WITHDRAWALS'
    target=ROOT/'outputs/readiness.json';target.parent.mkdir(exist_ok=True);target.write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
