<?php

namespace Espo\Custom\Tools\PastDueImport;

use DateTimeImmutable;
use DateTimeZone;
use Espo\Core\Exceptions\BadRequest;
use Espo\Core\Record\ServiceContainer;
use Espo\ORM\EntityManager;
use Throwable;

/**
 * Imports a past-due invoice workbook and updates Account past-due fields.
 *
 * Port of src/past_due_import.py. Column layout:
 * B customer, C SO #, D order date, E due date, F aging, G amount, H balance.
 */
class ImportService
{
    private const MONTHS = [
        'jan' => 1,
        'feb' => 2,
        'mar' => 3,
        'apr' => 4,
        'may' => 5,
        'jun' => 6,
        'jul' => 7,
        'aug' => 8,
        'sep' => 9,
        'oct' => 10,
        'nov' => 11,
        'dec' => 12,
    ];

    private const DATE_PATTERNS = [
        '/\b(\d{1,2})\s*(?:st|nd|rd|th)?\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s*,?\s*(\d{4})\b/i',
        '/\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,2})\s*(?:st|nd|rd|th)?\s*,?\s*(\d{4})\b/i',
        '/\b(\d{1,2})-(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?[- ](\d{4})\b/i',
        '/\b(\d{1,2})\/(\d{1,2})\/(\d{4})\b/',
        '/\b(\d{4})-(\d{1,2})-(\d{1,2})\b/',
    ];

    /** @var array<string, ?string> */
    private array $accountNameCache = [];

    public function __construct(
        private EntityManager $entityManager,
        private ServiceContainer $serviceContainer,
        private XlsxParser $xlsxParser,
    ) {}

    /**
     * @return array<string, mixed>
     */
    public function run(string $contents, string $fileName, bool $dryRun): array
    {
        $records = $this->parseContents($contents);

        $filenameDate = $this->parseFilenameDate($fileName);

        $timezone = new DateTimeZone('America/Los_Angeles');
        $today = new DateTimeImmutable('today', $timezone);

        if ($filenameDate === null) {
            $filenameDate = $today->format('Y-m-d');
        }

        $fileDate = DateTimeImmutable::createFromFormat('!Y-m-d', $filenameDate, $timezone);

        if ($fileDate === false) {
            throw new BadRequest('Could not determine the report date.');
        }

        $daysSinceFile = (int) $fileDate->diff($today)->format('%r%a');

        $salesOrderAccountMap = $this->loadSalesOrderAccountMap($records);

        /** @var array<string, list<array<string, mixed>>> $ordersByAccount */
        $ordersByAccount = [];
        $unmatched = [];

        foreach ($records as $record) {
            $accountId = null;

            if ($record['so_num'] !== '' && isset($salesOrderAccountMap[$record['so_num']])) {
                $accountId = $salesOrderAccountMap[$record['so_num']];
            }

            if (!$accountId && $record['customer'] !== '') {
                $accountId = $this->lookupAccountByName($record['customer']);
            }

            if ($accountId) {
                $ordersByAccount[$accountId][] = $record;
            } else {
                $unmatched[] = $record;
            }
        }

        $cleared = $this->clearPastDue($dryRun);

        $updated = 0;
        $failed = 0;

        foreach ($ordersByAccount as $accountId => $orders) {
            $payload = $this->buildAccountPayload($orders, $daysSinceFile);

            if ($dryRun) {
                $updated++;
                continue;
            }

            try {
                $this->serviceContainer->get('Account')->update($accountId, (object) $payload);
                $updated++;
            } catch (Throwable) {
                $failed++;
            }
        }

        return [
            'ordersImported' => count($records),
            'accountsUpdated' => $updated,
            'failed' => $failed,
            'unmatched' => count($unmatched),
            'unmatchedOrders' => array_map(
                fn (array $record): string => 'SO#' . $record['so_num'] . ' — ' . $record['customer'],
                array_slice($unmatched, 0, 10)
            ),
            'cleared' => $cleared,
            'filenameDate' => $filenameDate,
            'daysElapsed' => $daysSinceFile,
            'dryRun' => $dryRun,
        ];
    }

    /**
     * @return list<array<string, mixed>>
     */
    private function parseContents(string $contents): array
    {
        $path = tempnam(sys_get_temp_dir(), 'pastdue-');

        if ($path === false) {
            throw new BadRequest('Could not create a temporary file.');
        }

        try {
            if (file_put_contents($path, $contents) === false) {
                throw new BadRequest('Could not write the uploaded file.');
            }

            $rows = $this->xlsxParser->parse($path);
        } catch (BadRequest $e) {
            throw $e;
        } catch (Throwable $e) {
            throw new BadRequest('Could not parse the Excel file: ' . $e->getMessage());
        } finally {
            @unlink($path);
        }

        $records = [];

        foreach ($rows as $rowNumber => $cells) {
            if ($rowNumber < 3) {
                continue;
            }

            $customer = $this->stringValue($cells[1] ?? null);
            $soNum = $this->stringValue($cells[2] ?? null);

            if ($customer === '' && $soNum === '') {
                continue;
            }

            $records[] = [
                'customer' => $customer,
                'so_num' => $soNum,
                'order_date' => $this->stringValue($cells[3] ?? null),
                'due_date' => $this->stringValue($cells[4] ?? null),
                'aging' => $this->intValue($cells[5] ?? null),
                'amount' => $this->floatValue($cells[6] ?? null),
                'balance' => $this->floatValue($cells[7] ?? null),
            ];
        }

        return $records;
    }

    /**
     * @param list<array<string, mixed>> $records
     * @return array<string, string>
     */
    private function loadSalesOrderAccountMap(array $records): array
    {
        $soNumbers = [];

        foreach ($records as $record) {
            if ($record['so_num'] !== '') {
                $soNumbers[$record['so_num']] = true;
            }
        }

        $soNumbers = array_keys($soNumbers);

        if ($soNumbers === []) {
            return [];
        }

        $map = [];

        foreach (array_chunk($soNumbers, 500) as $chunk) {
            $orders = $this->entityManager
                ->getRepository('CSalesOrder')
                ->where(['fishbowlNum' => $chunk])
                ->find();

            foreach ($orders as $order) {
                $accountId = $order->get('accountId');

                if ($accountId) {
                    $map[(string) $order->get('fishbowlNum')] = $accountId;
                }
            }
        }

        return $map;
    }

    private function lookupAccountByName(string $name): ?string
    {
        if (array_key_exists($name, $this->accountNameCache)) {
            return $this->accountNameCache[$name];
        }

        $accounts = $this->entityManager
            ->getRepository('Account')
            ->where(['name*' => '%' . $name . '%'])
            ->limit(0, 5)
            ->find();

        $accountId = null;

        foreach ($accounts as $account) {
            if (strcasecmp((string) $account->get('name'), $name) === 0) {
                $accountId = $account->getId();
                break;
            }
        }

        if (!$accountId && count($accounts)) {
            $accountId = $accounts[0]->getId();
        }

        return $this->accountNameCache[$name] = $accountId;
    }

    private function clearPastDue(bool $dryRun): int
    {
        $accounts = $this->entityManager
            ->getRepository('Account')
            ->where(['cPastDue' => true])
            ->find();

        $cleared = 0;

        foreach ($accounts as $account) {
            if ($dryRun) {
                $cleared++;
                continue;
            }

            try {
                $this->serviceContainer->get('Account')->update($account->getId(), (object) [
                    'cPastDue' => false,
                    'cPastDueData' => null,
                    'cPastDueAmount' => null,
                    'cDaysOverdue' => 0,
                ]);

                $cleared++;
            } catch (Throwable) {
                // Match the Python behavior: skip failures silently.
            }
        }

        return $cleared;
    }

    /**
     * @param list<array<string, mixed>> $orders
     * @return array<string, mixed>
     */
    private function buildAccountPayload(array $orders, int $daysSinceFile): array
    {
        $totalBalance = 0.0;
        $maxAging = 0;

        foreach ($orders as $order) {
            $totalBalance += $order['balance'];

            if ($order['aging'] > $maxAging) {
                $maxAging = $order['aging'];
            }
        }

        return [
            'cPastDue' => true,
            'cDaysOverdue' => $maxAging + $daysSinceFile,
            'cPastDueAmount' => round($totalBalance, 2),
            'cPastDueAmountCurrency' => 'USD',
            'cPastDueData' => json_encode($orders),
        ];
    }

    private function parseFilenameDate(string $fileName): ?string
    {
        if ($fileName === '') {
            return null;
        }

        foreach (self::DATE_PATTERNS as $pattern) {
            if (!preg_match($pattern, $fileName, $matches)) {
                continue;
            }

            $first = $matches[1];
            $second = $matches[2];
            $third = $matches[3];

            if (ctype_alpha($first) || ctype_alpha($second)) {
                if (ctype_alpha($first)) {
                    $month = self::MONTHS[strtolower(substr($first, 0, 3))] ?? null;
                    $day = (int) $second;
                    $year = (int) $third;
                } else {
                    $day = (int) $first;
                    $month = self::MONTHS[strtolower(substr($second, 0, 3))] ?? null;
                    $year = (int) $third;
                }
            } else {
                $a = (int) $first;
                $b = (int) $second;
                $c = (int) $third;

                if ($a > 31) {
                    $year = $a;
                    $month = $b;
                    $day = $c;
                } else {
                    $month = $a;
                    $day = $b;
                    $year = $c;
                }
            }

            if ($month !== null && checkdate($month, $day, $year)) {
                return sprintf('%04d-%02d-%02d', $year, $month, $day);
            }
        }

        return null;
    }

    private function stringValue(mixed $value): string
    {
        if ($value === null) {
            return '';
        }

        if (is_float($value) && floor($value) === $value) {
            return (string) (int) $value;
        }

        return trim((string) $value);
    }

    private function intValue(mixed $value): int
    {
        $value = $this->stringValue($value);

        if ($value === '' || !is_numeric($value)) {
            return 0;
        }

        return (int) (float) $value;
    }

    private function floatValue(mixed $value): float
    {
        $value = $this->stringValue($value);

        if ($value === '' || !is_numeric($value)) {
            return 0.0;
        }

        return (float) $value;
    }
}
