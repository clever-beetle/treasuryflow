with open('templates/macros.html', 'r', encoding='utf-8') as f:
    m = f.read()
m = m.replace(
    "or 'SHOPEEPAY' in d",
    "or 'SHOPEEPAY' in d or 'SPINJAM' in d or 'HONEST' in d"
)
m = m.replace(
    "{% elif 'SHOPEEPAY' in d %}<img src=\"https://upload.wikimedia.org/wikipedia/commons/f/fe/Shopee.svg\" class=\"w-full h-full object-contain\" alt=\"ShopeePay\" onerror=\"this.outerHTML='<i data-lucide=\\'wallet\\' class=\\'w-6 h-6 text-primary\\'></i>'; lucide.createIcons();\">",
    "{% elif 'SHOPEEPAY' in d or 'SPINJAM' in d %}<img src=\"https://upload.wikimedia.org/wikipedia/commons/f/fe/Shopee.svg\" class=\"w-full h-full object-contain\" alt=\"ShopeePay\" onerror=\"this.outerHTML='<i data-lucide=\\'wallet\\' class=\\'w-6 h-6 text-primary\\'></i>'; lucide.createIcons();\">\n        {% elif 'HONEST' in d %}<img src=\"https://icon.horse/icon/honest.co.id\" class=\"w-full h-full object-contain\" alt=\"Honest Card\" onerror=\"this.outerHTML='<i data-lucide=\\'wallet\\' class=\\'w-6 h-6 text-primary\\'></i>'; lucide.createIcons();\">"
)
with open('templates/macros.html', 'w', encoding='utf-8') as f:
    f.write(m)

with open('templates/financial_performance.html', 'r', encoding='utf-8') as f:
    fp = f.read()
fp = fp.replace(
    "{% elif 'SHOPEEPAY' in d %}<img src=\"https://upload.wikimedia.org/wikipedia/commons/f/fe/Shopee.svg\" class=\"w-5 h-5 object-contain\" alt=\"ShopeePay\" title=\"ShopeePay\">",
    "{% elif 'SHOPEEPAY' in d or 'SPINJAM' in d %}<img src=\"https://upload.wikimedia.org/wikipedia/commons/f/fe/Shopee.svg\" class=\"w-5 h-5 object-contain\" alt=\"ShopeePay\" title=\"ShopeePay\">\n                                            {% elif 'HONEST' in d %}<img src=\"https://icon.horse/icon/honest.co.id\" class=\"w-5 h-5 object-contain\" alt=\"Honest Card\" title=\"Honest Card\">"
)
with open('templates/financial_performance.html', 'w', encoding='utf-8') as f:
    f.write(fp)
print('Updated templates')
