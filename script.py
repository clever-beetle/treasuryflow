import psycopg2
import psycopg2.extras
import os
import re

with open('.env', 'rb') as f:
    env = f.read().decode('utf-16', errors='ignore')

match = re.search(r'DATABASE_URL="(.*?)"', env)
url = match.group(1)

conn = psycopg2.connect(url)
cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

user_id = 1
try:
    cursor.execute('SELECT id FROM users LIMIT 1')
    user_id = cursor.fetchone()[0]
    print('Testing user:', user_id)
except:
    pass

queries = [
    "SELECT name, initial_balance, current_balance FROM accounts WHERE user_id = %s",
    "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE user_id = %s AND type = 'expense' AND category != 'Transfer'",
    "SELECT COALESCE(MAX(amount), 0) FROM transactions WHERE user_id = %s AND type = 'expense' AND category != 'Transfer'",
    "SELECT * FROM debts_receivables WHERE user_id = %s AND status = 'BELUM LUNAS' ORDER BY due_date ASC",
    "SELECT * FROM recurring_installments WHERE user_id = %s AND is_active = 1 ORDER BY due_day_of_month ASC",
    "SELECT category, COALESCE(SUM(purchase_price), 0) as total FROM assets WHERE user_id = %s GROUP BY category",
    "SELECT id, name, target_amount, current_amount, due_date, status, COALESCE((current_amount / NULLIF(target_amount, 0) * 100), 0) as percentage FROM financial_goals WHERE user_id = %s ORDER BY status DESC, due_date ASC",
    "SELECT t.id, t.date, t.type, t.amount, t.category, t.description, a.name AS account_name FROM transactions t JOIN accounts a ON t.account_id = a.id WHERE t.user_id = %s AND t.category != 'Transfer' ORDER BY t.date ASC"
]

for i, q in enumerate(queries):
    try:
        cursor.execute(q, (user_id,))
        res = cursor.fetchall()
        print(f'Query {i} OK, rows: {len(res)}')
    except Exception as e:
        print(f'Query {i} ERROR:', e)
        conn.rollback()
