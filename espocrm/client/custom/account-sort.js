(function () {
    // Set default sort: cTotalOrderAmount desc
    function setDefaultSort() {
        try {
            var key = 'espo-listSorting-Account';
            var existing = localStorage.getItem(key);
            if (existing) return;
            var sort = JSON.stringify({orderBy: 'cTotalOrderAmount', order: 'desc'});
            localStorage.setItem(key, '__JSON__:' + sort);
        } catch (e) {}
    }

    // Monkey-patch list view setup to persist sort across navigation
    function patchListSortPersistence() {
        if (!window.Espo || !window.Espo.views || !window.Espo.views.List) return;
        if (window.Espo.views.List.prototype._sortPatchApplied) return;

        var OriginalSetup = window.Espo.views.List.prototype.setup;
        window.Espo.views.List.prototype.setup = function () {
            if (this.scope === 'Account') {
                try {
                    var raw = localStorage.getItem('espo-listSorting-Account');
                    if (raw) {
                        var json = raw.indexOf('__JSON__:') === 0 ? raw.substring(9) : raw;
                        var stored = JSON.parse(json);
                        if (stored && stored.orderBy) {
                            this.defaultOrderBy = stored.orderBy;
                            this.defaultOrder = stored.order || 'desc';
                        }
                    }
                } catch (e) {}
            }
            OriginalSetup.apply(this, arguments);
        };
        window.Espo.views.List.prototype._sortPatchApplied = true;
    }

    setDefaultSort();
    patchListSortPersistence();
})();
