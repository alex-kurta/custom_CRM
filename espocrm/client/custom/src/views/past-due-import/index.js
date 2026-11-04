define('custom:views/past-due-import/index', ['view'], function (Dep) {

    return Dep.extend({

        template: 'custom:past-due-import/index',

        events: {
            'change #import-file': 'onFileChange',
            'click #import-btn': 'onImport',
            'click #dry-run-btn': 'onDryRun',
            'click #reset-btn': 'onReset',
        },

        data: function () {
            return {
                error: this.error || null,
                result: this.result || null,
                importing: this.importing || false,
                fileName: this.file ? this.file.name : '',
            };
        },

        afterRender: function () {
            var hasFile = !!this.file;

            this.$('#import-btn').prop('disabled', !hasFile || this.importing);
            this.$('#dry-run-btn').prop('disabled', !hasFile || this.importing);
        },

        onFileChange: function (e) {
            var file = e.target.files[0];

            this.file = file || null;
            this.error = null;
            this.result = null;

            this.$('#import-file-name').text(this.file ? this.file.name : '');
            this.$('#import-btn').prop('disabled', !this.file);
            this.$('#dry-run-btn').prop('disabled', !this.file);
        },

        onImport: function () {
            this.doImport(false);
        },

        onDryRun: function () {
            this.doImport(true);
        },

        onReset: function () {
            this.file = null;
            this.error = null;
            this.result = null;
            this.importing = false;
            this.reRender();
        },

        doImport: function (dryRun) {
            if (!this.file || this.importing) {
                return;
            }

            this.importing = true;
            this.error = null;
            this.result = null;
            this.reRender();

            var url = 'PastDueImport' +
                '?fileName=' + encodeURIComponent(this.file.name) +
                '&dryRun=' + (dryRun ? '1' : '0');

            var self = this;

            Espo.Ajax.postRequest(url, null, {
                contentType: 'application/octet-stream',
                data: this.file,
                timeout: 0,
            }).then(function (data) {
                self.importing = false;
                self.result = data;
                self.reRender();
                Espo.Ui.success(dryRun ? 'Dry run complete' : 'Import complete');
            }).catch(function (xhr) {
                var message = 'Import failed';

                try {
                    var body = JSON.parse(xhr.responseText);

                    if (body && body.message) {
                        message = body.message;
                    }
                } catch (e) {
                    // Keep the generic message.
                }

                self.importing = false;
                self.error = message;
                self.reRender();
            });
        },
    });
});
