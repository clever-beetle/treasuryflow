import re

# 1. Fix routes/settings.py
with open('routes/settings.py', 'r', encoding='utf-8') as f:
    settings = f.read()

settings = settings.replace(
    "accounts = db.execute('SELECT id, name, initial_balance, current_balance FROM accounts WHERE user_id = ?', (user_id,)).fetchall()",
    "accounts = db.execute('SELECT id, name, initial_balance, current_balance, account_type, limit_amount FROM accounts WHERE user_id = ?', (user_id,)).fetchall()"
)

with open('routes/settings.py', 'w', encoding='utf-8') as f:
    f.write(settings)

# 2. Fix templates/setup_account.html
with open('templates/setup_account.html', 'r', encoding='utf-8') as f:
    html = f.read()

new_balance_html = """              </div>
              <div class="p-6 pt-4 bg-muted/20">
                  <div class="flex justify-between items-end">
                      <div>
                          <p class="text-sm text-muted-foreground mb-1">Current Balance</p>
                          <p class="text-2xl font-bold tracking-tight">Rp {{ "{:,.0f}".format(account.current_balance).replace(',', '.') }}</p>
                      </div>
                      {% if account.limit_amount %}
                      <div class="text-right">
                          <p class="text-xs text-muted-foreground mb-1">Credit Limit</p>
                          <p class="text-sm font-semibold text-muted-foreground">Rp {{ "{:,.0f}".format(account.limit_amount).replace(',', '.') }}</p>
                      </div>
                      {% endif %}
                  </div>
              </div>"""

html = re.sub(
    r'\s*</div>\s*<div class="p-6 pt-4 bg-muted/20">\s*<p class="text-sm text-muted-foreground mb-1">Current Balance</p>\s*<p class="text-2xl font-bold tracking-tight">Rp \{\{ "\{:,\.0f\}".format\(account\.current_balance\)\.replace\(\',\', \'\.\'\) \}\}</p>\s*</div>',
    new_balance_html,
    html
)

with open('templates/setup_account.html', 'w', encoding='utf-8') as f:
    f.write(html)
