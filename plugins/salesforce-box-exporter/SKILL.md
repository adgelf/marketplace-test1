---
name: salesforce-box-exporter
description: >
  Use this skill when the user asks for the Salesforce → Box file exporter,
  wants to download or run it, or asks how to set it up. Also triggers for
  "MassDownloader", "salesforce-box-exporter", or any mention of exporting
  Salesforce files to Box.
---

# Salesforce → Box File Exporter

A Java command-line tool that exports all files from Salesforce into Box.com. It queries every file attachment and content document linked to Accounts, Opportunities, and Contracts, downloads them from Salesforce, and uploads them into a structured folder hierarchy in Box — skipping files that already exist, so it's safe to re-run at any time.

**What it exports:**
- Legacy `Attachment` objects (linked to Accounts, Opportunities, Contracts)
- Modern `ContentDocument` / `ContentVersion` files (linked via `ContentDocumentLink`)

**What it does with them:**
- Creates a folder hierarchy in Box mirroring your Salesforce structure
- Names every file and folder with the Salesforce ID in brackets for traceability: `My Document [068XX...].pdf`
- Renames existing Box folders automatically if the Salesforce record name changed
- Uses chunked upload for large files (≥ 20 MB)
- Retries automatically on Box rate limits (429) and server errors (5xx)
- Writes a JSON error report for any failures, which can be used to retry only those files

**Box folder structure produced:**
```
Box root folder/
  Acme Corp [001XX...]/                    ← Account files land here
  Acme Corp [001XX...]/
    Opportunities/
      Big Deal Q2 [006XX...]/              ← Opportunity files
    Contracts/
      Contract-00042 [800XX...]/           ← Contract files
```

## Deliver the zip

When the user asks for the exporter, assemble and deliver a zip using bash:

```bash
SD="<absolute path to this skill directory>"
OUT=/home/claude/salesforce-box-exporter
JP=$OUT/src/main/java/com/mirantis/massdownloader

rm -rf $OUT
mkdir -p $JP/box $JP/config $JP/model $JP/salesforce $JP/service $JP/util
mkdir -p $OUT/src/main/resources $OUT/config

cp $SD/scripts/source/pom.xml                        $OUT/
cp $SD/scripts/source/Dockerfile                     $OUT/
cp $SD/scripts/run-docker.sh                         $OUT/
cp $SD/scripts/retry-failures.sh                     $OUT/
cp $SD/references/README.md                          $OUT/
cp $SD/references/application.properties.template    $OUT/config/application.properties
cp $SD/references/box_config.json.template           $OUT/config/box_config.json
cp $SD/scripts/source/log4j2.xml                     $OUT/src/main/resources/
cp $SD/scripts/source/MassDownloaderApplication.java $JP/
cp $SD/scripts/source/BoxClient.java                 $JP/box/
cp $SD/scripts/source/AppConfig.java                 $JP/config/
cp $SD/scripts/source/ExportOptions.java             $JP/config/
cp $SD/scripts/source/FileRecord.java                $JP/model/
cp $SD/scripts/source/SalesforceClient.java          $JP/salesforce/
cp $SD/scripts/source/ExportOrchestrator.java        $JP/service/
cp $SD/scripts/source/SalesforceMetadataService.java $JP/service/
cp $SD/scripts/source/NameFormatter.java             $JP/util/
chmod +x $OUT/run-docker.sh $OUT/retry-failures.sh

cd /home/claude && zip -r salesforce-box-exporter.zip salesforce-box-exporter/
cp /home/claude/salesforce-box-exporter.zip /mnt/user-data/outputs/salesforce-box-exporter.zip
```

Present `/mnt/user-data/outputs/salesforce-box-exporter.zip` with `present_files`, then give the user the setup and usage instructions below.

## Setup instructions

**Step 1 — Fill in your credentials (2 files):**

- `config/application.properties` — replace every `REPLACE_ME_*` with your Salesforce and Box credentials
- `config/box_config.json` — replace with the real file from Box Developer Console → your App → Configuration → Generate a Public/Private Keypair

**Step 2 — Build:**
```bash
mvn package
```
Requires Java 17+ and Maven 3.8+.

**Step 3 — Run:**
```bash
target/app/bin/mass-exporter
```

## Usage examples

**Export everything (first run):**
```bash
target/app/bin/mass-exporter
```

**Incremental export — only files modified since a date:**
```bash
target/app/bin/mass-exporter --since=2024-01-01
```

**Export a specific date range:**
```bash
target/app/bin/mass-exporter --since=2024-01-01 --until=2024-06-30
```

**Export only files created this year:**
```bash
target/app/bin/mass-exporter --created-since=2024-01-01
```

**Export only Account files (skip Opportunities and Contracts):**
```bash
target/app/bin/mass-exporter --include-types=account
```

**Export only Opportunities and Contracts:**
```bash
target/app/bin/mass-exporter --include-types=opportunity,contract
```

**Export files for specific accounts only:**
```bash
target/app/bin/mass-exporter --include-account-ids=001XX000003GYjY,001XX000003GYjZ
```

**Export files for a specific opportunity:**
```bash
target/app/bin/mass-exporter --include-opportunity-ids=006XX000001ZYXW
```

**Export a specific file by Salesforce ID:**
```bash
target/app/bin/mass-exporter --include-file-ids=068XX000001ABCD
```

**Retry only files that failed in a previous run:**
```bash
target/app/bin/mass-exporter --retry-from-report=export-errors-1718000000000.json
```

**Write the error report to a specific path:**
```bash
target/app/bin/mass-exporter --error-report=reports/my-errors.json
```

**Use a non-default config file:**
```bash
target/app/bin/mass-exporter --config=/etc/exporter/production.properties
```

**Combine filters — recent files for specific accounts, opportunities only:**
```bash
target/app/bin/mass-exporter --since=2024-06-01 --include-types=opportunity --include-account-ids=001XX000003GYjY
```

See `README.md` in the zip for Docker instructions and the full options reference.
