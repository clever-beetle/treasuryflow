lines = []
with open('templates/financial_performance.html', 'r', encoding='utf-8') as f:
    for line in f:
        if '<img' in line and 'wikimedia' in line:
            lines.append(line.strip())

macro_lines = []
for line in lines:
    parts = line.split('<img src="')
    cond = parts[0]
    src = parts[1].split('"')[0]
    alt = line.split('alt="')[1].split('"')[0] if 'alt="' in line else ''
    new_line = f"{cond}<img src=\"{src}\" class=\"w-full h-full object-contain\" alt=\"{alt}\" onerror=\"this.outerHTML='<i data-lucide=\\'wallet\\' class=\\'w-6 h-6 text-primary\\'></i>'; lucide.createIcons();\">"
    if '{% if' in cond:
        new_line = new_line.replace('{% if', '{% elif')
    macro_lines.append("        " + new_line)

with open('templates/macros.html', 'r', encoding='utf-8') as f:
    macro_content = f.read()

import re
pattern = re.compile(r'        {% elif \'BCA\'.*?        {% else %}', re.DOTALL)
replacement = '\n'.join(macro_lines) + '\n        {% else %}'
new_macro = pattern.sub(replacement, macro_content)

new_macro = new_macro.replace('img/cash.jpg', 'img/cash_100k.jpg')

with open('templates/macros.html', 'w', encoding='utf-8') as f:
    f.write(new_macro)

with open('templates/financial_performance.html', 'r', encoding='utf-8') as f:
    fp_content = f.read()

if '{% if \'CASH\' in d %}' not in fp_content:
    cash_img_line = "{% if 'CASH' in d %}<img src=\"{{ url_for('static', filename='img/cash_100k.jpg') }}\" class=\"w-5 h-5 object-cover rounded-sm\" alt=\"Cash\" title=\"Cash\">\n                                              "
    fp_content = fp_content.replace("{% if 'BCA' in d %}", cash_img_line + "{% elif 'BCA' in d %}")
    with open('templates/financial_performance.html', 'w', encoding='utf-8') as f:
        f.write(fp_content)

print('Done!')
