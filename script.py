import os
import psycopg2
import psycopg2.extras
import re

with open('.env', 'rb') as f:
    env = f.read().decode('utf-16')

match = re.search(r'DATABASE_URL="(.*?)"', env)
url = match.group(1)

conn = psycopg2.connect(url)
cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
try:
    cursor.execute('SELECT * FROM error_logs ORDER BY created_at DESC LIMIT 5')
    for r in cursor.fetchall():
        print(r['created_at'], repr(r['error'][:800]))
except Exception as e:
    print('No error_logs table or other error:', e)
