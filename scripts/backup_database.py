"""External daily scheduler entry point. Encrypt dump using AWS KMS on S3."""
import os
import subprocess
import tempfile
from datetime import datetime,timezone
from pathlib import Path
import boto3
from dotenv import load_dotenv

def main():
    load_dotenv()
    # Keep password out of process arguments. PG* env can be supplied by server secret store.
    required=('PGHOST','PGUSER','PGDATABASE','PGPASSWORD','PGSSLROOTCERT','BACKUP_BUCKET','BACKUP_KMS_KEY_ID')
    if any(not os.getenv(k) for k in required):raise ValueError('Backup configuration incomplete')
    env={**os.environ,'PGSSLMODE':'verify-full'}
    with tempfile.TemporaryDirectory(prefix='paktai-backup-') as directory:
        file=Path(directory)/'paktai.dump'
        subprocess.run(['pg_dump','--format=custom','--schema=paktai_edu','--no-owner','--no-acl','--file',str(file)],env=env,check=True,capture_output=True)
        key='paktai-edu/'+datetime.now(timezone.utc).strftime('%Y/%m/%d/%H%M%S')+'.dump'
        boto3.client('s3').upload_file(str(file),os.environ['BACKUP_BUCKET'],key,
          ExtraArgs={'ServerSideEncryption':'aws:kms','SSEKMSKeyId':os.environ['BACKUP_KMS_KEY_ID']})
    print('Encrypted backup uploaded; restore drill still required.')
if __name__=='__main__':main()
