"""One-off: point every logo reference in the app to the new brand assets."""
import io
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FAVICON_BLOCK = (
    '<link rel="icon" href="{{ url_for(\'static\', filename=\'favicon.ico\') }}" sizes="any">\n'
    '    <link rel="icon" type="image/png" sizes="32x32" href="{{ url_for(\'static\', filename=\'img/brand/favicon-32.png\') }}">'
)
APPLE = '<link rel="apple-touch-icon" href="{{ url_for(\'static\', filename=\'img/brand/apple-touch-icon.png\') }}">'

TEMPLATE_RULES = [
    # favicon <link rel="icon" ...> (any attribute order) -> ico + 32px png
    (re.compile(r'<link rel="icon"[^>]*logo_v5_512\.png[^>]*>'), FAVICON_BLOCK),
    # apple-touch-icon -> dedicated 180px icon
    (re.compile(r'<link rel="apple-touch-icon"[^>]*>'), APPLE),
    # navbar logo (shadcn) - circular mascot, no white-box filters needed
    (re.compile(r'<img src="\{\{ url_for\(\'static\', filename=\'img/logo_v5_512\.png\'\) \}\}" alt="Logo" class="h-10 w-auto drop-shadow-md[^"]*">'),
     '<img src="{{ url_for(\'static\', filename=\'img/brand/logo_128.png\') }}" alt="Treasury Flow" class="h-10 w-10 object-contain drop-shadow-sm">'),
    # AI chat toggle button - fill the round button with the round mascot
    (re.compile(r'<img src="\{\{ url_for\(\'static\', filename=\'img/logo_v5_512\.png\'\) \}\}" class="h-10 w-10 object-contain" alt="AI">'),
     '<img src="{{ url_for(\'static\', filename=\'img/brand/logo_128.png\') }}" class="h-12 w-12 object-contain" alt="Treasury Flow AI">'),
    # AI chat header avatar - white circle so it pops on the blue gradient
    (re.compile(r'<img src="\{\{ url_for\(\'static\', filename=\'img/logo_v5_512\.png\'\) \}\}" class="h-8 w-8 object-contain drop-shadow-md" alt="AI">'),
     '<img src="{{ url_for(\'static\', filename=\'img/brand/logo_128.png\') }}" class="h-9 w-9 rounded-full bg-white p-0.5 object-contain shadow-md" alt="Treasury Flow AI">'),
    # Auth pages hero logo
    (re.compile(r'<img src="\{\{ url_for\(\'static\', filename=\'img/logo_v5_512\.png\'\) \}\}" alt="Logo" class="h-16 w-auto object-contain">'),
     '<img src="{{ url_for(\'static\', filename=\'img/brand/logo.png\') }}" alt="Treasury Flow" class="h-20 w-20 object-contain drop-shadow-md">'),
    # PWA install banners
    (re.compile(r'<img src="/static/img/logo_v5_192\.png" alt="Icon" class="w-12 h-12 rounded-xl bg-white p-1 shadow-sm">'),
     '<img src="/static/img/brand/logo_128.png" alt="Treasury Flow" class="w-12 h-12 rounded-full bg-white p-0.5 shadow-sm object-contain">'),
    # Notification icon
    (re.compile(r"icon: '/static/icon-512x512\.png'"), "icon: '/static/img/brand/icon_192.png'"),
    # Anything left (legacy bootstrap base.html navbar etc.)
    (re.compile(r'img/logo_v5_512\.png'), 'img/brand/logo.png'),
    (re.compile(r'img/logo_v5_192\.png'), 'img/brand/logo_128.png'),
]


def patch(path, rules):
    with io.open(path, encoding='utf-8', newline='') as f:
        src = f.read()
    out = src
    for pat, rep in rules:
        out = pat.sub(lambda m: rep, out)
    if out != src:
        with io.open(path, 'w', encoding='utf-8', newline='') as f:
            f.write(out)
        print('patched', os.path.relpath(path, ROOT))


tpl_dir = os.path.join(ROOT, 'templates')
for name in sorted(os.listdir(tpl_dir)):
    if name.endswith('.html'):
        patch(os.path.join(tpl_dir, name), TEMPLATE_RULES)

# base_auth.html only had an apple-touch-icon; make sure it has a favicon too
auth = os.path.join(tpl_dir, 'base_auth.html')
with io.open(auth, encoding='utf-8', newline='') as f:
    s = f.read()
if 'favicon.ico' not in s:
    s = s.replace(APPLE, APPLE + '\n    ' + FAVICON_BLOCK, 1)
    with io.open(auth, 'w', encoding='utf-8', newline='') as f:
        f.write(s)
    print('patched templates/base_auth.html (favicon)')

# PDF exports
patch(os.path.join(ROOT, 'routes', 'transactions.py'),
      [(re.compile(r"os\.path\.join\(current_app\.static_folder, 'img', 'logo_v4\.png'\)"),
        "os.path.join(current_app.static_folder, 'img', 'brand', 'logo_pdf.png')")])

# Service worker: new cache version + new icons
patch(os.path.join(ROOT, 'static', 'sw.js'), [
    (re.compile(r"treasuryflow-v\d+"), 'treasuryflow-v11'),
    (re.compile(r"'/static/img/logo_v5_192\.png',\s*\n\s*'/static/img/logo_v5_512\.png',"),
     "'/static/img/brand/icon_192.png',\n        '/static/img/brand/icon_512.png',\n        '/static/img/brand/logo_128.png',"),
])
