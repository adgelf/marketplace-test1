# Canonical SOQL Queries for Login Anomaly Detection

Ready-to-use queries for Mode B (live via Salesforce MCP). Principle: **one query pulls as much data as possible**. All filtering and grouping happens downstream in DuckDB or pandas after the pull.

## Q1. Universal pull for anomaly detection

The starter query for any "find anomalies in logins" task. Covers ~90% of the patterns in `anomaly_patterns.md`.

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

Adjust `LAST_N_DAYS:N` to the requested window. For exact dates:
```sql
WHERE LoginTime >= 2026-04-15T00:00:00Z AND LoginTime <= 2026-04-22T00:00:00Z
```

## Q2. User enrichment (one query, after Q1)

After Q1 you have a list of `UserId`s. If you need usernames / MFA / profiles — one query:

```sql
SELECT Id, Username, Name, IsActive, Profile.Name, UserRole.Name,
       LastLoginDate, UserType
FROM User
WHERE Id IN ('005xx...', '005xx...')
```

Collect the ID list from the DataFrame: `df['UserId'].unique().tolist()`. Join downstream.

## Q3. Targeted pull by LoginSubType

For "all users with SOAP API / Bulk API / Metadata API" queries:

```sql
SELECT UserId, LoginTime, SourceIp, Status, Application, CountryIso,
       LoginType, LoginSubType, TlsProtocol
FROM LoginHistory
WHERE LoginSubType = 'SOAP API'
  AND LoginTime >= LAST_N_DAYS:30
ORDER BY UserId, LoginTime
LIMIT 20000
```

For multiple subtypes — use `IN` and one query:
```sql
WHERE LoginSubType IN ('SOAP API', 'Bulk API', 'Metadata API')
```

## Q4. Failed-logins focus

When the user explicitly wants only failures (brute force audit):

```sql
SELECT UserId, LoginTime, SourceIp, Status, LoginType, LoginSubType,
       CountryIso, Browser, Platform, Application
FROM LoginHistory
WHERE Status != 'Success'
  AND LoginTime >= LAST_N_DAYS:7
ORDER BY SourceIp, LoginTime
LIMIT 20000
```

## Q5. Date chunking (only when Q1 hit the 20000 limit)

Pattern for multiple queries by week. Do this **only** if Q1 returned exactly 20000 rows — a marker that data was truncated.

```python
# Pseudo-code — in practice each soqlQuery call is a separate tool call
windows = [
    ('2026-04-01T00:00:00Z', '2026-04-08T00:00:00Z'),
    ('2026-04-08T00:00:00Z', '2026-04-15T00:00:00Z'),
    ('2026-04-15T00:00:00Z', '2026-04-22T00:00:00Z'),
]
# For each window — Q1 with substituted dates
# Concat results into one DataFrame via pd.concat
```

Tell the user: "a month exceeds 20000 rows, pulling in N weekly chunks".

## What NOT to do

- ❌ `SELECT COUNT() FROM LoginHistory` as a "probe" — go straight for the data
- ❌ `SELECT Id FROM LoginHistory LIMIT 1` "to verify the schema" — the schema is documented above
- ❌ One query per `LoginSubType` — use `IN`
- ❌ `SELECT ... WHERE UserId = 'X'` for each user in turn — join downstream after one pull
- ❌ A query without `LIMIT` — always set 20000, otherwise timeout risk

## Useful SOQL constructs for LoginHistory

- `LAST_N_DAYS:N` — last N full days + today
- `TODAY`, `YESTERDAY`, `THIS_WEEK`, `LAST_WEEK`, `LAST_N_HOURS:N`
- `CALENDAR_MONTH(LoginTime)`, `CALENDAR_YEAR(LoginTime)` — for aggregations
- `LoginTime >= :someDate` — bind variables, when SOQL runs from Apex (not from MCP)

`LoginHistory` does **not** support:
- `HAVING` on most fields
- `GROUP BY ROLLUP` on `LoginTime`
- Subqueries in `WHERE`

So aggregate downstream (DuckDB or pandas) — faster and more flexible.
