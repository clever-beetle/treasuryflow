const fs = require('fs');

const logPaths = [
  'C:\\Users\\vinho\\.gemini\\antigravity\\brain\\9922428c-3a64-4423-baf3-90b6c2037f13\\.system_generated\\logs\\transcript_full.jsonl',
  'C:\\Users\\vinho\\.gemini\\antigravity\\brain\\f5ab185c-3cc4-49a4-b85c-5d61b2b7308b\\.system_generated\\logs\\transcript_full.jsonl'
];

let foundLines = [];

for (const logPath of logPaths) {
  try {
    const lines = fs.readFileSync(logPath, 'utf8').split('\n');
    for (const line of lines) {
      if (line.includes('x-data') && line.includes('transactions_list.html')) {
        foundLines.push(line);
      }
    }
  } catch(e) {}
}

fs.writeFileSync('recovered_lines.json', JSON.stringify(foundLines, null, 2));
console.log('Found:', foundLines.length);
