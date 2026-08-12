import subprocess
out = subprocess.check_output(['git', 'show', 'fcc9b155:templates/financial_performance.html'])
with open('temp_clean_fc.html', 'wb') as f:
    f.write(out)
