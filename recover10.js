const fs = require('fs');
const path = require('path');

const brainDir = 'C:\\Users\\vinho\\.gemini\\antigravity\\brain';
let maxLen = 0;
let bestContent = '';

function searchDir(dir) {
  const files = fs.readdirSync(dir);
  for (const file of files) {
    const fullPath = path.join(dir, file);
    const stat = fs.statSync(fullPath);
    if (stat.isDirectory()) {
      searchDir(fullPath);
    } else if (file === 'transcript_full.jsonl' || fullPath.includes('.system_generated\\messages\\')) {
      try {
        const text = fs.readFileSync(fullPath, 'utf8');
        const lines = text.split('\n');
        for (const line of lines) {
          if (!line) continue;
          if (line.includes('transactions_list.html') && line.includes('<div x-data=')) {
            // Found a line!
            try {
              const data = JSON.parse(line);
              let str = '';
              if (data.content) str = data.content;
              else if (data.tool_calls) str = JSON.stringify(data.tool_calls);
              
              if (str.length > maxLen) {
                maxLen = str.length;
                bestContent = str;
              }
            } catch(e) {}
          }
        }
      } catch(e) {}
    }
  }
}

searchDir(brainDir);
fs.writeFileSync('ultimate_best.txt', bestContent);
console.log('Done, ultimate best length:', maxLen);
