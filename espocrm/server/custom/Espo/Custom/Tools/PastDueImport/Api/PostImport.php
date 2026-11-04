<?php

namespace Espo\Custom\Tools\PastDueImport\Api;

use Espo\Core\Acl;
use Espo\Core\Api\Action;
use Espo\Core\Api\Request;
use Espo\Core\Api\Response;
use Espo\Core\Api\ResponseComposer;
use Espo\Core\Exceptions\BadRequest;
use Espo\Core\Exceptions\Forbidden;
use Espo\Custom\Tools\PastDueImport\ImportService;

/**
 * Handles POST /api/v1/PastDueImport.
 *
 * The raw request body is the .xlsx file. Query params:
 * - fileName: original file name (used for the report date)
 * - dryRun: "1" to preview without writes
 */
class PostImport implements Action
{
    public function __construct(
        private Acl $acl,
        private ImportService $importService,
    ) {}

    public function process(Request $request): Response
    {
        if (
            !$this->acl->checkScope('Account', 'edit') ||
            !$this->acl->checkScope('CSalesOrder', 'read')
        ) {
            throw new Forbidden();
        }

        $contents = $request->getBodyContents();

        if ($contents === null || $contents === '') {
            throw new BadRequest('The uploaded file is empty.');
        }

        $fileName = $request->getQueryParam('fileName') ?? 'past-due.xlsx';
        $dryRun = $request->getQueryParam('dryRun') === '1';

        return ResponseComposer::json(
            $this->importService->run($contents, $fileName, $dryRun)
        );
    }
}
