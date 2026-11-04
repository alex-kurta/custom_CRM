define('custom:controllers/past-due-import', ['controller'], function (Dep) {

    return Dep.extend({

        checkAccess: function () {
            return !!this.getAcl().checkScope('Account', 'edit');
        },

        actionIndex: function () {
            this.main('custom:views/past-due-import/index', {});
        },
    });
});
