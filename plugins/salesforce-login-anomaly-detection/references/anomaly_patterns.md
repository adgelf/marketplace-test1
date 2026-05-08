# Salesforce Login Anomaly Patterns

Catalog of concrete detectors. For each pattern: what we look for, why it's anomalous, limitations (what can produce false positives), and implementations.

Each pattern includes a **DuckDB SQL** implementation (scales to 15M+ rows by streaming directly from the CSV) and a **pandas** alternative for smaller files or ad-hoc exploration.

All examples assume a normalized schema (camelCase). The scripts handle normalization automatically via `profile_logins.normalize_view()`.

Canonical columns:
`userId, username, loginTime, sourceIp, loginType, loginSubType, status, countryIso, browser, platform, application, clientVersion, tlsProtocol, apiType, apiVersion, networkId`

`loginTime` is a UTC TIMESTAMP.

---

## 1. Impossible Travel

**What we look for:** a single user logging in from two countries more than N km apart within T hours.

**Why anomalous:** physically impossible. Usually: stolen token/password, or VPN.

**False positives:** VPN, Cloudflare Warp, corporate proxies in different regions.

### DuckDB SQL (scales to millions of rows)

```sql
WITH ordered AS (
    SELECT
        userId,
        loginTime,
        sourceIp,
        countryIso,
        LAG(countryIso) OVER (PARTITION BY userId ORDER BY loginTime) AS prevCountry,
        LAG(loginTime) OVER (PARTITION BY userId ORDER BY loginTime) AS prevTime,
        LAG(sourceIp) OVER (PARTITION BY userId ORDER BY loginTime) AS prevIp
    FROM logins
    WHERE status = 'Success' AND countryIso IS NOT NULL
)
SELECT
    userId, prevCountry, countryIso, prevTime, loginTime,
    prevIp, sourceIp,
    EXTRACT(EPOCH FROM (loginTime - prevTime)) / 3600.0 AS hoursDelta
FROM ordered
WHERE prevCountry IS NOT NULL
  AND prevCountry <> countryIso
  AND (loginTime - prevTime) <= INTERVAL '2 hours'
ORDER BY userId, loginTime;
```

After this SQL, join the output with a country-centroid table to compute actual distance. See `scripts/detect_anomalies.py` for the full implementation including haversine distance.

### pandas (small files only)

```python
import pandas as pd
from math import radians, sin, cos, asin, sqrt

COUNTRY_CENTROIDS = {
    'US': (39.8, -98.6), 'SE': (62.0, 15.0), 'GB': (54.0, -2.0),
    'DE': (51.2, 10.4), 'FR': (46.2, 2.2), 'BR': (-14.2, -51.9),
    'IN': (20.6, 78.9), 'SG': (1.3, 103.8), 'AU': (-25.3, 133.8),
    # extend as needed
}

def haversine_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    return 2 * 6371 * asin(sqrt(a))

def detect_impossible_travel(df, min_km=1000, max_hours=2):
    data = df[df['status'] == 'Success'].copy()
    data = data.dropna(subset=['countryIso']).sort_values(['userId', 'loginTime'])
    data['prevCountry'] = data.groupby('userId')['countryIso'].shift()
    data['prevTime'] = data.groupby('userId')['loginTime'].shift()
    data['hoursDelta'] = (data['loginTime'] - data['prevTime']).dt.total_seconds() / 3600

    suspicious = data[
        (data['countryIso'] != data['prevCountry'])
        & data['prevCountry'].notna()
        & (data['hoursDelta'] <= max_hours)
    ].copy()

    def distance(row):
        a = COUNTRY_CENTROIDS.get(row['prevCountry'])
        b = COUNTRY_CENTROIDS.get(row['countryIso'])
        return haversine_km(*a, *b) if a and b else None

    suspicious['distanceKm'] = suspicious.apply(distance, axis=1)
    return suspicious[suspicious['distanceKm'] >= min_km]
```

Presentation: group by `userId`, show `prev → current` pairs with distance and time delta.

---

## 2. Brute Force / Credential Stuffing

**What we look for:** a burst of failed logins from one IP against different usernames, OR against one user from different IPs.

**Why anomalous:** normal users don't forget their password 50 times in 10 minutes; attackers do.

**False positives:** broken integration (stale password in config), script with a wrong keytab.

### DuckDB SQL

```sql
-- Brute force by IP: many failures from same IP across distinct users
WITH failed AS (
    SELECT sourceIp, userId, loginTime
    FROM logins
    WHERE status <> 'Success'
)
SELECT
    sourceIp,
    COUNT(*) AS totalFailures,
    COUNT(DISTINCT userId) AS uniqueUsersTargeted,
    MIN(loginTime) AS firstSeen,
    MAX(loginTime) AS lastSeen
FROM failed
GROUP BY sourceIp
HAVING COUNT(*) >= 10 AND COUNT(DISTINCT userId) >= 3
ORDER BY totalFailures DESC;
```

For a tighter "burst within a window" filter (e.g. 10 minutes), use a window function approach:

```sql
WITH failed AS (
    SELECT sourceIp, userId, loginTime
    FROM logins WHERE status <> 'Success'
),
windowed AS (
    SELECT
        sourceIp, loginTime,
        COUNT(*) OVER (
            PARTITION BY sourceIp
            ORDER BY loginTime
            RANGE BETWEEN INTERVAL '10 minutes' PRECEDING AND CURRENT ROW
        ) AS failuresInWindow,
        COUNT(DISTINCT userId) OVER (
            PARTITION BY sourceIp
            ORDER BY loginTime
            RANGE BETWEEN INTERVAL '10 minutes' PRECEDING AND CURRENT ROW
        ) AS usersInWindow
    FROM failed
)
SELECT sourceIp, MAX(failuresInWindow) AS peakFailures, MAX(usersInWindow) AS peakUsers
FROM windowed
GROUP BY sourceIp
HAVING MAX(failuresInWindow) >= 10 AND MAX(usersInWindow) >= 3
ORDER BY peakFailures DESC;
```

---

## 3. Failed → Success (success after a burst of failures)

**What we look for:** for one user — a run of failed logins followed by a successful one (same or different IP — different is more suspicious).

**Why anomalous:** classic guessed-password signature (or the user genuinely recalled their password — low-severity case).

### DuckDB SQL

```sql
WITH tagged AS (
    SELECT
        userId, loginTime, sourceIp, status,
        CASE WHEN status <> 'Success' THEN 1 ELSE 0 END AS isFail
    FROM logins
),
with_priors AS (
    SELECT
        userId, loginTime, sourceIp, status,
        SUM(isFail) OVER (
            PARTITION BY userId ORDER BY loginTime
            RANGE BETWEEN INTERVAL '30 minutes' PRECEDING AND INTERVAL '1 second' PRECEDING
        ) AS priorFailures30m
    FROM tagged
)
SELECT userId, loginTime AS successTime, sourceIp AS successIp, priorFailures30m
FROM with_priors
WHERE status = 'Success' AND priorFailures30m >= 3
ORDER BY priorFailures30m DESC, successTime;
```

**Severity hint:** if the success IP is different from where the failures came from, it's critical.

---

## 4. New country for a user

**What we look for:** first successful login for a `userId` from a `countryIso` they've never used before.

### DuckDB SQL

```sql
WITH success AS (
    SELECT userId, loginTime, sourceIp, countryIso
    FROM logins
    WHERE status = 'Success' AND countryIso IS NOT NULL
),
max_time AS (SELECT MAX(loginTime) AS maxT FROM success),
baseline AS (
    SELECT DISTINCT userId, countryIso
    FROM success, max_time
    WHERE loginTime < maxT - INTERVAL '90 days'
)
SELECT s.userId, s.loginTime, s.sourceIp, s.countryIso AS newCountry
FROM success s, max_time m
WHERE s.loginTime >= m.maxT - INTERVAL '90 days'
  AND NOT EXISTS (
      SELECT 1 FROM baseline b
      WHERE b.userId = s.userId AND b.countryIso = s.countryIso
  )
  AND EXISTS (
      SELECT 1 FROM baseline b2 WHERE b2.userId = s.userId
  )
ORDER BY s.userId, s.loginTime;
```

---

## 5. API logins by regular (non-integration) users

**What we look for:** `LoginSubType` in {SOAP API, Bulk API, Metadata API, ...} from users whose username does not look like an integration.

**Why anomalous:** usually means Data Loader or a custom script run by a human. Mass data export is a leak risk.

### DuckDB SQL

```sql
SELECT
    username,
    loginSubType,
    COUNT(*) AS logins,
    MIN(loginTime) AS firstSeen,
    MAX(loginTime) AS lastSeen,
    COUNT(DISTINCT sourceIp) AS uniqueIps
FROM logins
WHERE loginSubType IN (
    'SOAP API', 'Bulk API', 'Bulk API 2.0', 'Metadata API',
    'Partner API', 'Enterprise API', 'Tooling API'
)
  AND username IS NOT NULL
  AND NOT regexp_matches(
      lower(username),
      '(integration|svc|service|^api|sys|etl|bot|automation|dataloader|mulesoft|workato|zapier|connector)'
  )
GROUP BY username, loginSubType
ORDER BY logins DESC;
```

Always caveat: the username heuristic isn't ground truth. Ask the user to confirm / extend the integration-user pattern list.

---

## 6. Concurrent sessions from different locations (shared credentials)

**What we look for:** two successful logins for one `userId` from different `countryIso` within a very short window (< 5 min).

Alternative: overlapping sessions via `SESSION_KEY` (Event Monitoring only).

### DuckDB SQL

```sql
WITH ordered AS (
    SELECT
        userId, loginTime, sourceIp, countryIso,
        LAG(countryIso) OVER (PARTITION BY userId ORDER BY loginTime) AS prevCountry,
        LAG(sourceIp) OVER (PARTITION BY userId ORDER BY loginTime) AS prevIp,
        LAG(loginTime) OVER (PARTITION BY userId ORDER BY loginTime) AS prevTime
    FROM logins
    WHERE status = 'Success'
)
SELECT *,
    EXTRACT(EPOCH FROM (loginTime - prevTime)) / 60.0 AS minutesDelta
FROM ordered
WHERE prevCountry IS NOT NULL
  AND prevCountry <> countryIso
  AND (loginTime - prevTime) <= INTERVAL '5 minutes'
ORDER BY userId, loginTime;
```

---

## 7. Logins outside a user's typical hours

**What we look for:** a login at an hour-of-day that this user has almost never used before.

### DuckDB SQL

```sql
WITH hours AS (
    SELECT userId, EXTRACT(HOUR FROM loginTime) AS hourUtc, COUNT(*) AS cnt
    FROM logins
    WHERE status = 'Success'
    GROUP BY userId, EXTRACT(HOUR FROM loginTime)
),
stats AS (
    SELECT userId, AVG(cnt) AS meanCnt, STDDEV_POP(cnt) AS stdCnt
    FROM hours
    GROUP BY userId
    HAVING SUM(cnt) >= 20
)
SELECT
    l.userId, l.loginTime, l.sourceIp,
    EXTRACT(HOUR FROM l.loginTime) AS hourUtc
FROM logins l
JOIN stats s ON l.userId = s.userId
LEFT JOIN hours h ON h.userId = l.userId AND h.hourUtc = EXTRACT(HOUR FROM l.loginTime)
WHERE l.status = 'Success'
  AND s.stdCnt > 0
  AND (s.meanCnt - COALESCE(h.cnt, 0)) / s.stdCnt > 3
ORDER BY l.userId, l.loginTime;
```

---

## 8. Weak TLS / Cipher Suites

**What we look for:** `tlsProtocol` in {TLS 1.0, TLS 1.1} or RC4/DES in `cipherSuite`.

**Why anomalous:** compliance risk (PCI DSS and most regulatory frameworks). Often a legacy integration.

### DuckDB SQL

```sql
SELECT
    userId,
    username,
    tlsProtocol,
    cipherSuite,
    COUNT(*) AS logins
FROM logins
WHERE tlsProtocol IN ('TLSv1', 'TLSv1.1', 'TLS 1.0', 'TLS 1.1')
   OR cipherSuite LIKE '%RC4%'
   OR cipherSuite LIKE '%DES%'
   OR cipherSuite LIKE '%MD5%'
   OR cipherSuite LIKE '%NULL%'
GROUP BY userId, username, tlsProtocol, cipherSuite
ORDER BY logins DESC;
```

---

## 9. Stale accounts waking up

**What we look for:** user inactive for N+ days, then a successful login.

### DuckDB SQL

```sql
WITH gaps AS (
    SELECT
        userId, username, loginTime, sourceIp, countryIso,
        LAG(loginTime) OVER (PARTITION BY userId ORDER BY loginTime) AS prevLogin
    FROM logins
    WHERE status = 'Success'
)
SELECT
    userId, username, prevLogin, loginTime AS wakeUpTime,
    EXTRACT(EPOCH FROM (loginTime - prevLogin)) / 86400.0 AS gapDays,
    sourceIp, countryIso
FROM gaps
WHERE prevLogin IS NOT NULL
  AND (loginTime - prevLogin) >= INTERVAL '90 days'
ORDER BY gapDays DESC;
```

---

## 10. Status spikes

**What we look for:** an unusually high share of a specific failure status in a short window (e.g. `Restricted IP`).

### DuckDB SQL

```sql
WITH bucketed AS (
    SELECT
        date_trunc('hour', loginTime) AS hourBucket,
        status,
        COUNT(*) AS cnt
    FROM logins
    GROUP BY 1, 2
),
stats AS (
    SELECT status, AVG(cnt) AS meanCnt, STDDEV_POP(cnt) AS stdCnt
    FROM bucketed
    GROUP BY status
)
SELECT
    b.hourBucket, b.status, b.cnt,
    (b.cnt - s.meanCnt) / NULLIF(s.stdCnt, 0) AS zscore
FROM bucketed b
JOIN stats s USING (status)
WHERE s.stdCnt > 0 AND (b.cnt - s.meanCnt) / s.stdCnt > 3
ORDER BY zscore DESC;
```

---

## Finding prioritization (severity mapping)

When presenting results, use a rough scale:

| Severity | What lands here |
|---|---|
| **Critical** | Impossible travel + success; failed-then-success from a different IP; active logins by deactivated users; brute force that ends in a success |
| **High** | Brute force without success; new country for a privileged user; humans using Metadata / Bulk API at volume |
| **Medium** | Stale reactivation; new country for a regular user; weak TLS; unusual hours |
| **Info** | Integration summaries, distributions, compliance reviews without specific incidents |

Severity is always a hint, not a hard rule. Org context can shift it in either direction.
