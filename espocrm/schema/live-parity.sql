-- Supplemental EspoCRM schema for exact parity with the current live system.
--
-- Normal EspoCRM rebuild should create the tracked custom entities and fields from
-- metadata. This file preserves live-only legacy columns that are present on the
-- running system but are not fully derivable from the tracked metadata alone.
--
-- Apply this after a normal rebuild. Do not rely on `rebuild --hard` if exact
-- live-schema parity is required, as hard rebuild can remove unused columns.

ALTER TABLE `account`
    ADD COLUMN IF NOT EXISTS `c_c_order_count` int(11) DEFAULT NULL AFTER `c_fishbowl_last_modified`,
    ADD COLUMN IF NOT EXISTS `c_past_due_date` date DEFAULT NULL AFTER `c_past_due_amount`,
    ADD COLUMN IF NOT EXISTS `cDaysOverdue` int(11) DEFAULT 0 AFTER `c_past_due_amount_currency`;

ALTER TABLE `account`
    MODIFY COLUMN `c_c_order_count` int(11) DEFAULT NULL AFTER `c_fishbowl_last_modified`,
    MODIFY COLUMN `c_past_due_date` date DEFAULT NULL AFTER `c_past_due_amount`,
    MODIFY COLUMN `cDaysOverdue` int(11) DEFAULT 0 AFTER `c_past_due_amount_currency`;
