import re
import os

# 1. Update app.py
with open('app.py', 'r', encoding='utf-8') as f:
    app_content = f.read()

if 'def inject_clean_url():' not in app_content:
    injection = '''
@app.context_processor
def inject_clean_url():
    def clean_url(endpoint, **kwargs):
        from flask import url_for
        filtered_kwargs = {}
        for k, v in kwargs.items():
            if v == '' or v is None:
                continue
            if k == 'page' and (v == 1 or v == '1'):
                continue
            if k == 'sort_by' and v == 'date':
                continue
            if k == 'sort_order' and v == 'desc':
                continue
            filtered_kwargs[k] = v
            
        if endpoint == 'transactions.transactions_list':
            if filtered_kwargs.get('view') == 'calendar':
                endpoint = 'transactions.transactions_calendar'
                filtered_kwargs.pop('view')
            elif filtered_kwargs.get('view') == 'list':
                filtered_kwargs.pop('view', None)
                
        return url_for(endpoint, **filtered_kwargs)
    return dict(clean_url=clean_url)
'''
    # insert before @app.after_request
    app_content = app_content.replace('@app.after_request', injection + '\n@app.after_request')
    with open('app.py', 'w', encoding='utf-8') as f:
        f.write(app_content)

# 2. Update routes/transactions.py
with open('routes/transactions.py', 'r', encoding='utf-8') as f:
    trans_content = f.read()

if '@transactions_bp.route(\'/calendar\'' not in trans_content:
    new_route = '''@transactions_bp.route('/calendar', strict_slashes=False, endpoint='transactions_calendar')
@login_required
def transactions_calendar():
    from flask import request
    # Pass all query args to transactions_list but override view
    args = request.args.copy()
    args['view'] = 'calendar'
    request.args = args
    return transactions_list()

@transactions_bp.route('', strict_slashes=False)'''
    trans_content = trans_content.replace('@transactions_bp.route(\'\', strict_slashes=False)', new_route, 1)
    with open('routes/transactions.py', 'w', encoding='utf-8') as f:
        f.write(trans_content)

# 3. Update templates/transactions_list.html
with open('templates/transactions_list.html', 'r', encoding='utf-8') as f:
    tpl = f.read()

# Replace hardcoded hrefs with clean_url
# We just need to replace the big long query string hrefs with clean_url calls.
# I will use a simple regex or just string replacement for the most common ones.

replacements = {
    # View toggles
    'href="?view=list&cal_year={{ cal_year }}&cal_month={{ cal_month }}&start_date={{ start_date }}&end_date={{ end_date }}&category={{ selected_category }}&account_id={{ selected_account }}&search={{ search_query }}&sort_by={{ sort_by }}&sort_order={{ sort_order }}&page={{ page }}"': 'href="{{ clean_url(\'transactions.transactions_list\', view=\'list\', cal_year=cal_year, cal_month=cal_month, start_date=start_date, end_date=end_date, category=selected_category, account_id=selected_account, search=search_query, sort_by=sort_by, sort_order=sort_order, page=page) }}"',
    
    'href="?view=calendar&cal_year={{ cal_year }}&cal_month={{ cal_month }}&start_date={{ start_date }}&end_date={{ end_date }}&category={{ selected_category }}&account_id={{ selected_account }}&search={{ search_query }}&sort_by={{ sort_by }}&sort_order={{ sort_order }}&page={{ page }}"': 'href="{{ clean_url(\'transactions.transactions_list\', view=\'calendar\', cal_year=cal_year, cal_month=cal_month, start_date=start_date, end_date=end_date, category=selected_category, account_id=selected_account, search=search_query, sort_by=sort_by, sort_order=sort_order, page=page) }}"',
    
    # Calendar month navigation
    'href="?view=calendar&cal_year={{ cal_year if cal_month > 1 else cal_year - 1 }}&cal_month={{ cal_month - 1 if cal_month > 1 else 12 }}&start_date={{ start_date }}&end_date={{ end_date }}&category={{ selected_category }}&account_id={{ selected_account }}&search={{ search_query }}&sort_by={{ sort_by }}&sort_order={{ sort_order }}&page={{ page }}"': 'href="{{ clean_url(\'transactions.transactions_list\', view=\'calendar\', cal_year=(cal_year if cal_month > 1 else cal_year - 1), cal_month=(cal_month - 1 if cal_month > 1 else 12), start_date=start_date, end_date=end_date, category=selected_category, account_id=selected_account, search=search_query, sort_by=sort_by, sort_order=sort_order, page=page) }}"',
    
    'href="?view=calendar&cal_year={{ now.year }}&cal_month={{ now.month }}&start_date={{ start_date }}&end_date={{ end_date }}&category={{ selected_category }}&account_id={{ selected_account }}&search={{ search_query }}&sort_by={{ sort_by }}&sort_order={{ sort_order }}&page={{ page }}"': 'href="{{ clean_url(\'transactions.transactions_list\', view=\'calendar\', cal_year=now.year, cal_month=now.month, start_date=start_date, end_date=end_date, category=selected_category, account_id=selected_account, search=search_query, sort_by=sort_by, sort_order=sort_order, page=page) }}"',
    
    'href="?view=calendar&cal_year={{ cal_year if cal_month < 12 else cal_year + 1 }}&cal_month={{ cal_month + 1 if cal_month < 12 else 1 }}&start_date={{ start_date }}&end_date={{ end_date }}&category={{ selected_category }}&account_id={{ selected_account }}&search={{ search_query }}&sort_by={{ sort_by }}&sort_order={{ sort_order }}&page={{ page }}"': 'href="{{ clean_url(\'transactions.transactions_list\', view=\'calendar\', cal_year=(cal_year if cal_month < 12 else cal_year + 1), cal_month=(cal_month + 1 if cal_month < 12 else 1), start_date=start_date, end_date=end_date, category=selected_category, account_id=selected_account, search=search_query, sort_by=sort_by, sort_order=sort_order, page=page) }}"',

    # Calendar day click
    'href="?view=list&start_date={{ d_str }}&end_date={{ d_str }}&cal_month={{ cal_month }}&cal_year={{ cal_year }}&category={{ selected_category }}&account_id={{ selected_account }}&search={{ search_query }}&sort_by={{ sort_by }}&sort_order={{ sort_order }}&page={{ page }}"': 'href="{{ clean_url(\'transactions.transactions_list\', view=\'list\', start_date=d_str, end_date=d_str, cal_month=cal_month, cal_year=cal_year, category=selected_category, account_id=selected_account, search=search_query, sort_by=sort_by, sort_order=sort_order, page=1) }}"',
    
    # Pagination
    'href="?view={{ view }}&page={{ page - 1 }}&sort_by={{ sort_by }}&sort_order={{ sort_order }}&search={{ search_query }}&start_date={{ start_date }}&end_date={{ end_date }}&category={{ selected_category }}&account_id={{ selected_account }}"': 'href="{{ clean_url(\'transactions.transactions_list\', view=view, page=page - 1, sort_by=sort_by, sort_order=sort_order, search=search_query, start_date=start_date, end_date=end_date, category=selected_category, account_id=selected_account) }}"',
    
    'href="?view={{ view }}&page={{ page + 1 }}&sort_by={{ sort_by }}&sort_order={{ sort_order }}&search={{ search_query }}&start_date={{ start_date }}&end_date={{ end_date }}&category={{ selected_category }}&account_id={{ selected_account }}"': 'href="{{ clean_url(\'transactions.transactions_list\', view=view, page=page + 1, sort_by=sort_by, sort_order=sort_order, search=search_query, start_date=start_date, end_date=end_date, category=selected_category, account_id=selected_account) }}"'
}

for old, new in replacements.items():
    tpl = tpl.replace(old, new)

# And the sort headers!
# 'href="?view={{ view }}&page={{ page }}&sort_by={{ col_name }}&sort_order={{ new_order }}&search={{ search_query }}&start_date={{ start_date }}&end_date={{ end_date }}&category={{ selected_category }}&account_id={{ selected_account }}"'
tpl = tpl.replace(
    'href="?view={{ view }}&page={{ page }}&sort_by={{ col_name }}&sort_order={{ new_order }}&search={{ search_query }}&start_date={{ start_date }}&end_date={{ end_date }}&category={{ selected_category }}&account_id={{ selected_account }}"',
    'href="{{ clean_url(\'transactions.transactions_list\', view=view, page=1, sort_by=col_name, sort_order=new_order, search=search_query, start_date=start_date, end_date=end_date, category=selected_category, account_id=selected_account) }}"'
)

# And base_shadcn.html side navigation for Calendar!
with open('templates/base_shadcn.html', 'r', encoding='utf-8') as f:
    base = f.read()
base = base.replace(
    '{{ url_for(\'transactions.transactions_list\', view=\'calendar\') }}', 
    '{{ url_for(\'transactions.transactions_calendar\') }}'
)
with open('templates/base_shadcn.html', 'w', encoding='utf-8') as f:
    f.write(base)

with open('templates/transactions_list.html', 'w', encoding='utf-8') as f:
    f.write(tpl)

print('Updated URLs!')
