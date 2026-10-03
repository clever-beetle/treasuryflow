with open('templates/base_shadcn.html', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace(
    "request.endpoint == 'transactions.transactions_list'",
    "request.endpoint in ['transactions.transactions_list', 'transactions.transactions_calendar']"
)

with open('templates/base_shadcn.html', 'w', encoding='utf-8') as f:
    f.write(content)
print('Replaced')
