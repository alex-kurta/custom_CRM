# Fishbowl + EspoCRM Monorepo

This repository has two jobs:

1. `src/` and related Python code handle the Fishbowl -> EspoCRM import, sync, categorization, ranking, and reminders.
2. `espocrm/` captures the live EspoCRM custom layer so someone can start from a vanilla EspoCRM Docker install and patch it to the same behavior.

This repo does not contain live CRM data, database dumps, or secrets. It contains code, metadata, templates, and deployment helpers.

## Repository layout

```text
src/                      Fishbowl -> EspoCRM integration code
scripts/                  one-off helper scripts
espocrm/
  server/custom/          contents of persistent/custom/
  client/custom/          contents of persistent/custom-client/
  patches/                patched ClientManager.php + minimal diff
  config/                 sanitized compose/config/nginx snippets
  schema/                 supplemental SQL for exact live-schema parity
  cron/                   optional follow-up reminder cron entry
  scripts/                repo -> live deploy and live -> repo export
```

For EspoCRM UI and metadata changes, the source of truth is the repo copy under `espocrm/`. Do not keep ad hoc working copies in `/path/to/project`; deploy from the repo tree and export back into the repo if the live CRM was changed directly.

## What You Can Rebuild From This Repo

Starting from a vanilla Docker-based EspoCRM install, this repo can restore:

- server-side custom metadata under `custom/`
- client-side custom JS/templates under `custom-client/`
- the `ClientManager.php` modification that loads the 4 custom client scripts
- safe non-secret config keys like `recordsPerPageSmall` and `maxEmailAccountCount`
- the left navigation `tabList` (including the Past Due Import tab below Calendar)
- the in-app Past Due Import page and its `POST /api/v1/PastDueImport` upload endpoint
- supplemental SQL needed to match the current live custom schema exactly
- the nginx upload-size tweak
- the optional follow-up reminder cron entry

This repo does not restore:

- the live EspoCRM database contents
- users, accounts, contacts, orders, or attachments
- secret values from `.env`, `config.php`, or the real `docker-compose.yml`

## Rebuild A Vanilla EspoCRM Docker Install To Match This Repo

These instructions assume Ubuntu/Linux and the same deployment layout used on the live host: `/var/www/espocrm` with containers named `espocrm`, `espocrm-db`, and `espocrm-nginx`.

### Prerequisites

- Docker with the Compose plugin (`docker compose`)
- `rsync`
- shell access to the Docker host
- permission to write under `/var/www/espocrm`

The deployment scripts in `espocrm/scripts/` assume those exact paths and container names. If you use a different layout, adjust `espocrm/scripts/deploy.sh` first.

### 1. Clone this repo

```bash
git clone <your-remote-url>
cd <repo-directory>
```

### 2. Bring up a vanilla EspoCRM Docker stack

Use `espocrm/config/docker-compose.yml.example` as the starting point.

```bash
sudo mkdir -p /var/www/espocrm
sudo cp espocrm/config/docker-compose.yml.example /var/www/espocrm/docker-compose.yml
# edit placeholders in /var/www/espocrm/docker-compose.yml
cd /var/www/espocrm
docker compose up -d
```

Wait for the containers to become healthy before patching.

```bash
docker ps
```

Notes:

- The compose file already includes the `persistent/custom` and `persistent/custom-client` bind mounts that this repo deploys into.
- `espocrm/config/nginx-snippet.conf` is a local tweak for large uploads. Add it to `/var/www/espocrm/data/nginx/espocrm.conf` if your vanilla install does not already contain `client_max_body_size 50M;`.
- The compose example is sanitized. You must fill in all `CHANGE_ME_*` values before startup.

### 3. Patch the vanilla instance with this repo

From the repo root:

```bash
./espocrm/scripts/deploy.sh
```

What `deploy.sh` does:

- syncs `espocrm/server/custom/` into `/var/www/espocrm/data/espocrm/persistent/custom/`
- syncs `espocrm/client/custom/` into `/var/www/espocrm/data/espocrm/persistent/custom-client/`
- replaces `ClientManager.php` inside the running `espocrm` container so the 4 custom client scripts load
- merges the safe keys from `espocrm/config/config-overrides.php` into `data/config.php` (and overwrites `tabList` so the sidebar matches the repo)
- bumps `appTimestamp` in `state.php`
- runs `php command.php rebuild`
- applies `espocrm/schema/live-parity.sql` for exact live-schema parity
- restarts the `espocrm` container to clear opcode cache
- verifies schema parity with `espocrm/scripts/verify-schema.sh`

After that, hard-refresh the browser.

### 4. Verify the patch

Minimum checks:

```bash
docker exec espocrm grep -q 'past-due-highlight.js' /var/www/html/application/Espo/Core/Utils/ClientManager.php
docker exec espocrm php -l /var/www/html/data/config.php
docker exec espocrm php -l /var/www/html/data/state.php
./espocrm/scripts/verify-schema.sh
```

UI checks:

- Account list row highlighting is active
- custom Sales Order panel renders on Account detail
- custom fields such as `cCategory`, `cPrePay`, and `cComments` exist
- removed sidebar items stay removed
- the `Past Due Import` tab is present below Calendar and its Dry Run returns a count

## Cold-Start Recovery Summary

If someone downloads this repo onto a fresh host, the shortest path is:

1. Clone the repo.
2. Copy `espocrm/config/docker-compose.yml.example` to `/var/www/espocrm/docker-compose.yml` and fill the placeholders.
3. Run `docker compose up -d` in `/var/www/espocrm`.
4. Add the nginx `client_max_body_size 50M;` tweak if missing.
5. Run `./espocrm/scripts/deploy.sh` from the repo root.
6. Run `./espocrm/scripts/verify-schema.sh`.
7. Log into EspoCRM and verify the custom UI and fields are present.

That gets a vanilla Docker install patched to the current custom code state captured here.

## Persistence, Backups & Power-Loss Recovery

Live state lives on the host filesystem under `/var/www/espocrm/data` (bind mounts), not inside containers:

| Path | Contents |
|---|---|
| `data/mariadb/data` | MariaDB data directory |
| `data/espocrm/persistent/data` | EspoCRM `data/` (config.php, state.php, uploads) |
| `data/espocrm/persistent/custom` | deployed server-side custom code |
| `data/espocrm/persistent/custom-client` | deployed client-side custom code |
| `data/nginx` | nginx configs and logs |

All services use `restart: always`, and Docker is enabled at boot, so a reboot or power loss restarts the stack automatically. MariaDB runs with `innodb_flush_log_at_trx_commit=1`, so committed transactions survive an unclean shutdown.

Two changes live in the container layer, not on a bind mount: the `ClientManager.php` patch and the php-fpm `pm.max_children` tuning. `espocrm/scripts/restore-container-config.sh` re-applies both and is installed in cron every 10 minutes, so a recreated container heals itself without a manual deploy.

Backups run daily at 02:30 via `espocrm/scripts/backup.sh` (installed by `espocrm/cron/crontab.txt`):

- `/var/www/espocrm-backup/sql/db-<timestamp>.sql.gz` — consistent `mariadb-dump --single-transaction` of all databases (kept 30 days)
- `/var/www/espocrm-backup/<timestamp>.tar.gz` — full `/var/www/espocrm` archive via `command.sh backup` (kept 14 days)

Restore the logical database dump into the running DB container:

```bash
gunzip -c /var/www/espocrm-backup/sql/db-<timestamp>.sql.gz \
  | docker exec -i espocrm-db sh -lc 'exec mariadb -uroot -p"$MARIADB_ROOT_PASSWORD"'
```

Restore the full application archive:

```bash
/var/www/espocrm/command.sh restore /var/www/espocrm-backup/<timestamp>.tar.gz
```

A hypervisor-level power loss is best covered by a UPS. These backups cover disk failure, bad upgrades, and operator mistakes, not a dead host.

## Fishbowl integration quick start

```bash
cp .env.example .env
python3 -m virtualenv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m src.verify
```

Common commands:

```bash
.venv/bin/python -m src.import --dry-run --limit 10
.venv/bin/python -m src.import
.venv/bin/python -m src.sync --dry-run
.venv/bin/python -m src.sync
.venv/bin/python -m src.categorize --stats
```

Optional cron for follow-up reminders:

```bash
# edit the path inside espocrm/cron/crontab.txt if this repo lives elsewhere
crontab espocrm/cron/crontab.txt
```

The sync/import/categorization code depends on `.env` values. Keep `.env` local-only.

## Past Due Import (in-app)

The CRM exposes a `Past Due Import` tab below Calendar. Upload the accounting `.xlsx` export there; the importer detects the report date from the filename, matches each sales order number to its Account, and writes the aggregated values back to `cPastDue`, `cDaysOverdue`, `cPastDueAmount`, `cPastDueAmountCurrency`, and `cPastDueData`.

The importer clears existing past-due flags first and then re-applies the uploaded report, so each run is a full refresh. Use **Dry Run** to preview counts without writing.

The underlying endpoint is `POST /api/v1/PastDueImport?fileName=<name>&dryRun=1`, with the raw `.xlsx` bytes as the request body and a valid `X-Api-Key`. It requires edit access to `Account`.

This is a PHP port of the original Python importer, which is still available:

```bash
python3 -m src.past_due_import "past-due-invoices.xlsx" --dry-run
```

## Notable EspoCRM customizations captured here

- custom `CSalesOrder` and `CSalesOrderItem` entities and related controllers/metadata
- Account custom fields such as `cCategory`, `cPrePay`, `cComments`, `cPastDue`, and follow-up fields
- Account list behavior: row highlighting, click behavior, default sort persistence, panel tweaks
- Sales order panel custom rendering, row expansion, filtering, and styling
- sidebar/menu cleanup and record/layout overrides (left navigation comes from `tabList`, not `app.menu`)
- in-app Past Due Import: sidebar tab below Calendar, `POST /api/v1/PastDueImport`, PHP `.xlsx` parser + Account updater
- safe config overrides: `clientCspDisabled`, `recordsPerPageSmall`, `maxEmailAccountCount`, `siteUrl`, `tabList`

## Important constraints

- Never commit `.env`.
- Never commit live `data/config.php` or the real `/var/www/espocrm/docker-compose.yml`; this repo stores sanitized equivalents only.
- `ClientManager.php` and the php-fpm tuning are not on a Docker volume. `restore-container-config.sh` (cron, every 10 minutes) re-applies them after a container recreate; `deploy.sh` also restores the patch.
- This repo is pinned to the current live behavior. If you switch to a materially newer EspoCRM image, re-test the `ClientManager.php` replacement.
- `deploy.sh` targets `/var/www/espocrm` specifically.
- `export-from-live.sh` should be run before committing if someone changed the live CRM through the UI or by editing live files directly.
- `espocrm/config/config-overrides.php` owns the left navigation `tabList`; `deploy.sh` overwrites it, so sidebar changes made in the UI must be copied back into the repo to survive a deploy.
- The in-app Past Due Import is a full refresh: it clears existing past-due flags before re-applying the uploaded report. Run Dry Run first.
- Exact live-schema parity includes a small supplemental SQL layer in `espocrm/schema/live-parity.sql` for legacy columns that metadata rebuild alone does not describe.

## Exporting new live changes back into the repo

If someone changes metadata or client files directly on the running CRM:

```bash
./espocrm/scripts/export-from-live.sh
git diff
```

Recommended workflow:

1. make the live CRM change
2. run `./espocrm/scripts/export-from-live.sh`
3. review `git diff`
4. commit the repo change
5. push

## Security

- Never read `.env` as a file.
- Secrets must stay in environment variables or local-only files.
- Diagnostics should report presence/health, not secret values.
