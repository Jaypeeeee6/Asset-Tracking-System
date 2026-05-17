/**
 * Client-side search for Settings page tables (dashboard filter-search styling).
 */
(function (global) {
    'use strict';

    var NO_MATCH_CLASS = 'settings-search-no-match-row';

    function applySettingsTableSearch(tbodyId) {
        var tbody = document.getElementById(tbodyId);
        if (!tbody) return;

        var input = document.querySelector('.settings-table-search[data-settings-search-for="' + tbodyId + '"]');
        var query = input ? String(input.value || '').trim().toLowerCase() : '';
        var rows = tbody.querySelectorAll('tr');
        var visible = 0;

        tbody.querySelectorAll('.' + NO_MATCH_CLASS).forEach(function (r) { r.remove(); });

        rows.forEach(function (tr) {
            var placeholder = tr.querySelector('td[colspan]');
            if (placeholder) {
                tr.style.display = query ? 'none' : '';
                return;
            }
            var text = (tr.textContent || '').toLowerCase();
            var show = !query || text.indexOf(query) !== -1;
            tr.style.display = show ? '' : 'none';
            if (show) visible += 1;
        });

        if (query && visible === 0 && rows.length > 0) {
            var hasDataRow = Array.prototype.some.call(rows, function (tr) {
                return !tr.querySelector('td[colspan]');
            });
            if (hasDataRow) {
                var colCount = 1;
                var first = tbody.querySelector('tr:not(.' + NO_MATCH_CLASS + ')');
                if (first) colCount = first.querySelectorAll('td').length || 1;
                var tr = document.createElement('tr');
                tr.className = NO_MATCH_CLASS;
                tr.innerHTML = '<td colspan="' + colCount + '" class="text-center text-muted py-4">No matching results</td>';
                tbody.appendChild(tr);
            }
        }
    }

    function bindSettingsSearchInputs() {
        document.querySelectorAll('.settings-table-search').forEach(function (input) {
            if (input.dataset.settingsSearchBound === '1') return;
            input.dataset.settingsSearchBound = '1';
            input.addEventListener('input', function () {
                applySettingsTableSearch(input.getAttribute('data-settings-search-for'));
            });
        });
    }

    function init() {
        bindSettingsSearchInputs();
        document.querySelectorAll('.settings-table-search').forEach(function (input) {
            applySettingsTableSearch(input.getAttribute('data-settings-search-for'));
        });
    }

    global.applySettingsTableSearch = applySettingsTableSearch;
    global.initSettingsSearch = init;

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})(window);
