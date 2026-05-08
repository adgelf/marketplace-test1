---
name: salesforce-login-anomaly-detection
description: Analyze Salesforce login history (LoginHistory CSV exports, SOQL results, Event Monitoring Login event files, or live SOQL via the Salesforce MCP) to surface security and compliance anomalies. Use whenever the user mentions Salesforce, SFDC, LoginHistory, Login History, Event Monitoring, suspicious logins, account compromise, MFA, SSO — or asks for impossible travel, brute force, unusual API usage (SOAP/REST/Bulk/Metadata), off-hours logins, "who logged in via SOAP API", "all users with LoginSubType=X", "find anomalies via SOQL", "login audit", "security review". Trigger even on bare CSVs with columns like UserId/LoginTime/SourceIp/LoginType. Handles very large exports (15M+ rows) via DuckDB streaming. IMPORTANT: for live SOQL follow the Mode B minimization rules — one query pulls everything, filters happen downstream.
---

# Salesforce Login Anomaly Detection

Interactive analysis of Salesforce login history exports to surface security and compliance anomalies. Use this skill when the user has a LoginHistory export (from Setup → Login History, SOQL, or Event Monitoring) and wants to understand whether there is suspicious activity: compromised accounts, unusual API usage, impossible travel, etc.

## Working philosophy

**Anomaly ≠ rare event.** Many "suspicious" patterns in Salesforce are actually normal for a given org: integration users log in via SOAP API every 5 minutes, consultants work from multiple countries, deployment users hit the org from CI/CD. So this skill:

1. First **calibrates** — understands what counts as normal in *this* org (are there integration users, is SSO used, where is the team located).
2. Only then looks for deviations.
3. Always explains *why* something looks suspicious and gives a way to verify (specific UserId, IP, timestamp).

Security is a domain where false positives are expensive. It is better to present 5 high-quality findings with context than 500 rows of "every user who logged in at night".

## Two modes — pick one upfront

This skill runs in one of two modes. Decide which one based on the user's **first** message and stick with it. Do not switch silently.

### Mode A — Offline file analysis

The user attached a file (UI export, SOQL dump, Event Monitoring log). Work happens through the scripts in `scripts/`. This is the default mode — see "Workflow" below.

### Mode B — Live SOQL via Salesforce MCP

The user wants data pulled directly from Salesforce through the connected Salesforce MCP (`soqlQuery`). **Strict query-minimization rules apply** in this mode.

#### Mode B rules

1. **One query, maximum data.** Do not issue several small SOQLs "to explore". Build a single query that pulls all fields and rows needed for the task. `LoginHistory` allows `LIMIT 20000` — use the upper bound if a time filter is enough.

2. **No clarifying questions before the first query.** If the user says "find anomalies in logins from the last week", run the query for the last 7 days immediately. Do not ask "which week?", "should I include failures?", "what fields matter?". Sensible defaults:
   - Window: last **7 days** unless specified
   - Status: **both** Success and failure
   - Fields: the full set in point 3
   - LoginType / LoginSubType / NetworkId: **no filter** (filter later locally)

3. **Canonical SOQL for anomaly detection.** Use this as the starter query — it covers ~90% of the patterns in `references/anomaly_patterns.md` in a single call:

   ```sql
   SELECT Id, UserId, LoginTime, SourceIp, LoginType, LoginSubType,
          LoginUrl, Status, Browser, Platform, Application, ClientVersion,
          ApiType, ApiVersion, CountryIso, TlsProtocol, CipherSuite,
          NetworkId, AuthenticationServiceId, LoginGeoId
   FROM LoginHistory
   WHERE LoginTime >= LAST_N_DAYS:7
   ORDER BY LoginTime DESC
   LIMIT 20000
   ```

   If you need usernames — one additional query to `User`, filtered by the UserIds you just collected:
   ```sql
   SELECT Id, Username, IsActive, Profile.Name, UserRole.Name, LastLoginDate
   FROM User
   WHERE Id IN (:userIdList)
   ```

4. **"All users with LoginSubType = X" is also one query.**
   ```sql
   SELECT UserId, LoginTime, SourceIp, Status, Application, CountryIso
   FROM LoginHistory
   WHERE LoginSubType = 'SOAP API'
     AND LoginTime >= LAST_N_DAYS:30
   ORDER BY UserId, LoginTime
   LIMIT 20000
   ```
   Do not run a separate `COUNT()`, then a separate pull, then a separate distinct-users query — do all of that locally after one pull.

5. **If 20000 rows is not enough.** Hitting the limit means the data is truncated. Narrow the **date** range and issue parallel chunks by date (e.g. 4 weekly queries for a month). Do not narrow by user / type / status — that biases the analysis. Tell the user: "over a month we'd exceed 20000 rows; pulling in 4 weekly chunks."

6. **Cache the result in a DataFrame.** All subsequent filters, groupings, detectors — run locally on the data you already have. If the user then asks "now show only SOAP API" — **do not issue a new SOQL**, filter the existing DataFrame.

7. **A new SOQL is only justified when:** (a) the user explicitly asks for a different time window; (b) you need data that is not in `LoginHistory` (e.g. `User.IsActive`); (c) the first query actually hit the 20000 limit.

8. **No "let me verify the schema first".** If the result looks off, show what you got and ask based on real data. Do not issue exploratory SOQLs.

#### Correct Mode B flow

1. User: "find anomalies in last week's logins"
2. Claude: one SOQL from point 3 → 20k rows → load into DataFrame
3. (Optionally, if usernames are needed) one SOQL to `User`
4. Run the detectors from `anomaly_patterns.md` locally, show top-5 findings
5. User: "dig into impossible travel"
6. Claude: **no new SOQL** — show details from the DataFrame already in memory

#### Anti-patterns — do NOT do this

- ❌ `SELECT COUNT() FROM LoginHistory WHERE ...` → then `SELECT ... LIMIT 100` → then "let me refine the filter" → another query
- ❌ A separate SOQL per `LoginSubType`
- ❌ "Let me check the schema first" → `SELECT Id FROM LoginHistory LIMIT 1`
- ❌ Asking the user for timezone / period / integration users before the first query

## Workflow

_This section covers Mode A (offline file). For Mode B see the rules above._

### Step 0. Preflight — verify toolkit availability

**Before any analysis, check what is actually available on disk.** This skill ships with supporting `scripts/` and `references/` directories, but users sometimes install only `SKILL.md`. The behavior must be deterministic either way — a security skill cannot produce different findings between runs on the same data.

Run this check first:

```bash
# Locate the skill directory — adjust path if installed elsewhere
SKILL_DIR="$(dirname "$(readlink -f SKILL.md 2>/dev/null || echo .)")"
ls "$SKILL_DIR/scripts" 2>/dev/null
ls "$SKILL_DIR/references" 2>/dev/null
```

Then decide per the table below, **state the chosen branch to the user**, and stick with it for the whole session:

| Situation | Branch | What to do |
|---|---|---|
| `scripts/` present + DuckDB installed (`python -c 'import duckdb'` succeeds) | **Full toolkit** | Use the scripts as written in Steps 2–4. This is the fast, memory-safe path for files of any size. |
| `scripts/` present but `import duckdb` fails | **Install or degrade** | Offer the user two install options: `pip install --require-hashes -r requirements.lock` (preferred — exact versions plus SHA256 hash verification of every package and transitive dep, supply-chain hardened) or `pip install -r requirements.txt` (exact versions, no hash check). If install fails or user declines, fall back to the Inline branch. |
| `scripts/` absent, only `SKILL.md` on disk | **Inline SQL / pandas** | Use the **Inline Detector Specs** section at the bottom of this file. Do NOT improvise — every detector has a fixed SQL/pandas implementation with fixed thresholds defined below. |
| File is huge (> 500 MB) AND branch is Inline AND DuckDB unavailable | **Refuse with explanation** | Tell the user: `pandas.read_csv` will exhaust memory on this file, and the DuckDB-based toolkit isn't available. Ask them to install DuckDB or provide a smaller time-windowed export. Do not proceed. |

**Announce the branch explicitly**, e.g.:
> "I see `scripts/` is missing — running in **Inline mode**. I'll use the fixed detector specs from SKILL.md. Results will be identical to what the `scripts/` toolkit would produce for the same thresholds, just slower on large files."

This announcement is non-optional. It prevents the skill from silently producing inconsistent findings between runs where the toolkit is and isn't present.

### Step 1. Identify the data source

Salesforce login data comes from several places with *different* column structures. Figure out the source **before** analysis — it decides which fields to expect and which anomalies are even detectable. The full field map is in `references/salesforce_login_schema.md`. Read it before any real processing.

Primary sources:

- **Setup → Login History UI export** — CSV with columns like `Username, Login Time, Source IP, Login Type, Status, Browser, Platform, Application, Login URL, Client Version, API Type, API Version, Country`. Usually ≤ 20 000 rows (UI limit).
- **SOQL query on `LoginHistory`** — JSON or CSV with camelCase API field names: `UserId, LoginTime, SourceIp, LoginType, LoginSubType, Status, Browser, Platform, Application, CountryIso, TlsProtocol, CipherSuite, NetworkId, AuthenticationServiceId, LoginGeoId`.
- **Event Monitoring `Login` event log file** — CSV with a much richer field set (`EVENT_TYPE, TIMESTAMP, USER_ID, LOGIN_KEY, SESSION_KEY, SOURCE_IP, LOGIN_STATUS, LOGIN_TYPE, LOGIN_SUB_TYPE, API_TYPE, API_VERSION, USER_NAME, CLIENT_IP, TLS_PROTOCOL, CIPHER_SUITE, AUTHENTICATION_METHOD_REFERENCE ...`). Column names are UPPER_SNAKE_CASE. Richer and more common for security audits.

If the source is unclear (e.g. a custom export from Tableau / Splunk / Snowflake into which logins are tee'd), ask the user and map columns to one of the canonical schemas.

### Step 2. Profile (calibrate normal)

Before searching for anomalies — **understand this org's baseline**. Run `scripts/profile_logins.py`:

```bash
python scripts/profile_logins.py --input /path/to/login_export.csv
```

The script uses DuckDB under the hood and handles files of any size (tested on 15M+ rows) with a near-constant memory footprint. It produces a Markdown summary:

- Time range
- Scale: rows, unique users, unique IPs, unique countries
- `LoginType` / `LoginSubType` distribution (integrations become obvious here)
- Success / Failure breakdown by status
- Top users by login count
- Top IPs by login count
- Platform / browser / application distributions

Show this profile to the user **before** searching for anomalies. They often immediately say "oh, that user is our Zapier integration, ignore it" or "we don't use Data Loader — why are there so many Bulk API logins?".

**After** the profile is shown, and **only if** the answers are not already obvious from the profile itself, ask focused calibration questions grounded in what the profile revealed. The rule is: *one question, maximum two*, each tied to a concrete row the user just saw — no preparatory interrogation. Examples:

- If the profile shows top-10 users with integration-sounding names: "I see `mulesoft.integration@`, `svc.etl@` etc. in the top users — can you confirm the integration-user naming pattern, or should I treat them as humans?"
- If multiple `LoginType` values appear without SSO hits: "Profile shows `Application` logins but no `SAML *` — is SSO in use, or should direct Application logins be considered normal?"
- If the country distribution is wide: "I see 12 distinct countries — is the team globally distributed, or should non-EU logins be flagged?"
- If Login IP Ranges matter to the org: "Are Login IP Ranges / Trusted IP Ranges configured in this org?"

Do NOT ask these questions preemptively or as a checklist. If the profile already makes the answer clear (e.g. one country, one obvious integration user), skip the question entirely and proceed.

### Step 3. Detect anomalies by category

The full pattern catalog with DuckDB SQL and pandas implementations is in `references/anomaly_patterns.md`. Main categories:

**Compromise / suspicious access:**
- *Impossible travel* — one `UserId` logging in from geographically distant IPs in a short interval (e.g. > 1000 km with < 2h gap). Account for: VPN, mobile roaming — not always an attack.
- *Brute force* — a burst of `Status != 'Success'` against one UserId or from one IP, especially across different usernames.
- *Failed → Success for one user* — a series of failures followed by a success (classic guessed-password signal).
- *New country for a user* — first successful login from a `CountryIso` where this UserId has never been before.
- *Logins after a failed MFA challenge* — in Event Monitoring, visible via `AUTHENTICATION_METHOD_REFERENCE`.

**API / automation:**
- *Unusual SOAP / Bulk / Metadata API use by a regular user* — regular non-integration users should not be logging in via `LoginSubType = "SOAP API"` / `"Bulk API"`. Often a sign that someone is exporting data via Data Loader or a custom script. See the next section.
- *API logins outside business hours* — fine for an integration; suspicious for a human user.
- *Legacy TLS / weak ciphers* — `TLS 1.0 / 1.1`, RC4 — compliance risk.

**Behavioral:**
- *Logins outside a user's typical hours* — if the user usually works 9–18 CET but there's a 3am login.
- *Stale accounts waking up* — the user has not logged in for 90+ days, then activity resumes.
- *Shared credentials* — the same UserId logging in concurrently from different IPs / countries.
- *New devices / user agents* — first login with a new `Browser + Platform + ClientVersion` combo.

**Organizational:**
- *Users without MFA logging in successfully from new countries* — requires join with `User` to find who lacks MFA.
- *Deactivated users* — if `User.IsActive` is available, cross-reference with UserIds in logins: logins from deactivated users are critical.
- *NetworkId* — if Experience Cloud communities are in use, sudden activity in a redundant community is suspicious.

### Step 4. User-specific queries

Besides general anomaly search, the skill supports targeted queries. The most common one is **"find all users with a specific LoginSubType"**, especially `SOAP API`. This matters because:

- Salesforce is retiring `Platform SOAP API login()` for some flows — stragglers need to be identified and migrated.
- SOAP API logins by non-integration users are a classic red flag: Data Loader, WorkBench, third-party ETL run by a human.
- Compliance audits often need a named list of "who used the legacy API and when".

Use `scripts/filter_by_subtype.py`. It takes a CSV path and a `LoginSubType` value and returns:

1. A list of unique users with that subtype (UserId, Username if available, login count, first and last timestamp, success rate, distinct IPs).
2. A Success / Failure breakdown.
3. A daily activity timeline.
4. A CSV of the full matching rows for further drilling.

Examples:

```bash
# All users with SOAP API logins
python scripts/filter_by_subtype.py --input login_history.csv --subtype "SOAP API"

# Bulk API (mass exports via Data Loader)
python scripts/filter_by_subtype.py --input login_history.csv --subtype "Bulk API"

# Metadata API (deploys via sfdx / ant)
python scripts/filter_by_subtype.py --input login_history.csv --subtype "Metadata API"

# Multiple subtypes at once
python scripts/filter_by_subtype.py --input login_history.csv --subtype "SOAP API,Bulk API"
```

Typical `LoginSubType` values that appear in exports: `SOAP API`, `Partner API`, `Enterprise API`, `Bulk API`, `Bulk API 2.0`, `Metadata API`, `REST API`, `Apex API`, `OAuth`, `SAML`, `Refresh Token`. The exact set depends on the Salesforce release and enabled features.

When the user asks about "SOAP API logins":

1. Run the filter and show the summary.
2. Not just a list — but **grouped by user**, so it's clear who it is: integration or human.
3. Highlight potentially-human users (usernames without `integration`/`svc`/`api`/`apex` prefixes) — priority 1.
4. Show success rate — a user at 100% failure on SOAP API means either a broken integration or a breach attempt.
5. Attach the full CSV via `present_files` for deeper analysis.

### Step 5. Present results

Don't dump every finding on the user at once. Structure it:

1. **Top 3–5 priority findings** with severity (Critical / High / Medium / Info) and a short explanation each: what was found, why it's anomalous, how many users / logins are affected.
2. **For each** — concrete examples (UserId, Username, LoginTime, SourceIp) so the user can verify.
3. **Soft observations** — things that *might* be anomalies but could also be normal (an integration? a VPN? a test user?). Ask.
4. **Recommendations** — where appropriate (enable MFA for this group, configure Login IP Range, review a Connected App).
5. Large lists of suspicious rows — ship as a separate CSV via `present_files`, keep only the summary in chat.

## Handling large files (10M+ rows)

Event Monitoring and long-range SOQL dumps can produce CSVs with **tens of millions of rows** (hundreds of MB to several GB). Naive `pandas.read_csv` will blow up memory on such files. The scripts in this skill use **DuckDB** to stream data directly from CSV without loading everything into RAM. A few implications:

- `profile_logins.py`, `filter_by_subtype.py`, and `detect_anomalies.py` all run aggregate queries against the CSV file in place. A 15M-row file profiles in tens of seconds with well under 1 GB of RAM.
- For `detect_anomalies.py`, the heavy detectors (impossible travel, brute force, failed-then-success) are implemented as DuckDB window-function SQL, not pandas loops — essential at scale.
- If you need to hand-roll a query on a very large file, prefer DuckDB SQL over pandas:
  ```python
  import duckdb
  con = duckdb.connect()
  result = con.sql("""
      SELECT UserId, COUNT(*) AS logins
      FROM read_csv_auto('/path/to/big_file.csv')
      WHERE Status != 'Success'
      GROUP BY UserId
      ORDER BY logins DESC
      LIMIT 20
  """).df()
  ```
- Parquet is dramatically more efficient than CSV for repeated queries. The scripts **cache it automatically**: files larger than 500 MB are converted once to Parquet next to the CSV on the first run (e.g. `big_logins.csv` → `big_logins.csv.parquet`), and all subsequent runs read from Parquet without re-parsing the CSV. A 1.3 GB CSV typically compresses to ~70 MB Parquet.
- All three scripts accept the same cache-and-memory flags, matching the signature of `create_normalized_view()`:
    - `--parquet-threshold-mb FLOAT` — files larger than this are cached as Parquet on first run (default: **500**). Set to a large number (e.g. `1000000`) to disable caching entirely.
    - `--cache-dir DIR` — directory to put the `.parquet` cache file in. Default: alongside the input CSV. Use this to keep the source directory read-only, or to share the cache across multiple copies of the same CSV.
    - `--spill-dir DIR` — directory DuckDB spills intermediate results to when RAM is exhausted. Default: a private `tempfile.mkdtemp()` directory (cleaned up by the OS on reboot, not automatically deleted after the script exits).
    - `--memory-limit-gb FLOAT` — memory cap before DuckDB spills to disk (default: **2.0**).
- **Cache invalidation.** The cache filename is derived from the CSV basename; the skill does NOT automatically detect if the CSV has changed. If you replace `big_logins.csv` with a new file but keep the name, **delete the stale `big_logins.csv.parquet` manually** or pass `--cache-dir` to a fresh location.
- **Cleanup.** The Parquet cache is persistent — it's the whole point of the feature. Clean it up yourself when you're done with a given dataset. Spill directories under `tempfile.mkdtemp()` will accumulate if the process crashes; `rm -rf /tmp/duckdb_spill_*` is safe any time no analysis is running.
- Only fall back to pandas chunked reading when DuckDB is unavailable. DuckDB is the default.

## Principles for interactive work

- **This is a security context — mistakes are costly.** Better to under-claim than to wrongly accuse a user of compromise. Always flag hypotheses as hypotheses.
- **Ask after data, not before.** In Mode B (live SOQL) — query first, show results, then clarify. Don't ask preparatory questions about period / fields / whether failures matter — use sensible defaults. In Mode A (file) — run the profile first; clarifying questions come only after the user has seen the summary.
- **Don't re-ask what can be computed.** Integration-user list? — apply the default heuristic, show the result, ask "does this look right, or should I extend the list?". Timezone? — show in UTC, note that it's UTC, ask only if it matters.
- **Respect privacy.** Don't log or persist full IPs / usernames to durable files without need. For discussion, UserId + masked IP (`203.0.113.xxx`) is enough.
- **Don't fabricate attribution.** If you don't know why a user logged in from Singapore, say "possibly travel or VPN — confirm with the user".

## References

- `references/salesforce_login_schema.md` — LoginHistory / Event Monitoring Login fields, values, and how they map between sources
- `references/anomaly_patterns.md` — detailed anomaly patterns with both DuckDB SQL and pandas implementations
- `references/soql_queries.md` — canonical SOQL queries for Mode B (live via Salesforce MCP), minimization rules
- `scripts/profile_logins.py` — initial profile of an export (DuckDB-based, scales to 15M+ rows)
- `scripts/detect_anomalies.py` — full detector suite (impossible travel, brute force, etc.) as DuckDB SQL
- `scripts/filter_by_subtype.py` — filter and summary by `LoginSubType` (SOAP API / Bulk API / etc.), DuckDB-based

---

## Inline Detector Specs (authoritative when `scripts/` is missing)

This section defines every detector with a fixed threshold and a fixed SQL implementation, so that runs in Inline mode (no `scripts/` on disk) produce the same findings as runs with the full toolkit. **Do NOT improvise new thresholds or alternative implementations** — if a threshold seems wrong for the user's org, surface it as a parameter to tweak, but start from these defaults.

### Canonical column names

All inline SQL assumes a normalized view named `logins` with these columns:
`userId, username, loginTime, sourceIp, loginType, loginSubType, status, countryIso, browser, platform, application, clientVersion, tlsProtocol, apiType, apiVersion, networkId`

`loginTime` is `TIMESTAMP`. If the raw CSV uses different column names, build the view with aliases first. Minimal DuckDB bootstrap (Inline mode):

```python
import duckdb
con = duckdb.connect()
con.execute("SET memory_limit='2GB'")
con.execute("""
    CREATE VIEW logins AS
    SELECT
        "UserId"       AS userId,
        "LoginTime"::TIMESTAMP AS loginTime,
        "SourceIp"     AS sourceIp,
        "LoginType"    AS loginType,
        "LoginSubType" AS loginSubType,
        "Status"       AS status,
        "CountryIso"   AS countryIso,
        "TlsProtocol"  AS tlsProtocol,
        "CipherSuite"  AS cipherSuite
        -- add more aliases as available in the source
    FROM read_csv_auto('/path/to/file.csv',
                       header=true, all_varchar=true, ignore_errors=true)
""")
```

### Default thresholds (authoritative)

| Detector | Parameter | Default | Unit |
|---|---|---|---|
| Impossible travel | min_km | 1000 | kilometers |
| Impossible travel | max_hours | 2.0 | hours |
| Brute force by IP | min_failures | 10 | count |
| Brute force by IP | window_minutes | 10 | minutes |
| Brute force by IP | min_unique_users | 3 | count |
| Failed-then-success | min_prior_failures | 3 | count |
| Failed-then-success | window_minutes | 30 | minutes |
| New country | lookback_days | 90 | days |
| Stale reactivation | min_dormant_days | 90 | days |
| Status spike | zscore_threshold | 3.0 | σ |
| Concurrent countries | max_minutes | 5 | minutes |

### Integration-user heuristic (fixed list)

A username is considered **integration-like** if its lowercase form contains ANY of:
`integration, svc, service, api, sys, system, etl, bot, automation, dataloader, mulesoft, workato, zapier, connector, informatica, boomi, snaplogic, talend, jitterbit`

A user whose username does not contain any of these substrings is `likelyHuman=true`. Do not add or remove patterns without the user's explicit consent.

### API-like LoginSubType set (fixed list)

`SOAP API, Bulk API, Bulk API 2.0, Metadata API, Partner API, Enterprise API, Tooling API`

### Detector 1: Impossible travel

```sql
WITH ordered AS (
    SELECT userId, loginTime, sourceIp, countryIso,
           LAG(countryIso) OVER w AS prevCountry,
           LAG(loginTime)  OVER w AS prevTime,
           LAG(sourceIp)   OVER w AS prevIp
    FROM logins WHERE status='Success' AND countryIso IS NOT NULL
    WINDOW w AS (PARTITION BY userId ORDER BY loginTime)
)
SELECT userId, prevCountry, countryIso, prevTime, loginTime,
       prevIp, sourceIp,
       EXTRACT(EPOCH FROM (loginTime - prevTime))/3600.0 AS hoursDelta
FROM ordered
WHERE prevCountry IS NOT NULL AND prevCountry <> countryIso
  AND (loginTime - prevTime) <= INTERVAL '2 hours'
ORDER BY userId, loginTime;
```

Post-process with haversine distance against a country-centroid table; keep only rows with distance ≥ 1000 km. Severity: **Critical** when both countries are far apart AND the session ended with successful access.

### Detector 2: Brute force by IP

```sql
WITH failed AS (
    SELECT sourceIp, userId, loginTime
    FROM logins WHERE status <> 'Success'
),
windowed AS (
    SELECT sourceIp, loginTime,
        COUNT(*) OVER (PARTITION BY sourceIp ORDER BY loginTime
                       RANGE BETWEEN INTERVAL '10 minutes' PRECEDING
                                 AND CURRENT ROW) AS failInWindow,
        COUNT(DISTINCT userId) OVER (PARTITION BY sourceIp ORDER BY loginTime
                       RANGE BETWEEN INTERVAL '10 minutes' PRECEDING
                                 AND CURRENT ROW) AS usersInWindow
    FROM failed
)
SELECT sourceIp,
       MAX(failInWindow) AS peakFailures,
       MAX(usersInWindow) AS peakUsers,
       COUNT(*) AS totalFailures,
       MIN(loginTime) AS firstSeen, MAX(loginTime) AS lastSeen
FROM windowed
GROUP BY sourceIp
HAVING MAX(failInWindow) >= 10 AND MAX(usersInWindow) >= 3
ORDER BY peakFailures DESC;
```

### Detector 3: Failed-then-success

```sql
WITH tagged AS (
    SELECT userId, loginTime, sourceIp, status,
           CASE WHEN status<>'Success' THEN 1 ELSE 0 END AS isFail
    FROM logins
),
with_priors AS (
    SELECT userId, loginTime, sourceIp, status,
        SUM(isFail) OVER (PARTITION BY userId ORDER BY loginTime
            RANGE BETWEEN INTERVAL '30 minutes' PRECEDING
                      AND INTERVAL '1 second' PRECEDING) AS priorFailures
    FROM tagged
)
SELECT userId, loginTime AS successTime, sourceIp AS successIp,
       CAST(priorFailures AS INTEGER) AS priorFailures
FROM with_priors
WHERE status='Success' AND priorFailures >= 3
ORDER BY priorFailures DESC, successTime;
```

Severity: **Critical** when the success IP differs from the failure IPs (enrich by comparing `successIp` against IPs in the preceding window). **High** otherwise.

### Detector 4: New country for a user

```sql
WITH success AS (
    SELECT userId, loginTime, sourceIp, countryIso
    FROM logins WHERE status='Success' AND countryIso IS NOT NULL
),
tmax AS (SELECT MAX(loginTime) AS m FROM success),
baseline AS (
    SELECT DISTINCT s.userId, s.countryIso
    FROM success s, tmax
    WHERE s.loginTime < tmax.m - INTERVAL '90 days'
)
SELECT c.userId, MIN(c.loginTime) AS loginTime, c.countryIso AS newCountry,
       any_value(c.sourceIp) AS sourceIp
FROM success c, tmax
WHERE c.loginTime >= tmax.m - INTERVAL '90 days'
  AND EXISTS (SELECT 1 FROM baseline b WHERE b.userId = c.userId)
  AND NOT EXISTS (SELECT 1 FROM baseline b
                  WHERE b.userId=c.userId AND b.countryIso=c.countryIso)
GROUP BY c.userId, c.countryIso
ORDER BY c.userId, loginTime;
```

### Detector 5: Human API logins (LoginSubType anomaly)

```sql
SELECT username, loginSubType,
       COUNT(*) AS logins,
       MIN(loginTime) AS firstSeen, MAX(loginTime) AS lastSeen,
       COUNT(DISTINCT sourceIp) AS uniqueIps
FROM logins
WHERE loginSubType IN ('SOAP API','Bulk API','Bulk API 2.0','Metadata API',
                       'Partner API','Enterprise API','Tooling API')
  AND username IS NOT NULL
  AND NOT regexp_matches(lower(username),
      '(integration|svc|service|api|sys|system|etl|bot|automation|dataloader|mulesoft|workato|zapier|connector|informatica|boomi|snaplogic|talend|jitterbit)')
GROUP BY username, loginSubType
ORDER BY logins DESC;
```

### Detector 6: Filter by LoginSubType (user-facing "who used SOAP API")

```sql
SELECT userId,
       any_value(username) AS username,
       COUNT(*) AS logins,
       SUM(CASE WHEN status='Success' THEN 1 ELSE 0 END) AS successLogins,
       MIN(loginTime) AS firstSeen, MAX(loginTime) AS lastSeen,
       COUNT(DISTINCT sourceIp) AS uniqueIps,
       STRING_AGG(DISTINCT loginSubType, ', ' ORDER BY loginSubType) AS subtypesUsed
FROM logins
WHERE loginSubType IN ('SOAP API')  -- parameter: the subtype(s) in question
GROUP BY userId
ORDER BY logins DESC;
```

After grouping, compute `likelyHuman` in pandas using the fixed integration-pattern list above, and split the output into "priority review (likely humans)" and "integrations" sections.

### Detector 7: Weak TLS / cipher suites

```sql
SELECT userId, username, tlsProtocol, cipherSuite, COUNT(*) AS logins
FROM logins
WHERE tlsProtocol IN ('TLSv1','TLSv1.1','TLS 1.0','TLS 1.1')
   OR cipherSuite LIKE '%RC4%' OR cipherSuite LIKE '%DES%'
   OR cipherSuite LIKE '%MD5%' OR cipherSuite LIKE '%NULL%'
GROUP BY userId, username, tlsProtocol, cipherSuite
ORDER BY logins DESC;
```

### Detector 8: Stale reactivation

```sql
WITH gaps AS (
    SELECT userId, username, loginTime, sourceIp, countryIso,
           LAG(loginTime) OVER (PARTITION BY userId ORDER BY loginTime) AS prevLogin
    FROM logins WHERE status='Success'
)
SELECT userId, username, prevLogin, loginTime AS wakeUpTime,
       EXTRACT(EPOCH FROM (loginTime - prevLogin))/86400.0 AS gapDays,
       sourceIp, countryIso
FROM gaps
WHERE prevLogin IS NOT NULL
  AND (loginTime - prevLogin) >= INTERVAL '90 days'
ORDER BY gapDays DESC;
```

### Detector 9: Concurrent-country sessions

```sql
WITH ordered AS (
    SELECT userId, loginTime, sourceIp, countryIso,
           LAG(countryIso) OVER w AS prevCountry,
           LAG(sourceIp)   OVER w AS prevIp,
           LAG(loginTime)  OVER w AS prevTime
    FROM logins WHERE status='Success'
    WINDOW w AS (PARTITION BY userId ORDER BY loginTime)
)
SELECT userId, prevTime, loginTime, prevCountry, countryIso, prevIp, sourceIp,
       EXTRACT(EPOCH FROM (loginTime - prevTime))/60.0 AS minutesDelta
FROM ordered
WHERE prevCountry IS NOT NULL AND prevCountry <> countryIso
  AND (loginTime - prevTime) <= INTERVAL '5 minutes';
```

### Detector 10: Status spikes (z-score on hourly buckets)

```sql
WITH bucketed AS (
    SELECT date_trunc('hour', loginTime) AS hourBucket, status, COUNT(*) AS cnt
    FROM logins WHERE loginTime IS NOT NULL
    GROUP BY 1, 2
),
stats AS (
    SELECT status, AVG(cnt) AS meanCnt, STDDEV_POP(cnt) AS stdCnt
    FROM bucketed GROUP BY status
)
SELECT b.hourBucket, b.status, b.cnt,
       (b.cnt - s.meanCnt) / NULLIF(s.stdCnt, 0) AS zscore
FROM bucketed b JOIN stats s USING (status)
WHERE s.stdCnt > 0 AND (b.cnt - s.meanCnt) / s.stdCnt > 3
ORDER BY zscore DESC;
```

### Severity mapping (fixed)

| Severity | Criteria |
|---|---|
| **Critical** | Impossible travel + success; failed-then-success from a different IP; active logins by deactivated users; brute force that ends in a success |
| **High** | Brute force without success; new country for a privileged user; humans using Metadata / Bulk API at volume (≥ 100 logins in window) |
| **Medium** | Stale reactivation; new country for a regular user; weak TLS; unusual hours |
| **Info** | Integration summaries, distributions, compliance reviews without specific incidents |

These criteria are authoritative — if a finding is ambiguous, prefer the lower severity and explain why, rather than escalating on speculation.

### Pandas fallback (if DuckDB is unavailable and file is small)

For files under ~200 MB and no DuckDB, pandas can substitute. But: **keep the same thresholds**, do not simplify logic. If memory is a constraint, ask the user to install DuckDB rather than silently skipping detectors.