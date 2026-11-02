define('custom:views/past-due-import/index', ['view'], function (Dep) {

    return Dep.extend({

        template: 'past-due-import:index',

        events: {
            'change #import-file': 'onFileChange',
            'click #import-btn': 'onImport',
            'click #dry-run-btn': 'onDryRun',
        },

        data: function () {
            return {
                error: this.error || null,
                result: this.result || null,
                importing: this.importing || false,
            };
        },

        onFileChange: function (e) {
            var file = e.target.files[0];
            if (file) {
                this.file = file;
                this.$('#import-btn').prop('disabled', false);
                this.$('#dry-run-btn').prop('disabled', false);
            }
        },

        onImport: function () {
            this.doImport(false);
        },

        onDryRun: function () {
            this.doImport(true);
        },

        doImport: function (dryRun) {
            if (!this.file) return;

            var self = this;
            this.importing = true;
            this.error = null;
            this.result = null;
            this.reRender();

            var formData = new FormData();
            formData.append('file', this.file);
            formData.append('dryRun', dryRun ? '1' : '0');

            // Use Espo.Ajax or direct XHR to upload
            var xhr = new XMLHttpRequest();
            xhr.open('POST', 'api/v1/PastDueImport', true);
            xhr.setRequestHeader('X-Api-Key', this.getMetadata().get('appKey') || '');

            xhr.onload = function () {
                self.importing = false;
                if (xhr.status === 200) {
                    try {
                        var data = JSON.parse(xhr.responseText);
                        if (data.error) {
                            self.error = data.error;
                        } else {
                            self.result = data;
                        }
                    } catch (e) {
                        self.error = 'Invalid response from server';
                    }
                } else {
                    self.error = 'Import failed: ' + xhr.status;
                }
                self.reRender();
            };

            xhr.onerror = function () {
                self.importing = false;
                self.error = 'Network error';
                self.reRender();
            };

            xhr.send(formData);
        },
    });
});