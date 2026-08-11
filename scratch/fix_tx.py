import sys

file_path = "routes/transactions.py"

with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
for idx, line in enumerate(lines):
    # Keep lines up to 832
    if idx <= 831:
        new_lines.append(line)

new_logic = """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Transactions"

    headers = ['Date', 'Type', 'Amount (Rp)', 'Description', 'Category', 'Account']
    ws.append(headers)
    
    header_fill = PatternFill(start_color="11237E", end_color="11237E", fill_type="solid")
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = header_fill

    cat_totals = {}
    row_idx = 2
    
    for tx in transactions:
        amount = tx['amount']
        type_cap = tx['type'].capitalize() if tx['type'] else ''
        ws.append([tx['date'], type_cap, amount, tx['description'], tx['category'], tx['account_name']])
        
        if tx['type'] == 'expense':
            cat = tx['category']
            cat_totals[cat] = cat_totals.get(cat, 0) + amount
        
        ws.cell(row=row_idx, column=3).number_format = '#,##0'
        row_idx += 1

    for col in ws.columns:
        max_length = 0
        column = col[0].column_letter
        for cell in col:
            try:
                if len(str(cell.value)) > max_length: max_length = len(str(cell.value))
            except: pass
        ws.column_dimensions[column].width = max_length + 2
"""

new_lines.extend([new_logic])

for idx, line in enumerate(lines):
    # Resume after line 835
    if idx >= 836:
        new_lines.append(line)

with open(file_path, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
