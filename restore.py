import codecs

with codecs.open('temp_9b.html', 'r', 'utf-16le') as f:
    orig = f.read()
    
with codecs.open('templates/financial_performance.html', 'r', 'utf-8') as f:
    curr = f.read()

# Find the split point in original
# The current file starts with:
#                                     </div>
#                                 </div>
#                                 {% endfor %}
#                             {% else %}
#                                 <div class="text-center py-8 text-muted-foreground border-2 border-dashed border-border rounded-xl">
#                                     <p class="text-sm">Tidak ada saldo tersedia untuk dianalisis.</p>

split_text = 'Tidak ada saldo tersedia'
if split_text in orig:
    idx_orig = orig.find(split_text)
    
    # We need to find the exact line in orig
    # Let's just find {% for acc in accounts %} or similar and just re-assemble it?
    # Actually, current file starts exactly somewhere around here.
    
    # Let's find the first 50 chars of current file
    idx_curr_first_chars = curr[:50].strip()
    
    # find where this is in orig
    idx_in_orig = orig.find('</div>\r\n                                </div>\r\n                                {% endfor %}')
    
    if idx_in_orig != -1:
        missing_top = orig[:idx_in_orig]
        with codecs.open('templates/financial_performance.html', 'w', 'utf-8') as f_out:
            f_out.write(missing_top + curr)
        print("Restored missing top!")
    else:
        print("Could not find sync point!")
else:
    print("Could not find split text")
