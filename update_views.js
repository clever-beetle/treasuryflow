const fs = require('fs');

let content = fs.readFileSync('templates/transactions_list.html', 'utf8');

// 1. Change calendar day links from view=calendar to view=list
content = content.replace(/\?view=calendar(&amp;|&)start_date={{ d_str }}/g, "?view=list$1start_date={{ d_str }}");

// 2. Wrap Filter Toolbar and Table in {% if view == 'list' %}
// The filter toolbar starts at <!-- Filter Toolbar -->
let filterIndex = content.indexOf('<!-- Filter Toolbar -->');
if (filterIndex !== -1) {
    content = content.substring(0, filterIndex) + "{% if view == 'list' %}\n        " + content.substring(filterIndex);
}

// 3. Close the {% if view == 'list' %} at the end of the block 
// The block ends right before the closing </div> of the main <div class="space-y-6"> block.
// Let's find the end of the content block.
// The file ends with:
// {% endblock %}
// {% block scripts %}
let endBlockIndex = content.lastIndexOf('{% endblock %}', content.indexOf('{% block scripts %}'));
if (endBlockIndex !== -1) {
    // We need to insert {% endif %} before the final </div> that closes `<div class="space-y-6">` or similar
    // Actually, it's safer to just replace `    </div>\n{% endblock %}` with `    </div>\n    {% endif %}\n</div>\n{% endblock %}`
    // Let's just find the last </div> before {% endblock %}
    let lastDiv = content.lastIndexOf('</div>', endBlockIndex);
    if (lastDiv !== -1) {
        content = content.substring(0, lastDiv + 6) + "\n        {% endif %}" + content.substring(lastDiv + 6);
    }
}

// Also, Alpine JS x-show="view === 'list'" on the Filter Toolbar is now redundant but harmless.
// Same for x-show="view === 'calendar'" on the Calendar View. We can leave them or remove them.
// Let's replace x-show="view === 'calendar'" with nothing because we will also wrap the calendar in {% if view == 'calendar' %}
let calIndex = content.indexOf('<!-- Calendar View -->');
if (calIndex !== -1) {
    content = content.substring(0, calIndex) + "{% if view == 'calendar' %}\n        " + content.substring(calIndex);
    
    // The calendar view ends before the filter toolbar.
    // The filter toolbar starts at {% if view == 'list' %} which we just added.
    let newFilterIndex = content.indexOf("{% if view == 'list' %}");
    if (newFilterIndex !== -1) {
        content = content.substring(0, newFilterIndex) + "{% endif %}\n\n        " + content.substring(newFilterIndex);
    }
}

fs.writeFileSync('templates/transactions_list.html', content);
console.log('transactions_list.html updated!');
