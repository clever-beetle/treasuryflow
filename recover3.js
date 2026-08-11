const fs = require('fs');
const path = require('path');
const readline = require('readline');

const logPaths = [
  'C:\\Users\\vinho\\.gemini\\antigravity\\brain\\9922428c-3a64-4423-baf3-90b6c2037f13\\.system_generated\\logs\\transcript_full.jsonl',
  'C:\\Users\\vinho\\.gemini\\antigravity\\brain\\f5ab185c-3cc4-49a4-b85c-5d61b2b7308b\\.system_generated\\logs\\transcript_full.jsonl'
];

let outStr = '';

for (const logPath of logPaths) {
  try {
    const lines = fs.readFileSync(logPath, 'utf8').split('\n');
    for (const line of lines) {
      if (!line) continue;
      try {
        const data = JSON.parse(line);
        let content = '';
        if (data.source === 'SYSTEM' && data.content) content = data.content;
        else if (data.type === 'ACTION_RESPONSE' && data.content) content = data.content;
        
        if (content.includes('transactions_list.html')) {
          if (content.includes('<div x-data="{')) {
            outStr += `\n\n=== FOUND IN ${logPath} ===\n\n`;
            outStr += content;
          }
        }
      } catch(e) {}
    }
  } catch(e) {}
}

fs.writeFileSync('recovered_all.txt', outStr);
console.log('Done searching, see recovered_all.txt. Length:', outStr.length);
