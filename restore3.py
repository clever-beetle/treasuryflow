with open('temp_clean.html', 'r', encoding='utf-8') as f:
    orig = f.read()

with open('templates/financial_performance.html', 'r', encoding='utf-8') as f:
    curr = f.read()

# Let's find exactly the first line of curr in orig.
# The first line of curr is "                                    </div>"
# But it might not be unique.
# Let's use the first 50 chars of curr to search.
first_50 = curr[:50]
idx = orig.find(first_50)
if idx != -1:
    missing_top = orig[:idx]
    with open('templates/financial_performance.html', 'w', encoding='utf-8') as f:
        f.write(missing_top + curr)
    print("Restored using first_50!")
else:
    print("Could not find first_50")
