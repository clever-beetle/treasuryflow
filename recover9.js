const fs = require('fs');

const logPath = 'C:\\Users\\vinho\\.gemini\\antigravity\\brain\\f5ab185c-3cc4-49a4-b85c-5d61b2b7308b\\.system_generated\\logs\\transcript_full.jsonl';
let bestContent = '';

try {
  const lines = fs.readFileSync(logPath, 'utf8').split('\n');
  for (const line of lines) {
    if (!line) continue;
    try {
      const data = JSON.parse(line);
      let str = '';
      if (data.type === 'ACTION_RESPONSE' && data.content) str = data.content;
      else if (data.content) str = data.content;
      
      if (str.includes('File Path: `file:///C:/Users/vinho/Downloads/FinanceTracker/templates/transactions_list.html`')) {
        if (str.length > bestContent.length) {
          bestContent = str;
        }
      }
    } catch(e) {}
  }
} catch(e) {}

fs.writeFileSync('subagent_best.txt', bestContent);
console.log('Subagent best length:', bestContent.length);
