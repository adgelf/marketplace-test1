# Salesforce → Box File Exporter

Exports all files from Salesforce (Accounts, Opportunities, Contracts) into a structured folder hierarchy in Box.com.

---

## Step 1 — Fill in your credentials

Edit **two files** in the `config/` folder:

### `config/application.properties`

Open the file and replace every value marked `REPLACE_ME_*`:

| Placeholder | What to put there |
|---|---|
| `REPLACE_ME_SF_CLIENT_ID` | Your Salesforce Connected App Client ID |
| `REPLACE_ME_SF_CLIENT_SECRET` | Your Salesforce Connected App Client Secret |
| `REPLACE_ME_SF_USERNAME` | Your Salesforce username (email) |
| `REPLACE_ME_SF_PASSWORD` | Your Salesforce password |
| `REPLACE_ME_SF_SECURITY_TOKEN` | Your Salesforce security token |
| `REPLACE_ME_BOX_ROOT_FOLDER_ID` | The Box folder ID where exports will go |
| `REPLACE_ME_BOX_APP_USER_ID` | Your Box app user ID (or leave blank to use enterprise connection) |

> **Where to find your Salesforce security token:**
> Salesforce → top-right avatar → Settings → Personal → Reset My Security Token

> **Where to find your Box folder ID:**
> Open the target folder in Box web → copy the number from the URL: `box.com/folder/1234567890`

### `config/box_config.json`

Replace this file entirely with the real `box_config.json` downloaded from Box:
- Box Developer Console → your App → Configuration → **Generate a Public/Private Keypair**
- This downloads a `YOURAPP_config.json` — rename it to `box_config.json` and drop it in the `config/` folder

---

## Step 2 — Build

You need **Java 17+** and **Maven 3.8+** installed.

```bash
mvn package
```

This assembles the launcher to `target/app/bin/mass-exporter`.

---

## Step 3 — Run

### Option A: Run the assembled launcher directly (requires Java 17+)

```bash
target/app/bin/mass-exporter
```

### Option B: Run with Docker (no Java/Maven needed after build)

```bash
# Build the image (one time)
docker build -t salesforce-box-exporter .

# Run
docker run --rm \
  -v "$(pwd)/config/box_config.json:/run/secrets/box_config.json:ro" \
  -e SF_CLIENT_ID=YOUR_CLIENT_ID \
  -e SF_CLIENT_SECRET=YOUR_CLIENT_SECRET \
  -e SF_USERNAME=your@email.com \
  -e SF_PASSWORD=yourpassword \
  -e SF_SECURITY_TOKEN=yourtoken \
  -e BOX_CONFIG_PATH=/run/secrets/box_config.json \
  -e BOX_ROOT_FOLDER_ID=YOUR_FOLDER_ID \
  salesforce-box-exporter
```

### Option C: Use the helper script

```bash
# Make it executable (Mac/Linux)
chmod +x run-docker.sh

# Set your credentials as environment variables, then run
export SF_CLIENT_ID=YOUR_CLIENT_ID
export SF_CLIENT_SECRET=YOUR_CLIENT_SECRET
export SF_USERNAME=your@email.com
export SF_PASSWORD=yourpassword
export SF_SECURITY_TOKEN=yourtoken
export BOX_ROOT_FOLDER_ID=YOUR_FOLDER_ID
export BOX_CONFIG_HOST_PATH=$(pwd)/config/box_config.json

./run-docker.sh
```

---

## Common run options

```bash
# Export only files modified since a date
target/app/bin/mass-exporter --since=2024-01-01

# Export only Account files
target/app/bin/mass-exporter --include-types=account

# Export only specific accounts
target/app/bin/mass-exporter --include-account-ids=001XX000003GYjY,001XX000003GYjZ

# Retry only failed files from a previous run
target/app/bin/mass-exporter --retry-from-report=export-errors-1718000000000.json
```

Full list of options:
```
--since=YYYY-MM-DD               Files modified on or after this date
--until=YYYY-MM-DD               Files modified on or before this date
--created-since=YYYY-MM-DD       Files created on or after this date
--created-until=YYYY-MM-DD       Files created on or before this date
--include-types=account,opportunity,contract
--include-account-ids=ID1,ID2,...
--include-opportunity-ids=ID1,ID2,...
--include-contract-ids=ID1,ID2,...
--include-file-ids=ID1,ID2,...
--retry-from-report=PATH
--error-report=PATH
--config=PATH                    Use a different application.properties
```

---

## What gets exported where

```
Box root folder/
  Acme Corp [001XX...]/                    ← Account files
  Acme Corp [001XX...]/
    Opportunities/
      Big Deal Q2 [006XX...]/              ← Opportunity files
    Contracts/
      Contract-00042 [800XX...]/           ← Contract files
```

Files are named: `Original Filename [SalesforceID].pdf`

---

## If some files fail

The exporter writes an error report: `export-errors-<timestamp>.json`

To retry only the failed files:
```bash
target/app/bin/mass-exporter --retry-from-report=export-errors-1718000000000.json
```

---

## Logs

Logs are written to `logs/export.log` and also printed to the console.
To see more detail, set `level="DEBUG"` in `src/main/resources/log4j2.xml` and rebuild.
