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

    // Left navigation tabs. Replaces the default core "Import" tab with a
    // dedicated Past Due Import tab right below Calendar. deploy.sh overwrites
    // this key on purpose (see merge-config.php overwrite list).
    'tabList' => [
        ['type' => 'divider', 'id' => '342567', 'text' => '$CRM'],
        'Account',
        ['type' => 'divider', 'text' => '$Activities', 'id' => '219419'],
        'Email',
        'Meeting',
        'Call',
        'Task',
        'Calendar',
        [
            'type' => 'url',
            'url' => '#PastDueImport',
            'text' => 'Past Due Import',
            'iconClass' => 'fas fa-file-import',
            'onlyAdmin' => true,
        ],
        ['type' => 'divider', 'text' => null, 'id' => '137994'],
        '_delimiter_',
        ['type' => 'divider', 'text' => '$Marketing', 'id' => '463280'],
        'Campaign',
        'TargetList',
        ['type' => 'divider', 'text' => '$Organization', 'id' => '566592'],
        'User',
        ['type' => 'divider', 'text' => null, 'id' => '898671'],
        'EmailTemplate',
        'Template',
    ],
];
