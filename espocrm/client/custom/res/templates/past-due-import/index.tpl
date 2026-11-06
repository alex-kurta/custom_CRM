<div class="past-due-import-container">
    <h3>Past Due Import</h3>
    <p class="text-muted">
        Upload the accounting past-due Excel file (.xlsx). The report date is read
        from the file name, e.g. "past-due-invoices.xlsx".
    </p>

    {{#if error}}
    <div class="alert alert-danger">{{error}}</div>
    {{/if}}

    {{#if result}}
    <div class="alert alert-success">
        <strong>{{#if result.dryRun}}Dry Run Complete{{else}}Import Complete{{/if}}</strong><br>
        Orders parsed: {{result.ordersImported}}<br>
        Accounts {{#if result.dryRun}}matched{{else}}updated{{/if}}: {{result.accountsUpdated}}<br>
        Unmatched orders: {{result.unmatched}}<br>
        Past-due flags cleared: {{result.cleared}}<br>
        {{#if result.failed}}Failed: {{result.failed}}<br>{{/if}}
        Report date: {{result.filenameDate}} ({{result.daysElapsed}} days elapsed)

        {{#if result.unmatchedOrders.length}}
        <div class="small" style="margin-top: 10px;">
            <strong>Unmatched (first 10):</strong>
            <ul>
                {{#each result.unmatchedOrders}}
                <li>{{this}}</li>
                {{/each}}
            </ul>
        </div>
        {{/if}}
    </div>

    <button class="btn btn-default" id="reset-btn">
        <span class="fas fa-upload"></span> Import another file
    </button>
    {{/if}}

    {{#unless result}}
    <div class="import-form" style="margin-top: 20px;">
        <div class="form-group">
            <label for="import-file">Select Excel File (.xlsx)</label>
            <input type="file" id="import-file" accept=".xlsx" class="form-control">
            <div id="import-file-name" class="text-muted small" style="margin-top: 5px;">{{fileName}}</div>
        </div>
        <div class="form-group" style="margin-top: 15px;">
            <button class="btn btn-primary" id="import-btn">
                <span class="fas fa-upload"></span> Import
            </button>
            <button class="btn btn-default" id="dry-run-btn">
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
