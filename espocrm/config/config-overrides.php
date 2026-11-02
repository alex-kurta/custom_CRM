<?php
/**
 * EspoCRM config overrides — custom keys ONLY (no secrets).
 *
 * Merge these keys into /var/www/espocrm/data/espocrm/persistent/data/config.php
 * (the live file also contains DB credentials — never commit it).
 *
 * deploy.sh inserts missing keys automatically; on EspoCRM upgrades the
 * installer may rewrite config.php — re-merge this file afterwards.
 */
return [
    // Allow the 4 custom client JS files to load (script-src 'unsafe-inline' etc.)
    'clientCspDisabled' => true,

    // List page size for small lists (cSalesOrders panel uses 200)
    'recordsPerPageSmall' => 200,

    // Raise EspoCRM default of 5 email accounts per user
    'maxEmailAccountCount' => 10,

    // Public URL of this instance
    'siteUrl' => 'https://crm.example.com',
];
