import requests
import re
import html

url = 'https://www.treasuryflow.web.id/dev-console?key=1'
s = requests.Session()
res = s.get(url)
csrf_match = re.search(r'name="csrf_token" value="(.*?)"', res.text)
if not csrf_match:
    print('No CSRF token found')
    exit(1)
csrf_token = csrf_match.group(1)

def run_query(q):
    print(f'Running: {q}')
    res = s.post(url, data={'action': 'run_query', 'query': q, 'csrf_token': csrf_token})
    match = re.search(r'<table.*?>(.*?)</table>', res.text, re.DOTALL)
    if not match:
        print('No table found')
        return
    table_html = match.group(1)
    
    rows = re.findall(r'<tr>(.*?)</tr>', table_html, re.DOTALL)
    if not rows:
        return
        
    headers = [html.unescape(th).strip() for th in re.findall(r'<th>(.*?)</th>', rows[0], re.DOTALL)]
    for row in rows[1:]:
        cols = [html.unescape(td).strip() for td in re.findall(r'<td>(.*?)</td>', row, re.DOTALL)]
        print(dict(zip(headers, cols)))

run_query('SELECT id, name, initial_balance, current_balance, account_type FROM accounts')
run_query('SELECT id, account_id, type, amount, category FROM transactions')
