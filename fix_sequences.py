from dotenv import load_dotenv
import os
load_dotenv()

import utils
import psycopg2

db = psycopg2.connect(os.environ.get('DATABASE_URL'), sslmode='require')
db.autocommit = True
cursor = db.cursor()

tables = ['users', 'accounts', 'transactions', 'debts', 'installments', 'savings_goals', 'assets', 'notifications', 'webauthn_credentials', 'error_logs']

for t in tables:
    try:
        cursor.execute(f"SELECT COALESCE(MAX(id), 1) FROM {t}")
        max_id = cursor.fetchone()[0]
        cursor.execute(f"SELECT setval(pg_get_serial_sequence('{t}', 'id'), {max_id + 1}, false)")
        print(f"Fixed sequence for {t} to {max_id + 1}")
    except Exception as e:
        print(f"Failed for {t}: {e}")
