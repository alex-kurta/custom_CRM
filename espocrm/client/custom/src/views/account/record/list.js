define('custom:views/account/record/list', ['views/record/list'], function (Dep) {

    return Dep.extend({

        setup: function () {
            this.options.checkboxes = false;
            this.options.massActionsDisabled = true;
            this.options.rowActionsView = null;
            this.options.rowActionsDisabled = true;

            Dep.prototype.setup.call(this);
        }
    });
});
