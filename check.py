with open('temp_clean.html', 'r', encoding='utf-8') as f:
    orig = f.read()
idx = orig.find('Tidak ada saldo tersedia')
if idx != -1:
    print(orig[idx-200:idx+200])
