const fs = require('fs');
const path = require('path');
const readline = require('readline');

const logPath = 'C:\\Users\\vinho\\.gemini\\antigravity\\brain\\f5ab185c-3cc4-49a4-b85c-5d61b2b7308b\\.system_generated\\logs\\transcript_full.jsonl';

const rl = readline.createInterface({
  input: fs.createReadStream(logPath),
  crlfDelay: Infinity
});

rl.on('line', (line) => {
  try {
    const data = JSON.parse(line);
    if (data.source === 'SYSTEM' && data.content && data.content.includes('File Path: `file:///C:/Users/vinho/Downloads/FinanceTracker/templates/transactions_list.html`') && data.content.includes('Total Lines: 507')) {
      fs.writeFileSync('recovered.txt', data.content);
      console.log('Found it!');
      process.exit(0);
    }
  } catch (e) {}
});

rl.on('close', () => {
  console.log('Not found.');
});
