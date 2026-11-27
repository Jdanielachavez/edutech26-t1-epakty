"""Run isolated schema migration with administrator credentials; no secret output."""
import os
from pathlib import Path
import psycopg
from psycopg.conninfo import conninfo_to_dict
from dotenv import load_dotenv
ROOT=Path(__file__).resolve().parents[1]
def main():
    load_dotenv(ROOT/'.env')
    url=os.environ['MIGRATION_DATABASE_URL']
    if conninfo_to_dict(url).get('sslmode')!='verify-full':raise ValueError('Migration requires sslmode=verify-full')
    with psycopg.connect(url) as connection:
        connection.execute((ROOT/'sql/04_schema_base_datos.sql').read_text())
    print('Schema paktai_edu migrated. Grant paktai_service to the dedicated runtime login separately.')
if __name__=='__main__':main()
