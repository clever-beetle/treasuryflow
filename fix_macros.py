with open('templates/macros.html', 'r', encoding='utf-8') as f:
    content = f.read()

new_macro = """
{% macro render_icon_only(account_name, extra_classes="w-full h-full object-contain") %}
{% set raw_d = account_name.upper() if account_name else '' %}
{% set d = raw_d.replace(' ', '') %}
        {% if 'CASH' in d %}<img src="{{ url_for('static', filename='img/cash_100k.jpg') }}" class="w-full h-full object-cover rounded-md" alt="Cash">
        {% elif 'BCA' in d %}<img src="https://upload.wikimedia.org/wikipedia/commons/5/5c/Bank_Central_Asia.svg" class="{{ extra_classes }}" alt="BCA">
        {% elif 'BNI' in d %}<img src="https://upload.wikimedia.org/wikipedia/commons/f/f0/Bank_Negara_Indonesia_logo_%282004%29.svg" class="{{ extra_classes }}" alt="BNI">
        {% elif 'BRI' in d %}<img src="https://upload.wikimedia.org/wikipedia/commons/6/6d/BRI_2025.png" class="{{ extra_classes }}" alt="BRI">
        {% elif 'MANDIRI' in d %}<img src="https://upload.wikimedia.org/wikipedia/commons/a/ad/Bank_Mandiri_logo_2016.svg" class="{{ extra_classes }}" alt="Mandiri">
        {% elif 'JAGO' in d %}<img src="https://upload.wikimedia.org/wikipedia/commons/c/c0/Logo-jago.svg" class="{{ extra_classes }}" alt="Jago">
        {% elif 'BSI' in d %}<img src="https://upload.wikimedia.org/wikipedia/commons/a/a0/Bank_Syariah_Indonesia.svg" class="{{ extra_classes }}" alt="BSI">
        {% elif 'CIMB' in d %}<img src="https://upload.wikimedia.org/wikipedia/commons/3/38/CIMB_Niaga_logo.svg" class="{{ extra_classes }}" alt="CIMB">
        {% elif 'SEABANK' in d %}<img src="https://upload.wikimedia.org/wikipedia/commons/a/ac/SeaBank.svg" class="{{ extra_classes }}" alt="SeaBank">
        {% elif 'JENIUS' in d or 'BTPN' in d %}<img src="https://upload.wikimedia.org/wikipedia/id/8/89/Jenius-logo.png" class="{{ extra_classes }}" alt="Jenius">
        {% elif 'OCBC' in d %}<img src="https://upload.wikimedia.org/wikipedia/commons/1/1d/Logo-ocbc.svg" class="{{ extra_classes }}" alt="OCBC">
        {% elif 'MEGA' in d %}<img src="https://upload.wikimedia.org/wikipedia/commons/a/af/Bank_Mega_2013.svg" class="{{ extra_classes }}" alt="Mega">
        {% elif 'PERMATA' in d %}<img src="https://upload.wikimedia.org/wikipedia/id/4/48/PermataBank_logo.svg" class="{{ extra_classes }}" alt="Permata">
        {% elif 'BTN' in d %}<img src="https://upload.wikimedia.org/wikipedia/commons/c/ca/BTN_2024.svg" class="{{ extra_classes }}" alt="BTN">
        {% elif 'HSBC' in d %}<img src="https://upload.wikimedia.org/wikipedia/commons/a/aa/HSBC_logo_%282018%29.svg" class="{{ extra_classes }}" alt="HSBC">
        {% elif 'SUPERBANK' in d %}<img src="https://upload.wikimedia.org/wikipedia/commons/c/c8/Superbank.svg" class="{{ extra_classes }}" alt="Superbank">
        {% elif 'DKI' in d %}<img src="https://upload.wikimedia.org/wikipedia/commons/2/2a/Bank_DKI.svg" class="{{ extra_classes }}" alt="DKI">
        {% elif 'BJB' in d %}<img src="https://upload.wikimedia.org/wikipedia/id/4/41/Bank_BJB_logo.svg" class="{{ extra_classes }}" alt="BJB">
        {% elif 'GOPAY' in d %}<img src="https://upload.wikimedia.org/wikipedia/commons/8/86/Gopay_logo.svg" class="{{ extra_classes }}" alt="GoPay">
        {% elif 'DANA' in d %}<img src="https://upload.wikimedia.org/wikipedia/commons/7/72/Logo_dana_blue.svg" class="{{ extra_classes }}" alt="DANA">
        {% elif 'OVO' in d %}<img src="https://upload.wikimedia.org/wikipedia/commons/e/eb/Logo_ovo_purple.svg" class="{{ extra_classes }}" alt="OVO">
        {% elif 'SHOPEEPAY' in d or 'SPINJAM' in d %}<img src="https://upload.wikimedia.org/wikipedia/commons/f/fe/Shopee.svg" class="{{ extra_classes }}" alt="ShopeePay">
        {% elif 'HONEST' in d %}<img src="https://icon.horse/icon/honest.co.id" class="{{ extra_classes }}" alt="Honest Card">
        {% elif 'LINKAJA' in d %}<img src="https://upload.wikimedia.org/wikipedia/commons/8/85/LinkAja.svg" class="{{ extra_classes }}" alt="LinkAja">
        {% else %}<i data-lucide="credit-card" class="w-6 h-6 text-primary"></i>{% endif %}
{% endmacro %}
"""

with open('templates/macros.html', 'w', encoding='utf-8') as f:
    f.write(content + "\n" + new_macro)

with open('templates/financial_performance.html', 'r', encoding='utf-8') as f:
    fp = f.read()

if "{% import 'macros.html' as macros %}" not in fp:
    fp = fp.replace("{% block page_title %}", "{% import 'macros.html' as macros %}\n{% block page_title %}")

fp = fp.replace(
    '<div class="w-10 h-10 rounded bg-indigo-100 dark:bg-indigo-900/50 flex items-center justify-center">\n                                              <i data-lucide="credit-card" class="w-5 h-5 text-indigo-600 dark:text-indigo-400"></i>\n                                          </div>',
    '<div class="w-12 h-8 bg-white border border-border/50 rounded flex items-center justify-center p-1 shrink-0">\n                                              {{ macros.render_icon_only(cc.name) }}\n                                          </div>'
)

with open('templates/financial_performance.html', 'w', encoding='utf-8') as f:
    f.write(fp)
