const fs = require('fs');
const arr = JSON.parse(fs.readFileSync('recovered_all.json', 'utf8'));
for (let i=0; i<arr.length; i++) {
  console.log(`[${i}] len=${arr[i].length}: ${arr[i].substring(0, 100).replace(/\n/g, '\\n')}`);
}
