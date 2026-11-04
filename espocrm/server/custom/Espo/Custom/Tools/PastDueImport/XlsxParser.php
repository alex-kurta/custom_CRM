<?php

namespace Espo\Custom\Tools\PastDueImport;

use DOMDocument;
use DOMXPath;
use RuntimeException;
use ZipArchive;

/**
 * Minimal .xlsx reader for the past-due accounting workbook.
 *
 * Returns rows keyed by 1-based row number, with cells keyed by 0-based
 * column index. Date-formatted numeric cells are converted to Y-m-d strings;
 * all other values are returned as raw strings or null.
 */
class XlsxParser
{
    private const NS_MAIN = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main';
    private const NS_REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships';
    private const NS_PKG_REL = 'http://schemas.openxmlformats.org/package/2006/relationships';

    /**
     * @return array<int, array<int, string|null>>
     */
    public function parse(string $path): array
    {
        $zip = new ZipArchive();

        if ($zip->open($path) !== true) {
            throw new RuntimeException('Could not open the Excel file.');
        }

        try {
            $sharedStrings = $this->readSharedStrings($zip);
            $workbook = $this->readWorkbookInfo($zip);
            $styles = $this->readStyles($zip);

            $sheetXml = $zip->getFromName($workbook['sheetPath']);

            if ($sheetXml === false) {
                throw new RuntimeException('The Excel file does not contain a readable worksheet.');
            }

            return $this->parseSheet($sheetXml, $sharedStrings, $styles, $workbook['date1904']);
        } finally {
            $zip->close();
        }
    }

    /**
     * @return string[]
     */
    private function readSharedStrings(ZipArchive $zip): array
    {
        $xml = $zip->getFromName('xl/sharedStrings.xml');

        if ($xml === false) {
            return [];
        }

        $xpath = $this->createXpath($xml);
        $strings = [];

        foreach ($xpath->query('//m:sst/m:si') as $si) {
            $text = '';

            foreach ($xpath->query('.//m:t', $si) as $t) {
                $text .= $t->textContent;
            }

            $strings[] = $text;
        }

        return $strings;
    }

    /**
     * @return array{sheetPath: string, date1904: bool}
     */
    private function readWorkbookInfo(ZipArchive $zip): array
    {
        $sheetPath = 'xl/worksheets/sheet1.xml';
        $date1904 = false;

        $xml = $zip->getFromName('xl/workbook.xml');

        if ($xml === false) {
            return ['sheetPath' => $sheetPath, 'date1904' => $date1904];
        }

        $xpath = $this->createXpath($xml);

        $pr = $xpath->query('//m:workbookPr')->item(0);

        if ($pr) {
            $value = strtolower($pr->getAttribute('date1904'));
            $date1904 = $value === '1' || $value === 'true';
        }

        $activeTab = 0;
        $workbookView = $xpath->query('//m:bookViews/m:workbookView')->item(0);

        if ($workbookView) {
            $value = $workbookView->getAttribute('activeTab');

            if ($value !== '') {
                $activeTab = (int) $value;
            }
        }

        $sheets = $xpath->query('//m:sheets/m:sheet');
        $sheet = $sheets->item($activeTab) ?? $sheets->item(0);
        $relationId = null;

        if ($sheet) {
            $relationId = $sheet->getAttributeNS(self::NS_REL, 'id');

            if ($relationId === '') {
                $relationId = $sheet->getAttribute('r:id');
            }
        }

        $relsXml = $zip->getFromName('xl/_rels/workbook.xml.rels');
        $target = null;

        if ($relsXml !== false && $relationId) {
            $relsXpath = $this->createXpath($relsXml);

            foreach ($relsXpath->query('//p:Relationship') as $rel) {
                if ($rel->getAttribute('Id') === $relationId) {
                    $target = $rel->getAttribute('Target');
                    break;
                }
            }
        }

        if ($target) {
            $target = ltrim($target, '/');

            if (!str_starts_with($target, 'xl/')) {
                $target = 'xl/' . $target;
            }

            $sheetPath = $target;
        }

        return ['sheetPath' => $sheetPath, 'date1904' => $date1904];
    }

    /**
     * @return array{isDate: array<int, bool>}
     */
    private function readStyles(ZipArchive $zip): array
    {
        $xml = $zip->getFromName('xl/styles.xml');

        if ($xml === false) {
            return ['isDate' => []];
        }

        $xpath = $this->createXpath($xml);
        $numFmts = [];

        foreach ($xpath->query('//m:numFmts/m:numFmt') as $numFmt) {
            $numFmts[(int) $numFmt->getAttribute('numFmtId')] = $numFmt->getAttribute('formatCode');
        }

        $isDate = [];
        $index = 0;

        foreach ($xpath->query('//m:cellXfs/m:xf') as $xf) {
            $numFmtId = $xf->getAttribute('numFmtId');
            $numFmtId = $numFmtId === '' ? 0 : (int) $numFmtId;
            $isDate[$index++] = $this->isDateFormat($numFmtId, $numFmts);
        }

        return ['isDate' => $isDate];
    }

    /**
     * @param array<int, string> $numFmts
     */
    private function isDateFormat(int $numFmtId, array $numFmts): bool
    {
        if (
            ($numFmtId >= 14 && $numFmtId <= 22) ||
            ($numFmtId >= 27 && $numFmtId <= 36) ||
            ($numFmtId >= 45 && $numFmtId <= 47) ||
            ($numFmtId >= 50 && $numFmtId <= 58)
        ) {
            return true;
        }

        $formatCode = $numFmts[$numFmtId] ?? null;

        if ($formatCode === null) {
            return false;
        }

        $clean = preg_replace('/"[^"]*"|\[[^\]]*\]|\\./u', '', $formatCode) ?? '';

        return (bool) preg_match('/[ymdhs]/i', $clean);
    }

    /**
     * @param string[] $sharedStrings
     * @param array{isDate: array<int, bool>} $styles
     * @return array<int, array<int, string|null>>
     */
    private function parseSheet(string $xml, array $sharedStrings, array $styles, bool $date1904): array
    {
        $xpath = $this->createXpath($xml);
        $rows = [];
        $sequence = 0;

        foreach ($xpath->query('//m:sheetData/m:row') as $rowNode) {
            $sequence++;

            $rowNumber = $rowNode->getAttribute('r');
            $rowNumber = $rowNumber === '' ? $sequence : (int) $rowNumber;

            $cells = [];

            foreach ($xpath->query('m:c', $rowNode) as $cellNode) {
                $columnIndex = $this->columnIndex($cellNode->getAttribute('r'));

                if ($columnIndex === null) {
                    continue;
                }

                $cells[$columnIndex] = $this->readCell(
                    $cellNode,
                    $xpath,
                    $sharedStrings,
                    $styles,
                    $date1904
                );
            }

            $rows[$rowNumber] = $cells;
        }

        ksort($rows);

        return $rows;
    }

    /**
     * @param string[] $sharedStrings
     * @param array{isDate: array<int, bool>} $styles
     */
    private function readCell(
        \DOMElement $cellNode,
        DOMXPath $xpath,
        array $sharedStrings,
        array $styles,
        bool $date1904
    ): ?string {
        $type = $cellNode->getAttribute('t');
        $valueNode = $xpath->query('m:v', $cellNode)->item(0);
        $raw = $valueNode?->textContent;

        if ($type === 's') {
            return $sharedStrings[(int) $raw] ?? '';
        }

        if ($type === 'inlineStr') {
            $text = '';

            foreach ($xpath->query('.//m:t', $cellNode) as $t) {
                $text .= $t->textContent;
            }

            return $text;
        }

        if ($type === 'str') {
            return $raw;
        }

        if ($type === 'b') {
            return $raw === '1' ? '1' : '0';
        }

        if ($raw === null) {
            return null;
        }

        $styleIndex = $cellNode->getAttribute('s');
        $styleIndex = $styleIndex === '' ? null : (int) $styleIndex;

        if (
            $styleIndex !== null &&
            ($styles['isDate'][$styleIndex] ?? false) &&
            is_numeric($raw)
        ) {
            return $this->excelSerialToDate((float) $raw, $date1904);
        }

        return $raw;
    }

    private function excelSerialToDate(float $serial, bool $date1904): string
    {
        $base = $date1904 ? '1904-01-01' : '1899-12-30';
        $days = (int) floor($serial);

        $date = new \DateTimeImmutable($base, new \DateTimeZone('UTC'));
        $date = $date->modify(($days >= 0 ? '+' : '') . $days . ' days');

        return $date->format('Y-m-d');
    }

    private function columnIndex(string $reference): ?int
    {
        if (!preg_match('/^([A-Za-z]+)/', $reference, $matches)) {
            return null;
        }

        $letters = strtoupper($matches[1]);
        $index = 0;

        for ($i = 0; $i < strlen($letters); $i++) {
            $index = $index * 26 + (ord($letters[$i]) - 64);
        }

        return $index - 1;
    }

    private function createXpath(string $xml): DOMXPath
    {
        $document = new DOMDocument();

        if (!@$document->loadXML($xml, LIBXML_NONET)) {
            throw new RuntimeException('The Excel file contains invalid XML.');
        }

        $xpath = new DOMXPath($document);
        $xpath->registerNamespace('m', self::NS_MAIN);
        $xpath->registerNamespace('p', self::NS_PKG_REL);

        return $xpath;
    }
}
