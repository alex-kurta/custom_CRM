(function () {
    // Account row highlighting via EspoCRM API.
    // Reads cPrePay, cPastDue, cDoNotContact, cBankrupt, cDoNotSell from Account
    // records and applies .pre-pay / .past-due / .flagged CSS classes.
    // Severity (lowest to highest): pre-pay (yellow #f0bc5b),
    // past-due (mid red #c16765), flagged (dark red #65333b).

    function highlightRows() {
        if (typeof $ === 'undefined') return;

        var rows = $('tr.list-row:not([data-past-due-done])');
        if (!rows.length) return;

        var ids = [];
        rows.each(function () {
            var id = $(this).attr('data-id');
            if (id) ids.push(id);
        });
        if (!ids.length) return;

        var auth = null;
        try { auth = localStorage.getItem('espo-user-auth'); } catch (e) {}

        var headers = {};
        if (auth) headers['Espo-Authorization'] = auth;

        var prePayIds = {};
        var pastDueIds = {};
        var flaggedIds = {};
        var CHUNK = 50;
        var done = 0;

        for (var c = 0; c < ids.length; c += CHUNK) {
            var chunk = ids.slice(c, c + CHUNK);
            var whereData = {
                'where[0][type]': 'in',
                'where[0][attribute]': 'id'
            };
            chunk.forEach(function (id, i) {
                whereData['where[0][value][' + i + ']'] = id;
            });

            $.ajax({
                url: '/api/v1/Account',
                type: 'GET',
                headers: headers,
                data: $.extend({
                    select: 'id,cPrePay,cPastDue,cDoNotContact,cBankrupt,cDoNotSell',
                    maxSize: chunk.length
                }, whereData),
                dataType: 'json',
                success: function (data) {
                    if (data && data.list) {
                        for (var j = 0; j < data.list.length; j++) {
                            var acct = data.list[j];
                            if (acct.cPrePay) prePayIds[acct.id] = true;
                            if (acct.cPastDue) pastDueIds[acct.id] = true;
                            if (acct.cDoNotContact || acct.cBankrupt || acct.cDoNotSell) flaggedIds[acct.id] = true;
                        }
                    }
                    done++;
                    if (done === Math.ceil(ids.length / CHUNK)) applyClasses();
                },
                error: function () {
                    done++;
                    if (done === Math.ceil(ids.length / CHUNK)) applyClasses();
                }
            });
        }

        function applyClasses() {
            rows.each(function () {
                var rid = $(this).attr('data-id');
                if (flaggedIds[rid]) {
                    $(this).addClass('flagged');
                } else if (pastDueIds[rid]) {
                    $(this).addClass('past-due');
                } else if (prePayIds[rid]) {
                    $(this).addClass('pre-pay');
                }
                $(this).attr('data-past-due-done', '1');
            });
        }
    }

    function injectHighlightCSS() {
        var CSS_ID = 'past-due-highlight-css';
        if (document.getElementById(CSS_ID)) return;
        var s = document.createElement('style');
        s.id = CSS_ID;
        s.textContent =
            'tr.list-row.pre-pay { background-color: rgba(240, 188, 91, 0.25) !important; }' +
            'tr.list-row.pre-pay:hover { background-color: rgba(240, 188, 91, 0.5) !important; }' +
            'tr.list-row.past-due { background-color: rgba(193, 103, 101, 0.25) !important; }' +
            'tr.list-row.past-due:hover { background-color: rgba(193, 103, 101, 0.5) !important; }' +
            'tr.list-row.flagged { background-color: rgba(101, 51, 59, 0.4) !important; }' +
            'tr.list-row.flagged:hover { background-color: rgba(101, 51, 59, 0.55) !important; }';
        document.head.appendChild(s);
    }

    function scan() {
        injectHighlightCSS();
        highlightRows();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () {
            setTimeout(scan, 2000);
            setInterval(scan, 3000);
        });
    } else {
        setTimeout(scan, 2000);
        setInterval(scan, 3000);
    }
})();
