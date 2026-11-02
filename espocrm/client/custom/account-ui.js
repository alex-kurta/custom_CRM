(function () {
    var CSS_ID = 'account-ui-css';
    if (document.getElementById(CSS_ID)) return;
    var s = document.createElement('style');
    s.id = CSS_ID;
    s.textContent =
        // Hide "Remove" from dropdown menus
        'body>#content>#main>.list-container>.list-buttons-container .dropdown-menu li a[data-action="remove"] { display: none !important; }' +
        'body>#content>#main>.list-container>.list-buttons-container .dropdown-menu li a[data-action="quickRemove"] { display: none !important; }' +
        'body>#content>#main>.list-container>.list-buttons-container .dropdown-menu li a[data-action="delete"] { display: none !important; }' +
        'body>#content>#main>.list-container>.list.has-show-more .list-row-dropdown-menu li a[data-action="quickRemove"] { display: none !important; }' +
        // Account detail: hide tabs in bottom panels
        '.detail .record-grid .left .bottom > .tabs.btn-group:not(.middle-tabs) { display: none !important; }' +
        // Sales order rows: pointer cursor
        '.panel[data-name="cSalesOrders"] .list-row { cursor: pointer !important; }' +
        // Hide thead in cSalesOrders
        '.panel-body[data-name="cSalesOrders"] .list[data-scope="CSalesOrder"] > table > thead { display: none !important; }' +
        // Match panel-heading vertical spacing to sales order row height, align left with panels above
        '.panel.panel-cSalesOrders .panel-heading { padding: 6px var(--10px, 10px) !important; min-height: 0 !important; }' +
        // Hide square icon in panel title action, remove pointer cursor
        '.panel-title > .action .color-icon.fas.fa-square { display: none !important; }' +
        '.panel-title > .action .color-icon.fas.fa-square + span { display: none !important; }' +
        'span.action { cursor: default !important; }' +
        // Date filter popover styling
        '.date-filter-popover .form-control:focus { border-color: var(--brand-primary, #3088de) !important; box-shadow: 0 0 0 2px rgba(48,136,222,0.15) !important; }' +
        '.date-filter-popover .btn-primary { background: var(--brand-primary, #3088de) !important; border-color: var(--brand-primary, #3088de) !important; color: #fff !important; }' +
        '.date-filter-popover .btn-primary:hover { background: var(--brand-primary-hover, #2070c0) !important; }' +
        // Hidden rows during date filter
        '.panel[data-name="cSalesOrders"] .list-row.hidden { display: none !important; }';
    document.head.appendChild(s);
})();
