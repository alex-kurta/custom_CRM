<div class="past-due-import-container">
    <h3>Past Due Import</h3>
    <p class="text-muted">Upload an Excel file (.xlsx) of past-due invoices from accounting.</p>

    {{#if error}}
    <div class="alert alert-danger">{{error}}</div>
    {{/if}}

    {{#if result}}
    <div class="alert alert-success">
        <strong>Import Complete!</strong><br>
        Orders imported: {{result.ordersImported}}<br>
        Accounts updated: {{result.accountsUpdated}}<br>
        Unmatched orders: {{result.unmatched}}
    </div>
    {{/if}}

    {{#unless result}}
    <div class="import-form" style="margin-top: 20px;">
        <div class="form-group">
            <label for="import-file">Select Excel File (.xlsx)</label>
            <input type="file" id="import-file" accept=".xlsx" class="form-control">
        </div>
        <div class="form-group" style="margin-top: 15px;">
            <button class="btn btn-primary" id="import-btn" disabled>
                <span class="fas fa-upload"></span> Import
            </button>
            <button class="btn btn-default" id="dry-run-btn" disabled>
                <span class="fas fa-eye"></span> Dry Run
            </button>
        </div>
        {{#if importing}}
        <div class="progress" style="margin-top: 15px;">
            <div class="progress-bar progress-bar-striped active" style="width: 100%">
                Importing...
            </div>
        </div>
        {{/if}}
    </div>
    {{/unless}}
</div>