(function () {
    function setupRowClicks() {
        var rows = document.querySelectorAll('tr.list-row:not([data-click-bound])');
        rows.forEach(function (row) {
            row.setAttribute('data-click-bound', '1');
            var nameCell = row.querySelector('td[data-name="name"] a[href]');
            if (!nameCell) return;
            var href = nameCell.getAttribute('href');
            row.style.cursor = 'pointer';
            row.addEventListener('click', function (e) {
                if (e.target.closest('a, button, input[type="checkbox"], .dropdown-menu, .btn-group')) return;
                window.location.hash = href;
            });
        });
    }

    function scan() {
        setupRowClicks();
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
