const fs = require('fs');

const arr = JSON.parse(fs.readFileSync('recovered_all.json', 'utf8'));

let maxLen = 0;
let bestContent = '';

for (const c of arr) {
  if (c.includes('Showing lines') || c.includes('Total Lines')) {
    if (c.length > maxLen) {
      maxLen = c.length;
      bestContent = c;
    }
  }
}

fs.writeFileSync('best_recovered.txt', bestContent);
console.log('Done, best length:', maxLen);
