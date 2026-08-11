const fs = require('fs');

const logPaths = [
  'C:\\Users\\vinho\\.gemini\\antigravity\\brain\\9922428c-3a64-4423-baf3-90b6c2037f13\\.system_generated\\logs\\transcript_full.jsonl',
  'C:\\Users\\vinho\\.gemini\\antigravity\\brain\\f5ab185c-3cc4-49a4-b85c-5d61b2b7308b\\.system_generated\\logs\\transcript_full.jsonl'
];

let outArr = [];

for (const logPath of logPaths) {
  try {
    const lines = fs.readFileSync(logPath, 'utf8').split('\n');
    for (const line of lines) {
      if (!line) continue;
      try {
        const data = JSON.parse(line);
        if (data.source === 'SYSTEM' && data.content && data.content.includes('transactions_list.html')) {
          outArr.push(data.content);
        }
      } catch(e) {}
    }
  } catch(e) {}
}

fs.writeFileSync('recovered_all.json', JSON.stringify(outArr, null, 2));
console.log('Done, length:', outArr.length);
