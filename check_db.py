import sqlite3
db = sqlite3.connect('database.db')
db.row_factory = sqlite3.Row
rows = db.execute('SELECT * FROM accounts LIMIT 5').fetchall()
for r in rows:
    print(dict(r))
