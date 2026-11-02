define('custom:views/account/panels/c-sales-orders', ['views/record/panels/relationship'], function (Dep) {
    return Dep.extend({
        showMore: false,
        rowActionsView: false,
        orderBy: 'fishbowlNum',
        orderDirection: 'desc',

        setup: function () {
            if (typeof Handlebars !== 'undefined' && !Handlebars.helpers['isNotCsalesOrder']) {
                Handlebars.registerHelper('isNotCsalesOrder', function (scope, options) {
                    return scope !== 'CSalesOrder' ? options.fn(this) : options.inverse(this);
                });
                Handlebars.registerHelper('isCsalesOrder', function (scope, options) {
                    return scope === 'CSalesOrder' ? options.fn(this) : options.inverse(this);
                });
            }
            Dep.prototype.setup.call(this);
            this.rowActionsView = false;
            this.options.rowActionsView = false;
            if (this.collection) {
                this.collection.maxSize = 200;
            }
            // The relationship panel builds data.select from layout columns (orderDate is
            // hidden there) but merges defs.mandatoryAttributeList into it before fetching.
            this.defs.mandatoryAttributeList = this.defs.mandatoryAttributeList || [];
            if (this.defs.mandatoryAttributeList.indexOf('orderDate') === -1) {
                this.defs.mandatoryAttributeList.push('orderDate');
            }
            this.dateFilterFrom = null;
            this.dateFilterTo = null;
        },

        injectDateFilter: function () {
            var self = this;
            var $panel = this.$el.closest('.panel');
            if (!$panel.length) $panel = this.$el.parents('.panel').first();
            if (!$panel.length) return;

            var $container = $panel.find('.panel-actions-container');
            if (!$container.length) return;

            var $existingBtn = $container.find('button').first();
            if (!$existingBtn.length || $existingBtn.data('dateFilterBound')) return;
            $existingBtn.data('dateFilterBound', true);

            // Replace button content with calendar icon
            $existingBtn
                .removeClass('dropdown-toggle')
                .removeAttr('data-toggle aria-expanded')
                .attr('title', 'Filter by date range')
                .html('<i class="fas fa-calendar-alt"></i>');

            // Build popover
            var $popover = $(
                '<div class="date-filter-popover" style="display:none; position:absolute; top:100%; right:0; z-index:100; background:var(--panel-bg, #fff); border:1px solid var(--panel-default-border, #ddd); border-radius:var(--panel-border-radius, 4px); box-shadow:var(--default-box-shadow, 0 2px 8px rgba(0,0,0,0.12)); padding:12px; min-width:260px;">' +
                '<div style="display:flex; gap:8px; align-items:center; margin-bottom:8px;">' +
                '<label style="font-size:12px; color:var(--text-muted-color, #888); white-space:nowrap;">From</label>' +
                '<input type="date" class="date-filter-from form-control input-sm" style="flex:1; font-size:13px; padding:4px 6px; height:auto;">' +
                '</div>' +
                '<div style="display:flex; gap:8px; align-items:center; margin-bottom:10px;">' +
                '<label style="font-size:12px; color:var(--text-muted-color, #888); white-space:nowrap;">To</label>' +
                '<input type="date" class="date-filter-to form-control input-sm" style="flex:1; font-size:13px; padding:4px 6px; height:auto;">' +
                '</div>' +
                '<div style="display:flex; gap:6px; justify-content:flex-end;">' +
                '<button class="btn btn-sm btn-default date-filter-clear" style="font-size:12px;">Clear</button>' +
                '<button class="btn btn-sm btn-primary date-filter-apply" style="font-size:12px;">Apply</button>' +
                '</div>' +
                '<div class="date-filter-status" style="font-size:11px; color:var(--text-muted-color, #888); margin-top:6px; text-align:right;"></div>' +
                '</div>'
            );

            $container.css('position', 'relative').append($popover);

            $existingBtn.on('click', function (e) {
                e.stopPropagation();
                $popover.toggle();
            });

            $(document).on('click.dateFilter', function (e) {
                if (!$(e.target).closest('.date-filter-popover, .panel-actions-container').length) {
                    $popover.hide();
                }
            });

            $popover.on('click', function (e) { e.stopPropagation(); });

            $popover.find('.date-filter-apply').on('click', function () {
                var fromVal = $popover.find('.date-filter-from').val();
                var toVal = $popover.find('.date-filter-to').val();
                self.dateFilterFrom = fromVal ? new Date(fromVal + 'T00:00:00') : null;
                self.dateFilterTo = toVal ? new Date(toVal + 'T23:59:59') : null;
                self.applyDateFilter();
                $popover.hide();
            });

            $popover.find('.date-filter-clear').on('click', function () {
                $popover.find('.date-filter-from').val('');
                $popover.find('.date-filter-to').val('');
                self.dateFilterFrom = null;
                self.dateFilterTo = null;
                self.applyDateFilter();
                $popover.find('.date-filter-status').text('');
                $popover.hide();
            });
        },

        applyDateFilter: function () {
            var self = this;
            var from = this.dateFilterFrom;
            var to = this.dateFilterTo;
            var $rows = this.$el.find('.list-row').not('.detail-row');
            var shown = 0;
            var hidden = 0;

            $rows.each(function () {
                var $row = $(this);
                var id = $row.data('id');
                if (!id) return;

                var model = null;
                if (self.collection && self.collection.models) {
                    model = self.collection.get(id);
                }

                if (!from && !to) {
                    $row.removeClass('hidden');
                    shown++;
                    return;
                }

                var orderDate = null;
                if (model) {
                    var raw = model.get('orderDate');
                    if (raw) orderDate = new Date(raw);
                }

                if (!orderDate) {
                    $row.addClass('hidden');
                    hidden++;
                    return;
                }

                if (from && orderDate < from) {
                    $row.addClass('hidden');
                    hidden++;
                    return;
                }
                if (to && orderDate > to) {
                    $row.addClass('hidden');
                    hidden++;
                    return;
                }

                $row.removeClass('hidden');
                shown++;
            });

            // Hide/show detail-rows paired with each list-row
            $rows.each(function () {
                var $row = $(this);
                var id = $row.data('id');
                if (!id) return;
                var $detail = self.$el.find('.detail-row[data-id="' + id + '"]');
                if (!$detail.length) return;
                if ($row.hasClass('hidden')) {
                    $detail.addClass('hidden').data('filterHidden', true);
                } else if ($detail.data('filterHidden')) {
                    $detail.removeClass('hidden').removeData('filterHidden');
                }
            });

            var $panel = this.$el.closest('.panel');
            if (!$panel.length) $panel = this.$el.parents('.panel').first();
            var $status = $panel.find('.date-filter-status');
            if (from || to) {
                var parts = [];
                if (from) parts.push('from ' + from.toLocaleDateString());
                if (to) parts.push('to ' + to.toLocaleDateString());
                $status.text(shown + ' of ' + (shown + hidden) + ' shown (' + parts.join(' ') + ')');
            } else {
                $status.text('');
            }
        },

        afterRender: function () {
            Dep.prototype.afterRender.call(this);
            var self = this;

            var nukeButtons = function () {
                self.$el.find('[data-name="buttons"]').closest('td, th, .cell').remove();
                self.$el.find('[data-name="buttons"]').remove();
                self.$el.find('td.cell[data-name="buttons"], th[data-name="buttons"]').remove();
                self.$el.find('.list-row-buttons').closest('td, .cell').remove();
                self.$el.find('th[data-name="buttons"], td[data-name="buttons"]').remove();
            };
            nukeButtons();
            if (this.collection) {
                this.listenTo(this.collection, 'sync', nukeButtons);
            }

            var sortDomRows = function () {
                setTimeout(function () {
                    var $rows = self.$el.find('.list-row').not('.detail-row');
                    if ($rows.length < 2) return;
                    var $parent = $rows.first().parent();
                    var arr = $rows.toArray();
                    arr.sort(function (a, b) {
                        var aText = $(a).find('[data-name="fishbowlNum"]').text().trim();
                        var bText = $(b).find('[data-name="fishbowlNum"]').text().trim();
                        var aNum = parseInt(aText, 10) || 0;
                        var bNum = parseInt(bText, 10) || 0;
                        return bNum - aNum;
                    });
                    arr.forEach(function (row) {
                        var $row = $(row);
                        $parent.append($row);
                        var id = $row.data('id');
                        if (id) {
                            var $detail = $parent.children('.detail-row[data-id="' + id + '"]');
                            $parent.append($detail);
                        }
                    });
                }, 300);
            };
            if (this.collection) {
                this.listenTo(this.collection, 'sync', sortDomRows);
            }

            var observer = new MutationObserver(nukeButtons);
            observer.observe(this.el, { childList: true, subtree: true });

            this.$el.off('click', '.list-row');
            this.$el.on('click', '.list-row', function (e) {
                if ($(e.target).closest('a, button, input').length) return;
                var $row = $(this);
                var id = $row.data('id');
                if (!id) return;
                var $detailRow = $row.next('.detail-row[data-id="' + id + '"]');
                if ($detailRow.length) {
                    $detailRow.toggleClass('hidden');
                    return;
                }
                var isTr = $row.is('tr');
                var colspan = $row.children('td, div.cell').length || 4;
                var $newRow;
                if (isTr) {
                    $newRow = $('<tr class="detail-row" data-id="' + id + '"><td colspan="' + colspan + '" style="padding:0; border-top:0;"><div class="detail-content panel-body" style="padding:0;"></div></td></tr>');
                } else {
                    $newRow = $('<div class="detail-row" data-id="' + id + '" style="padding:0; border-top:1px solid var(--panel-default-border, #ddd);"><div class="detail-content panel-body" style="padding:0;"></div></div>');
                    if ($row.is('li')) {
                        $newRow = $('<li class="detail-row" data-id="' + id + '" style="padding:0;"><div class="detail-content panel-body" style="padding:0;"></div></li>');
                    }
                }
                $row.after($newRow);
                var $content = $newRow.find('.detail-content');
                $content.html('<div class="text-muted" style="padding:8px 15px;">Loading...</div>');
                Espo.Ajax.getRequest('CSalesOrder/' + id).then(function (data) {
                    var html = '<div class="row" style="margin:0; padding:8px 15px;">' +
                        '<div class="cell col-sm-6 form-group" data-name="status"><label class="control-label"><span class="label-text">Status</span></label><div class="field">' + (data.status || '') + '</div></div>' +
                        '<div class="cell col-sm-6 form-group" data-name="orderDate"><label class="control-label"><span class="label-text">Order Date</span></label><div class="field">' + (data.orderDate || '').split(' ')[0] + '</div></div>' +
                        '</div><div class="sales-items" style="padding:0 15px 8px;"></div>';
                    $content.html(html);
                    $newRow.data('loaded', true);
                    Espo.Ajax.getRequest('CSalesOrder/' + id + '/salesOrderItems', { maxSize: 100 }).then(function (res) {
                        var items = res.list || [];
                        items = items.filter(function (it) {
                            var pn = (it.productNum || '').trim();
                            var name = (it.name || '').trim();
                            if (!pn) return true;
                            if (pn.toLowerCase() === 'shipping') return false;
                            if (/^\d+(\.\d+)?%$/.test(pn)) return false;
                            if (/dry\s*ice/i.test(pn) || /dry\s*ice/i.test(name)) return false;
                            if (/handling/i.test(pn) || /handling/i.test(name)) return false;
                            return true;
                        });
                        if (!items.length) {
                            $content.find('.sales-items').html('<span class="text-muted" style="padding:8px 15px;">No line items</span>');
                            return;
                        }
                        var t = '<table class="table table-bordered table-striped" style="margin:0; table-layout:fixed; width:100%;"><thead><tr><th style="padding:8px 15px; text-align:left;">Product</th><th style="width:110px; white-space:nowrap; padding:8px 15px; text-align:center;">Ordered</th><th style="width:110px; white-space:nowrap; padding:8px 15px; text-align:center;">Fulfilled</th></tr></thead><tbody>';
                        items.forEach(function (it) {
                            var prodName = it.name || it.productNum || '';
                            prodName = prodName.replace(/\s*x\d+(\.\d+)?\s*$/, '').trim();
                            if (!prodName) prodName = it.productNum || '';
                            prodName = prodName.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
                            var prodCell = '<div class="product-name-cell" style="max-width:100%; overflow-x:auto; white-space:nowrap; display:block; scrollbar-width:none; -ms-overflow-style:none; vertical-align:middle; line-height:1.5;" title="' + prodName + '">' + prodName + '</div>';
                            t += '<tr><td style="max-width:0; overflow:hidden; padding:8px 15px; vertical-align:middle;"><div class="product-name-wrapper" style="overflow-x:auto; white-space:nowrap; padding:0; margin:0; scrollbar-width:none; -ms-overflow-style:none; display:flex; align-items:center; min-height:24px;" onmouseenter="this.style.overflowX=\'auto\'" onmouseleave="this.style.overflowX=\'hidden\'">' + prodCell + '</div></td><td class="text-center" style="vertical-align:middle; padding:8px 15px;">' + (it.qtyOrdered || 0) + '</td><td class="text-center" style="vertical-align:middle; padding:8px 15px;">' + (it.qtyFulfilled || 0) + '</td></tr>';
                        });
                        t += '</tbody></table>';
                        $content.find('.sales-items').html(t);
                    });
                });
            });
            this.$el.find('.list-row').css('cursor', 'pointer').attr('title', 'Click to expand');
            nukeButtons();

            setTimeout(function () {
                self.injectDateFilter();
            }, 500);
        }
    });
});
