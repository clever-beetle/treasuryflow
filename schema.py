import os
from dotenv import load_dotenv
load_dotenv()
import psycopg2

conn = psycopg2.connect(os.environ['DATABASE_URL'], sslmode='require')
cur = conn.cursor()

# Check existing columns in transactions
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='transactions'")
cols = [r[0] for r in cur.fetchall()]
print("Current transactions columns:", cols)

# Add linked_transaction_id if missing
if 'linked_transaction_id' not in cols:
    print("Adding linked_transaction_id column...")
    cur.execute("ALTER TABLE transactions ADD COLUMN linked_transaction_id INTEGER")
    conn.commit()
    print("Done!")
else:
    print("linked_transaction_id already exists.")

# Check all tables exist
cur.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'")
tables = [r[0] for r in cur.fetchall()]
print("\nAll tables in database:", tables)

conn.close()
