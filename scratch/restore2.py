import json
import sys

log_path = r'C:\Users\vinho\.gemini\antigravity\brain\3362f2cc-3430-4fde-8bd6-f1dd04c50cb5\.system_generated\logs\transcript_full.jsonl'

matches = []
with open(log_path, 'r', encoding='utf-8') as f:
    for line in f:
        if 'transactions.py' in line and 'Total Lines' in line:
            matches.append(line)

with open('scratch/extracted2.txt', 'w', encoding='utf-8') as out:
    out.writelines(matches)
