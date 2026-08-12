import subprocess
out = subprocess.check_output(['git', 'show', '8635b2c1:templates/financial_performance.html'])
with open('temp_clean_86.html', 'wb') as f:
    f.write(out)
