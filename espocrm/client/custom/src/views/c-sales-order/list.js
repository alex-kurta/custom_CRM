// nuke buttons cell for cSalesOrders list - more aggressive
define('custom:views/c-sales-order/list', ['views/list'], function (Dep) {
    return Dep.extend({
        rowActionsView: false,
        setup: function () {
            Dep.prototype.setup.call(this);
            this.rowActionsView = false;
            this.options.rowActionsView = false;
            // also try to disable via layout
            if (this.options.layout) {
                // remove any buttons column from layout
            }
        },
        setup: function () {
            if (typeof Handlebars !== 'undefined' && !Handlebars.helpers['isNotCsalesOrder']) {
                Handlebars.registerHelper('isNotCsalesOrder', function(scope, options) {
                    return scope !== 'CSalesOrder' ? options.fn(this) : options.inverse(this);
                });
            }
            Dep.prototype.setup.call(this);
        },
        afterRender: function () {
            Dep.prototype.afterRender.call(this);
            var nuke = () => {
                this.$el.find('[data-name="buttons"]').closest('td, th, .cell').remove();
                this.$el.find('[data-name="buttons"]').remove();
                this.$el.find('td.cell[data-name="buttons"], th[data-name="buttons"]').remove();
                this.$el.find('.list-row-buttons').closest('td').remove();
            };
            nuke();
            // also listen to collection sync to re-nuke after re-render
            if (this.collection) {
                this.listenTo(this.collection, 'sync', nuke);
            }
            this.$el.find('.list-row').css('cursor', 'pointer');
            this.$el.find('.list-row').hover(function(){$(this).css('cursor','pointer');}, function(){$(this).css('cursor','');});
            // also use MutationObserver to catch re-renders
            var observer = new MutationObserver(nuke);
            observer.observe(this.el, {childList: true, subtree: true});
        }
    });
});
