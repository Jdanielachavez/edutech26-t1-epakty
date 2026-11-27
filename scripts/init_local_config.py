"""Create an uncommitted configuration without displaying its generated tokens."""
import json
import secrets
import os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=ROOT/'.env'
if p.exists():raise SystemExit('.env already exists; not overwritten')
s=(ROOT/'.env.example').read_text()
tokens={secrets.token_urlsafe(36):{'role':'admin'},secrets.token_urlsafe(36):{'role':'worker'}}
s=s.replace('PAKTAI_AUTH_TOKENS={}',"PAKTAI_AUTH_TOKENS='"+json.dumps(tokens)+"'")
s=s.replace('WEBHOOK_N8N_TOKEN=\n','WEBHOOK_N8N_TOKEN='+secrets.token_urlsafe(36)+'\n')
fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(fd,'w') as f:f.write(s)
print('Local .env created with private permissions; service addresses and credentials still required.')
