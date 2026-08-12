import subprocess
out = subprocess.check_output(['git', 'show', '9b79bf3e:templates/financial_performance.html'])
with open('temp_clean.html', 'wb') as f:
    f.write(out)
