with open('temp_clean.html', 'r', encoding='utf-8') as f:
    orig = f.read()

with open('templates/financial_performance.html', 'r', encoding='utf-8') as f:
    curr = f.read()

# We know the first few lines of current file are:
#                                     </div>
#                                 </div>
#                                 {% endfor %}
first_lines = curr[:200].strip().split('\n')
print(f"First lines of curr: {first_lines}")

idx = orig.find('{% endfor %}\n                            {% else %}')
if idx != -1:
    # Need to go back to the matching '</div>\n                                </div>'
    part1 = orig[:idx]
    # Actually just find the exact text in orig that matches curr
    match_str = curr[:100]
    idx_match = orig.find(match_str)
    if idx_match != -1:
        print(f"Found exact match at index {idx_match}")
        missing_top = orig[:idx_match]
        with open('templates/financial_performance.html', 'w', encoding='utf-8') as f:
            f.write(missing_top + curr)
        print("Restored!")
    else:
        print("Match not found, trying fuzzy match")
        # Let's try matching the first 20 characters of current file
        idx_match = orig.find(curr[:20])
        if idx_match != -1:
            print(f"Found fuzzy match at {idx_match}")
            with open('templates/financial_performance.html', 'w', encoding='utf-8') as f:
                f.write(orig[:idx_match] + curr)
            print("Restored fuzzy!")
        else:
            print("Could not find any match")
else:
    print("Could not find anchor")
