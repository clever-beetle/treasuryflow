import codecs
with codecs.open('temp_8635.html', 'r', 'utf-16le') as f:
    orig = f.read()
print(orig[:200])
