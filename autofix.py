"""
Auto-fix common bugs in templates and Python files.
Run this before deploy to catch and fix issues automatically.
"""
import os, re, sys

fixes_made = []

def fix_templates():
    """Fix common template issues."""
    template_dir = 'templates'
    if not os.path.isdir(template_dir):
        return
    
    for fname in os.listdir(template_dir):
        if not fname.endswith('.html'):
            continue
        path = os.path.join(template_dir, fname)
        with open(path, 'r', encoding='utf-8') as f:
            original = f.read()
        
        content = original
        
        # FIX 1: @click="..." with tojson inside → swap to single quotes
        # This prevents HTML attribute breakage when tojson outputs double-quoted strings
        lines = content.split('\n')
        new_lines = []
        for line in lines:
            if '@click="' in line and 'tojson' in line:
                # Extract the @click="..." part and swap quotes
                def swap_click_quotes(m):
                    inner = m.group(1)
                    # Swap: outer double→single, inner single→double
                    inner = inner.replace("'", '__TEMP__').replace('"', "'").replace('__TEMP__', '"')
                    return f"@click='{inner}'"
                
                line = re.sub(r'@click="([^"]*tojson[^"]*)"', swap_click_quotes, line)
                if line != lines[lines.index(line)]:
                    fixes_made.append(f'{path}: Fixed @click quote mismatch with tojson')
            new_lines.append(line)
        content = '\n'.join(new_lines)
        
        # FIX 2: Remove opacity-0 from action buttons (breaks mobile)
        # Pattern: buttons with lucide icons that have opacity-0
        old_content = content
        content = re.sub(
            r'(class="[^"]*?)opacity-0 group-hover:opacity-100 focus:opacity-100([^"]*?")',
            r'\1\2',
            content
        )
        if content != old_content:
            # Clean up double spaces from removal
            content = re.sub(r'  +', ' ', content)
            fixes_made.append(f'{path}: Removed opacity-0 from buttons (mobile fix)')
        
        # FIX 3: English confirm() dialogs → translate or flag
        old_content = content
        content = content.replace(
            "confirm('Delete this transaction?')",
            "confirm('Yakin ingin menghapus transaksi ini?')"
        )
        content = content.replace(
            "confirm('Are you sure you want to delete these transactions?')",
            "confirm('Yakin ingin menghapus transaksi yang dipilih?')"
        )
        content = content.replace(
            'confirm("Delete this transaction?")',
            'confirm("Yakin ingin menghapus transaksi ini?")'
        )
        if content != old_content:
            fixes_made.append(f'{path}: Translated confirm() dialogs to Indonesian')
        
        # Write back if changed
        if content != original:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)


def fix_python():
    """Fix common Python issues."""
    py_files = ['app.py', 'utils.py', 'models.py'] + \
               [os.path.join('routes', f) for f in os.listdir('routes') if f.endswith('.py')]
    
    for path in py_files:
        if not os.path.isfile(path):
            continue
        with open(path, 'r', encoding='utf-8') as f:
            original = f.read()
        
        content = original
        
        # FIX: Bare except → except Exception
        old_content = content
        content = re.sub(r'except\s*:', 'except Exception:', content)
        if content != old_content:
            fixes_made.append(f'{path}: Fixed bare except → except Exception')
        
        if content != original:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)


if __name__ == '__main__':
    fix_templates()
    fix_python()
    
    if fixes_made:
        print(f'🔧 Auto-fixed {len(fixes_made)} issue(s):')
        for fix in fixes_made:
            print(f'  • {fix}')
    else:
        print('✅ No issues found - all clean!')
    
    # Exit 0 always (fixes are applied, not errors)
    sys.exit(0)
