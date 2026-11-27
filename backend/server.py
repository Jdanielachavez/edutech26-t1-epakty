"""Canonical server entrypoint; the JSON-file MVP server has been retired."""
import argparse
from dotenv import load_dotenv
import uvicorn

def main():
    load_dotenv()
    parser=argparse.ArgumentParser()
    parser.add_argument('--host',default='127.0.0.1')
    parser.add_argument('--port',type=int,default=8000)
    args=parser.parse_args()
    uvicorn.run('backend.production.api:app',host=args.host,port=args.port,access_log=False)
if __name__=='__main__':main()
