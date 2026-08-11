const fs = require('fs');

let content = fs.readFileSync('templates/transactions_list.html', 'utf8');

content = content.replace(/url_for\('add_transaction'\)/g, "url_for('transactions.add_transaction')");
content = content.replace(/url_for\('transactions_list'\)/g, "url_for('transactions.transactions_list')");
content = content.replace(/url_for\('export_pdf'\)/g, "url_for('transactions.export_pdf')");
content = content.replace(/url_for\('export_csv'\)/g, "url_for('transactions.export_csv')");
content = content.replace(/url_for\('delete_transaction'/g, "url_for('transactions.delete_transaction'");
content = content.replace(/url_for\('bulk_delete_transactions'\)/g, "url_for('transactions.bulk_delete_transactions')");
content = content.replace(/url_for\('bulk_edit_transactions'\)/g, "url_for('transactions.bulk_edit_transactions')");

fs.writeFileSync('templates/transactions_list.html', content);
console.log('Fixed url_for calls!');
