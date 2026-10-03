import os
import glob

def fix_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    new_lines = []
    for line in lines:
        new_lines.append(line)
        if line.strip() == 'except Exception as e:':
            # find the indentation of 'except'
            indent = line[:len(line) - len(line.lstrip())]
            # add db.rollback() with one more level of indentation
            new_lines.append(indent + '    try:\n')
            new_lines.append(indent + '        db.rollback()\n')
            new_lines.append(indent + '    except:\n')
            new_lines.append(indent + '        pass\n')
            
    with open(filepath, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
        
    print(f"Fixed {filepath}")

for f in glob.glob('routes/*.py'):
    fix_file(f)
