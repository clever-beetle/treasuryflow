import re

def replace_logos(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Add import to top if not present
    if '{% import \\'macros.html\\' as macros %}' not in content and '{% import "macros.html" as macros %}' not in content:
        content = content.replace('{% extends \\'base_shadcn.html\\' %}', '{% extends \\'base_shadcn.html\\' %}\n{% import \\'macros.html\\' as macros %}')
        content = content.replace('{% extends "base_shadcn.html" %}', '{% extends "base_shadcn.html" %}\n{% import \\'macros.html\\' as macros %}')
    
    # Dashboard pattern 1 (with text label)
    pattern1 = r"{% set raw_d = tx\.account_name\.upper\(\) if tx\.account_name else '' %}\s*{% set d = raw_d\.replace\(' ', ''\) %}\s*<div class=\"flex items-center gap-3\">\s*<div class=\"w-10 h-7 flex items-center justify-center\">[\s\S]*?</div>\s*<span class=\"font-medium text-sm\">{{ tx\.account_name\.split\('\] '\)\[-1\] if '\] ' in tx\.account_name else tx\.account_name }}</span>\s*</div>"
    content = re.sub(pattern1, "{{ macros.render_account_logo(tx.account_name) }}", content)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

replace_logos('templates/dashboard.html')
