define('custom:views/past-due-import/index', ['view'], function (Dep) {

    return Dep.extend({

        template: 'custom:past-due-import/index',

        data: function () {
            return {
                error: this.error || null,
                result: this.result || null,
                importing: this.importing || false,
                fileName: this.file ? this.file.name : '',
            };
        },

        afterRender: function () {
            var self = this;
            var input = this.$el.find('#import-file').get(0);

            if (input) {
                input.onchange = function () {
                    self.onFileChange(input);
                };
            }

            if (this.file) {
                this.$el.find('#import-file-name').text(this.file.name);
            }

            var importButton = this.$el.find('#import-btn').get(0);

            if (importButton) {
                importButton.onclick = function () {
                    self.doImport(false);
                };
            }

            var dryRunButton = this.$el.find('#dry-run-btn').get(0);

            if (dryRunButton) {
                dryRunButton.onclick = function () {
                    self.doImport(true);
                };
            }

            var resetButton = this.$el.find('#reset-btn').get(0);

            if (resetButton) {
                resetButton.onclick = function () {
                    self.onReset();
                };
            }

            this.updateButtons();
        },

        updateButtons: function () {
            this.$el.find('#import-btn').prop('disabled', !!this.importing);
            this.$el.find('#dry-run-btn').prop('disabled', !!this.importing);
        },

        onFileChange: function (input) {
            this.file = (input && input.files && input.files[0]) || null;
            this.error = null;
            this.result = null;

            this.$el.find('#import-file-name').text(this.file ? this.file.name : '');
        },

        getFile: function () {
            var input = this.$el.find('#import-file').get(0);

            if (input && input.files && input.files[0]) {
                this.file = input.files[0];
            }

            return this.file || null;
        },

        onReset: function () {
            this.file = null;
            this.error = null;
            this.result = null;
            this.importing = false;
            this.reRender();
        },

        doImport: function (dryRun) {
            if (this.importing) {
                return;
            }

            var file = this.getFile();

            if (!file) {
                this.error = 'Select an .xlsx file first.';
                this.reRender();

                return;
            }

            this.importing = true;
            this.error = null;
            this.result = null;
            this.reRender();

            var url = 'PastDueImport' +
                '?fileName=' + encodeURIComponent(file.name) +
                '&dryRun=' + (dryRun ? '1' : '0');

            var self = this;

            Espo.Ajax.postRequest(url, null, {
                contentType: 'application/octet-stream',
                data: file,
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
