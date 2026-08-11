const fs = require('fs');

const lines = fs.readFileSync('ultimate_best.txt', 'utf8').split('\n');
let outLines = [];

// Format: "line_number: original_line" (e.g. "8: 1: {% extends 'base_shadcn.html' %}")
// Wait, the view_file tool output adds its OWN line numbers to the front:
// "8: 1: {% extends" means view_file added "8: ", and the original string had "1: "
// Wait! In ultimate_best.txt, this is JUST the string from the transcript's view_file output.
// So the string itself has lines like "1: {% extends 'base_shadcn.html' %}"
// Let's check `ultimate_best.txt` line 8: "8: 1: {% extends 'base_shadcn.html' %}"
// That means the view_file tool I JUST RAN added "8: ". 
// So the actual text inside ultimate_best.txt has "1: {% extends" as its FIRST line (well, 8th line of the file).
// Let's just match any line that starts with digits followed by a colon and a space, and strip it!
// E.g., `^\d+: (.*)`
let parsing = false;

for (const line of lines) {
  // If we match exactly "1: {% extends", we can start extracting
  if (!parsing && /^1:\s+{% extends/.test(line)) {
    parsing = true;
  }
  
  if (parsing) {
    const match = line.match(/^\d+:\s(.*)/);
    if (match) {
      outLines.push(match[1]);
    } else {
      // Maybe end of file or something without line numbers
      // Wait, view_file sometimes truncates. Is this the full file? The length is 42595.
    }
  }
}

fs.writeFileSync('templates/transactions_list.html', outLines.join('\n'));
console.log('Restored! Length:', outLines.length);
