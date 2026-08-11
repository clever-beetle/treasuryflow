const fs = require('fs');
const lines = JSON.parse(fs.readFileSync('recovered_lines.json', 'utf8'));

let maxLen = 0;
let bestContent = '';

for (const line of lines) {
  const data = JSON.parse(line);
  let str = '';
  if (data.content) str = data.content;
  else if (data.tool_calls) str = JSON.stringify(data.tool_calls);
  
  // Also check tool responses, which might be in 'tool_responses' or similar?
  // Wait, in transcript.jsonl, a tool response might just be data.content where data.type == "ACTION_RESPONSE"
  if (data.type === 'ACTION_RESPONSE' && data.content) {
      str = data.content;
  }

  // The actual text is inside str, but it might be JSON stringified.
  // Let's just find the first occurrence of "1: {% extends" or similar and extract up to the end.
  // Actually, let's just write the largest str we can find, we can clean it up manually.
  
  if (str.length > maxLen) {
    maxLen = str.length;
    bestContent = str;
  }
}

fs.writeFileSync('best.txt', bestContent);
console.log('Max length:', maxLen);
