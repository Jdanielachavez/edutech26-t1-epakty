"""Idempotent publish using n8n public API. Checks state; never claims mere JSON is live."""
import json
import os
from pathlib import Path
from urllib.parse import urlparse
import httpx
from dotenv import load_dotenv
ROOT=Path(__file__).resolve().parents[1]

def main():
    load_dotenv(ROOT/'.env')
    base=os.environ['N8N_BASE_URL'].rstrip('/')
    api=os.environ['PAKTAI_API_URL'].rstrip('/')
    for u in (base,api):
        parsed=urlparse(u)
        if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password:raise ValueError('Only HTTPS URLs without inline credentials')
    ids={'CONFIGURE_WEBHOOK_CREDENTIAL':os.environ['N8N_WEBHOOK_CREDENTIAL_ID'],
         'CONFIGURE_API_CREDENTIAL':os.environ['N8N_API_CREDENTIAL_ID'],
         'CONFIGURE_AWS_CREDENTIAL':os.environ['N8N_AWS_CREDENTIAL_ID']}
    if not all(ids.values()):raise ValueError('Faltan credenciales n8n')
    with httpx.Client(base_url=base+'/api/v1/',headers={'X-N8N-API-KEY':os.environ['N8N_API_KEY']},timeout=30,follow_redirects=False) as client:
        def call(method,path,body=None):
            r=client.request(method,path,json=body);r.raise_for_status();return r.json()
        all_workflows=[];cursor=None
        while True:
            page=call('GET','workflows?limit=100'+('&cursor='+cursor if cursor else ''))
            all_workflows+=page['data'];cursor=page.get('nextCursor')
            if not cursor:break
        def publish(filename,error_id=None,activate=False):
            w=json.loads((ROOT/'n8n'/filename).read_text())
            for node in w['nodes']:
                for cred in node.get('credentials',{}).values():cred['id']=ids.get(cred['id'],cred['id'])
                # Concrete deployment URL, no n8n Variables paid-plan dependency.
                raw=json.dumps(node['parameters'],ensure_ascii=False)
                raw=raw.replace('$vars.PAKTAI_API_URL',repr(api))
                node['parameters']=json.loads(raw)
            if error_id:w['settings']['errorWorkflow']=error_id
            body={k:w[k] for k in ('name','nodes','connections','settings')}
            matches=[x for x in all_workflows if x['name']==w['name']]
            if len(matches)>1:raise ValueError('Duplicate workflow names; resolve before updating')
            saved=call('PUT','workflows/'+matches[0]['id'],body) if matches else call('POST','workflows',body)
            if activate:call('POST','workflows/'+saved['id']+'/activate')
            current=call('GET','workflows/'+saved['id'])
            if activate and current.get('active') is not True:raise RuntimeError('Workflow not active')
            return current
        error=publish('paktai_error_handler.json')
        # Error Trigger workflows execute as referenced handlers; n8n does not require publishing them Active.
        main_flow=publish('paktai_alerta_temprana.json',error['id'],True)
        report={'main_id':main_flow['id'],'main_active':main_flow['active'],'error_workflow_id':error['id'],
                'error_handler_link_verified':main_flow['settings'].get('errorWorkflow')==error['id'],
                'production_webhook':base+'/webhook/paktai-alerta','execution_verified':False}
        path=ROOT/'outputs/n8n-deployment.json';path.parent.mkdir(exist_ok=True);path.write_text(json.dumps(report,indent=2))
        print(json.dumps(report))
if __name__=='__main__':main()
