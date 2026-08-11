const fs = require('fs');

function processFile(filename, replacements) {
    let content = fs.readFileSync(filename, 'utf8');
    let original = content;
    for (const r of replacements) {
        content = content.replace(r.search, r.replace);
    }
    if (content !== original) {
        fs.writeFileSync(filename, content);
        console.log(`Updated ${filename}`);
    } else {
        console.log(`No changes made to ${filename} (maybe already applied?)`);
    }
}

const HAS_LOGO_LOGIC = `{% set has_logo = ('CASH' in d or 'BCA' in d or 'BNI' in d or 'BRI' in d or 'MANDIRI' in d or 'JAGO' in d or 'BSI' in d or 'CIMB' in d or 'SEABANK' in d or 'JENIUS' in d or 'BTPN' in d or 'OCBC' in d or 'MEGA' in d or 'PERMATA' in d or 'BTN' in d or 'HSBC' in d or 'SUPERBANK' in d or 'DKI' in d or 'BJB' in d or 'GOPAY' in d or 'DANA' in d or 'OVO' in d or 'SHOPEEPAY' in d or 'LINKAJA' in d) %}`;

// Dashboard 1: Recent Transactions
processFile('templates/dashboard.html', [
    {
        search: `{% set d = tx.account_name.upper() if tx.account_name else '' %}`,
        replace: `{% set raw_d = tx.account_name.upper() if tx.account_name else '' %}\n                                {% set d = raw_d.replace(' ', '') %}`
    },
    {
        search: `{% else %}<i data-lucide="wallet" class="w-5 h-5 text-primary"></i>{% endif %}
                                    </div>
                                    <span class="font-medium text-sm">{{ tx.account_name.split('] ')[-1] if '] ' in tx.account_name else tx.account_name }}</span>`,
        replace: `{% else %}<i data-lucide="wallet" class="w-5 h-5 text-primary"></i>{% endif %}
                                    </div>
                                    ${HAS_LOGO_LOGIC}
                                    {% if not has_logo %}
                                    <span class="font-medium text-sm">{{ tx.account_name.split('] ')[-1] if '] ' in tx.account_name else tx.account_name }}</span>
                                    {% endif %}`
    }
]);

// Dashboard 2: Account Balances
processFile('templates/dashboard.html', [
    {
        search: `{% set d = acc.name.upper() %}`,
        replace: `{% set raw_d = acc.name.upper() %}\n                            {% set d = raw_d.replace(' ', '') %}`
    },
    {
        search: `{% else %}<i data-lucide="wallet" class="w-5 h-5 text-primary"></i>{% endif %}
                            </div>
                            {% set name_parts = acc.name.split('] ') %}
                            {% set detail_name = name_parts[1] if name_parts|length > 1 else acc.name %}
                            <span class="font-medium text-sm">{{ detail_name }}</span>`,
        replace: `{% else %}<i data-lucide="wallet" class="w-5 h-5 text-primary"></i>{% endif %}
                            </div>
                            ${HAS_LOGO_LOGIC}
                            {% if not has_logo %}
                            {% set name_parts = acc.name.split('] ') %}
                            {% set detail_name = name_parts[1] if name_parts|length > 1 else acc.name %}
                            <span class="font-medium text-sm">{{ detail_name }}</span>
                            {% endif %}`
    }
]);

// Financial Performance
processFile('templates/financial_performance.html', [
    {
        search: `{% set d = acc.name.upper() %}`,
        replace: `{% set raw_d = acc.name.upper() %}\n                                            {% set d = raw_d.replace(' ', '') %}`
    },
    {
        search: `{% else %}<i data-lucide="landmark" class="w-5 h-5 text-blue-500"></i>{% endif %}
                                            <span class="font-medium">{{ acc.name }}</span>`,
        replace: `{% else %}<i data-lucide="landmark" class="w-5 h-5 text-blue-500"></i>{% endif %}
                                            ${HAS_LOGO_LOGIC}
                                            {% if not has_logo %}
                                            <span class="font-medium ml-2">{{ acc.name }}</span>
                                            {% endif %}`
    }
]);

// Setup Account
processFile('templates/setup_account.html', [
    {
        search: `{% set d = account.name.upper() %}`,
        replace: `{% set raw_d = account.name.upper() %}\n                            {% set d = raw_d.replace(' ', '') %}`
    },
    {
        search: `{% if category in ['CASH', 'Custom'] %}`,
        replace: `${HAS_LOGO_LOGIC}\n                        {% if not has_logo %}`
    }
]);

console.log('All files processed!');
