const fs = require('fs');
const path = require('path');
const readline = require('readline');

const logPath = 'C:\\Users\\vinho\\.gemini\\antigravity\\brain\\9922428c-3a64-4423-baf3-90b6c2037f13\\.system_generated\\logs\\transcript_full.jsonl';

const rl = readline.createInterface({
  input: fs.createReadStream(logPath),
  crlfDelay: Infinity
});

let found = false;

rl.on('line', (line) => {
  try {
    const data = JSON.parse(line);
    if (data.source === 'SYSTEM' && data.content && data.content.includes('File Path: `file:///C:/Users/vinho/Downloads/FinanceTracker/templates/transactions_list.html`') && data.content.includes('Showing lines')) {
      fs.appendFileSync('recovered_chunks.txt', data.content + '\n==================\n');
      found = true;
    }
  } catch (e) {}
});

rl.on('close', () => {
  if (!found) console.log('Not found in parent transcript either.');
  else console.log('Recovered chunks!');
});
