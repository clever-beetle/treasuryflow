import re

with open('templates/financial_performance.html', 'r', encoding='utf-8') as f:
    fp = f.read()

# Replace the title and description
fp = fp.replace(
    '<h3 class="text-lg font-semibold tracking-tight">Pelacakan Kartu Kredit</h3>',
    '<h3 class="text-lg font-semibold tracking-tight">Kartu Kredit, Pinjaman Online, dan Paylater</h3>'
)

# We will use regex to replace the block
pattern = r'<div class="w-10 h-10 rounded bg-indigo-100 dark:bg-indigo-900/50 flex\s+items-center justify-center">\s*<i data-lucide="credit-card" class="w-5 h-5 text-indigo-600\s+dark:text-indigo-400"></i>\s*</div>\s*<div>\s*<h4 class="font-semibold text-sm">\{\{\s*cc\.name\s*\}\}</h4>'

replacement = """<div class="w-12 h-8 bg-white border border-border/50 rounded flex items-center justify-center p-1 shrink-0">
                                              {{ macros.render_icon_only(cc.name) }}
                                          </div>
                                          <div>
                                              {% set clean_name = cc.name.split('] ')[1] if '] ' in cc.name else cc.name %}
                                              <h4 class="font-semibold text-sm">{{ clean_name }}</h4>"""

fp_new = re.sub(pattern, replacement, fp, count=1)

with open('templates/financial_performance.html', 'w', encoding='utf-8') as f:
    f.write(fp_new)
