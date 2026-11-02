define('custom:views/account/panels/past-due', ['view'], function (Dep) {

    return Dep.extend({

        template: '<div class="past-due-panel">{{#if hasData}}<table class="table table-striped past-due-table"><thead><tr><th>SO #</th><th>Order Date</th><th>Due Date</th><th>Aging</th><th>Amount</th><th>Balance</th></tr></thead><tbody>{{#each orders}}<tr><td>{{soNum}}</td><td>{{orderDate}}</td><td>{{dueDate}}</td><td>{{aging}}</td><td>{{formatCurrency amount}}</td><td>{{formatCurrency balance}}</td></tr>{{/each}}</tbody></table><div class="past-due-summary"><strong>Total Open Balance: {{formatCurrency totalBalance}}</strong></div>{{else}}<div class="text-muted">No past due orders.</div>{{/if}}</div>',

        data: function () {
            var pastDue = this.model.get('cPastDue');
            var orders = this.model.get('cPastDueData');
            var total = 0;

            if (pastDue && orders && Array.isArray(orders)) {
                orders.forEach(function (o) {
                    total += parseFloat(o.balance) || 0;
                });
            }

            return {
                hasData: pastDue && orders && orders.length > 0,
                orders: orders || [],
                totalBalance: total
            };
        },

        formatCurrency: function (value) {
            if (value === null || value === undefined) return '';
            return parseFloat(value).toFixed(2);
        }
    });
});
