"""Destino de los mensajes aprobados. El envío real (correo y WhatsApp) lo hace n8n: este proceso no tiene esas credenciales."""
import os
import re
import ssl
import httpx

class DeliveryConfigurationError(ValueError): pass

def recipient_for(channel, recipient, environment):
    if channel=='email':
        valid=bool(re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+',recipient))
    else:
        valid=bool(re.fullmatch(r'\+[1-9][0-9]{7,14}',recipient))
    if not valid:raise DeliveryConfigurationError('Destinatario inválido')
    if environment=='staging':
        target=os.getenv('STAGING_EMAIL' if channel=='email' else 'STAGING_PHONE','').strip()
        allowed={s.strip() for s in os.getenv('STAGING_ALLOWLIST','').split(',') if s.strip()}
        if not target or target not in allowed:raise DeliveryConfigurationError('Configura destino staging y lista blanca')
        return target
    return recipient

def tls_client():
    context=ssl.create_default_context();context.minimum_version=ssl.TLSVersion.TLSv1_3
    return httpx.Client(verify=context,timeout=30,follow_redirects=False)
