<style>

.panel[data-name="cSalesOrders"] .detail-row table thead,
.panel[data-name="cSalesOrders"] .sales-items table thead,

.panel[data-name="cSalesOrders"] .detail-row th,
.panel[data-name="cSalesOrders"] .sales-items th {display:table-cell !important; visibility:visible !important;}
.panel[data-name="cSalesOrders"] .show-more{display:none !important;}
.panel[data-name="cSalesOrders"] .list-pagination{display:none !important;}
.list[data-scope="CSalesOrder"] .show-more{display:none !important;}
div[data-name="cSalesOrders"] .show-more{display:none !important;}
tr.list-row {cursor:pointer;}
tr.detail-row.hidden {display:none;}
tr.detail-row td {background:var(--panel-bg, #fff);}
div.list-row, li.list-row, tr.list-row {cursor:pointer;}
div.detail-row.hidden, li.detail-row.hidden, tr.detail-row.hidden {display:none;}
tr.list-row:hover, div.list-row:hover, li.list-row:hover {cursor:pointer !important; background:var(--table-bg-accent, #f5f5f5) !important;}
div.detail-row, li.detail-row {background:var(--panel-bg, #fff); border-top:1px solid var(--panel-default-border, #ddd);}
.panel[data-name="cSalesOrders"] [data-name="buttons"],
.panel[data-name="cSalesOrders"] .cell[data-name="buttons"],
.list[data-scope="CSalesOrder"] [data-name="buttons"] {display:none !important; width:0 !important; padding:0 !important; border:0 !important;}
.detail-row.list-group-item {padding-top:0 !important; padding-bottom:0 !important; border-top:0 !important;}
.detail-row.list-group-item .detail-content {padding-top:4px !important; padding-bottom:4px !important;}

.product-name-cell, .product-name-wrapper {scrollbar-width:none; -ms-overflow-style:none; overflow-x:auto;}
.product-name-cell::-webkit-scrollbar, .product-name-wrapper::-webkit-scrollbar {display:none; width:0; height:0;}
.product-name-wrapper:hover, .product-name-cell:hover {scrollbar-width:thin; overflow-x:auto;}
.product-name-wrapper:hover::-webkit-scrollbar, .product-name-cell:hover::-webkit-scrollbar {display:block; height:4px; width:4px;}
.product-name-wrapper {display:flex; align-items:center; min-height:24px;}
td[data-name="product"] {vertical-align:middle !important;}
.sales-items td {vertical-align:middle !important;}


.list-row.hidden, tr.list-row.hidden, div.list-row.hidden, li.list-row.hidden {display:none !important;}
.detail-row.hidden {display:none !important;}

/* Hide teams field in Account detail/edit only */
[data-scope="Account"] .cell[data-name="teams"] {visibility:hidden !important;}

/* master thead removed, ensure top matches bottom rounding */



/* 1. extend th:first-child padding to all th for product table */
.panel[data-name="cSalesOrders"] .detail-row .sales-items th,
.panel[data-name="cSalesOrders"] .detail-row .sales-items td,
.panel[data-name="cSalesOrders"] .sales-items table th,
.panel[data-name="cSalesOrders"] .sales-items table td {padding-left: 15px !important; padding-right: 15px !important; padding-top: 8px !important; padding-bottom: 8px !important;}
/* override first/last child padding that was causing mismatch */
.panel[data-name="cSalesOrders"] .sales-items th:first-child,
.panel[data-name="cSalesOrders"] .sales-items td:first-child,
.panel[data-name="cSalesOrders"] .sales-items th:last-child,
.panel[data-name="cSalesOrders"] .sales-items td:last-child {padding-left: 15px !important; padding-right: 15px !important;}


/* ensure both main and nested tables have top and bottom rounding */

/* for the main cSalesOrders list, ensure the first row after hidden thead also has top rounding */
/* remove border-top from first visible row, keep on subsequent visible rows */
.panel[data-name="cSalesOrders"] .list-row:not(.hidden) > td{border-top:0 !important;}
.panel[data-name="cSalesOrders"] .list-row:not(.hidden) ~ .list-row:not(.hidden) > td{border-top:1px solid var(--panel-default-border, #ddd) !important;}


/* fix top rounding to match bottom - div.list has bottom radius, add top */
.panel[data-name="cSalesOrders"] > .panel-body > .list[data-scope="CSalesOrder"],
.panel[data-name="cSalesOrders"] div.list[data-scope="CSalesOrder"] {border-top-left-radius: var(--panel-border-radius, 4px) !important; border-top-right-radius: var(--panel-border-radius, 4px) !important; overflow:hidden !important;}


.panel[data-name="cSalesOrders"] > .panel-body > .list-container > .list > table > thead{display:none !important;}
.panel[data-name="cSalesOrders"] > .panel-body > .list-container > .list > table > tbody > .detail-row > td > .detail-content > .sales-items > table > thead{display:table-header-group !important; visibility:visible !important; height:auto !important; overflow:visible !important; padding:8px 15px !important;}

/* fix .list  with spaces - handle both "list" and "list  " */
.panel[data-name="cSalesOrders"] > .panel-body > .list-container > div[class*="list"] > table > thead{display:none !important;}


/* Past Due yellow highlight in list view */
.list-row[data-record-id][data-record-params] {
    position: relative;
}
.past-due-highlight {
    background-color: #fff3cd !important;
}
.past-due-highlight:hover {
    background-color: #ffc107 !important;
}

/* Past Due panel styling */
.past-due-panel .table {
    margin-bottom: 0;
}
.past-due-panel .past-due-summary {
    padding: 8px 0;
    text-align: right;
    border-top: 1px solid var(--panel-default-border, #ddd);
}
.past-due-panel .text-muted {
    padding: 8px 0;
}
</style>
{{#each panelList}}
    {{#if isRightAfterDelimiter}}
        <div class="panels-show-more-delimiter">
            <a role="button" tabindex="0" data-action="showMorePanels" title="{{translate 'Show more'}}">
                <span class="fas fa-ellipsis-h fa-lg"></span>
            </a>
        </div>
    {{/if}}
    {{#if isTabsBeginning}}
    <div class="tabs btn-group">
        {{#each ../tabDataList}}
        <button
            class="btn btn-text btn-wide{{#if isActive}} active{{/if}}{{#if hidden}} hidden{{/if}}"
            data-tab="{{@key}}"
        >{{label}}</button>
        {{/each}}
    </div>
    {{/if}}
    <div
        class="panel panel-{{#if style}}{{style}}{{else}}default{{/if}} panel-{{name}} headered{{#if hidden}} hidden{{/if}}{{#if sticked}} sticked{{/if}}{{#if tabHidden}} tab-hidden{{/if}}"
        data-name="{{name}}"
        data-style="{{#if style}}{{style}}{{/if}}"
        data-tab="{{tabNumber}}"
    >
        {{#if title}}
        <div class="panel-heading">
            <div class="pull-right btn-group panel-actions-container">{{{var actionsViewKey ../this}}}</div>
            <h4 class="panel-title">
            {{#unless notRefreshable}}
            <span
                style="cursor: pointer; user-select: none;"
                class="action"
                title="{{translate 'clickToRefresh' category='messages'}}"
                data-action="refresh"
                data-panel="{{name}}"
            >
            {{/unless}}
            {{#if titleHtml}}
                {{{titleHtml}}}
            {{else}}
                {{title}}
            {{/if}}
            {{#unless notRefreshable}}
            </span>
            {{/unless}}
            </h4>
        </div>
        {{/if}}
        <div class="panel-body{{#if isForm}} panel-body-form{{/if}}" data-name="{{name}}">
            {{{var name ../this}}}
        </div>
    </div>
{{/each}}