"""Escribe frontend-v2/config.js desde env/frontend.env (solo valores públicos: ningún secreto va al navegador)."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    env = {}
    path = ROOT / 'env' / 'frontend.env'
    if path.is_file():
        for line in path.read_text(encoding='utf-8').splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                k, v = line.split('=', 1); env[k.strip()] = v.strip().strip('\'"')
    config = {'apiUrl': env.get('EPAKTI_API_URL', ''), 'contactEmail': env.get('EPAKTI_CONTACT_EMAIL', ''),
              'whatsappNumber': re.sub(r'\D', '', env.get('EPAKTI_WHATSAPP_NUMBER', ''))}
    for key, label in (('apiUrl', 'EPAKTI_API_URL'), ('contactEmail', 'EPAKTI_CONTACT_EMAIL'), ('whatsappNumber', 'EPAKTI_WHATSAPP_NUMBER')):
        if not config[key]:
            print(f'AVISO: falta {label} en env/frontend.env; la web mostrará el contacto vacío.')
    (ROOT / 'frontend-v2' / 'config.js').write_text(
        '// Configuración pública generada por scripts/build_frontend_config.py. Sin secretos.\n'
        f'window.EPAKTI_CONFIG = {json.dumps(config, ensure_ascii=False, indent=2)};\n', encoding='utf-8')
    print('frontend-v2/config.js actualizado')


if __name__ == '__main__':
    main()
