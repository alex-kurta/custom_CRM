define('custom:views/account/list', ['views/list'], function (Dep) {

    return Dep.extend({

        setup: function () {
            this.options.checkboxes = false;
            this.options.selectable = false;
            this.options.rowActionsView = null;
            this.options.rowActionsDisabled = true;
            this.options.massActionsDisabled = true;

            this.defaultOrderBy = 'cTotalOrderAmount';
            this.defaultOrder = 'desc';
            this.collection.setOrder('cTotalOrderAmount', 'desc', true);

            Dep.prototype.setup.call(this);

            this.checkboxes = false;
            this.checkboxesDisabled = true;
            this.selectEnabled = false;
            this.massActionsDisabled = true;
            this.rowActionsView = null;
            this.rowActionsDisabled = true;
            this.createDisabled = true;

            this.injectCSS();

            this.listenTo(this.collection, 'sync', function () {
                var self = this;
                setTimeout(function () { self.highlightPastDue(); }, 200);
                setTimeout(function () { self.highlightPastDue(); }, 800);
            });
        },

        afterRender: function () {
            Dep.prototype.afterRender.call(this);
            this.highlightPastDue();
            this.makeRowsClickable();
            this.hideUnwantedElements();
        },

        injectCSS: function () {
            if (document.getElementById('account-list-custom-css')) return;
            var style = document.createElement('style');
            style.id = 'account-list-custom-css';
            style.textContent =
                'tr.past-due-highlight, div.list-row.past-due-highlight { background-color: #fff3cd !important; }' +
                'tr.past-due-highlight:hover, div.list-row.past-due-highlight:hover { background-color: #ffe9a0 !important; }';
            document.head.appendChild(style);
        },

        hideUnwantedElements: function () {
            this.$el.find('.checkbox-cell').hide();
            this.$el.find('th.checkbox-cell').hide();
            this.$el.find('.list-btn-cell').hide();
            this.$el.find('th.list-btn-cell').hide();
            this.$el.find('.list-row-buttons').hide();
            this.$el.find('.list-button-column').hide();
            this.$el.find('.btn-group-actions').hide();
        },

        makeRowsClickable: function () {
            var self = this;
            this.$el.off('click.account-row');
            this.$el.on('click.account-row', 'tr.list-row, div.list-row', function (e) {
                if ($(e.target).closest('a').length) return;
                var id = $(this).attr('data-id');
                if (id) {
                    self.getRouter().navigate('#Account/view/' + id, {trigger: true});
                }
            });
        },

        highlightPastDue: function () {
            var self = this;
            var rows = this.$el.find('tr.list-row, div.list-row');
            if (!rows.length) return;

            rows.each(function () {
                var id = $(this).attr('data-id');
                if (!id) return;
                var model = self.collection.get(id);
                if (model && model.get('cPastDue')) {
                    $(this).addClass('past-due-highlight');
                }
            });
        }
    });
});
