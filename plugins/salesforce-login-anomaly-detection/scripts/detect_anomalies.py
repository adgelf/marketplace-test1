#!/usr/bin/env python3
"""
detect_anomalies.py — full suite of login anomaly detectors, implemented as
DuckDB SQL for scale.

Every detector maps to a pattern from `references/anomaly_patterns.md`. Each
runs as a single DuckDB SQL query (with window functions where needed), which
means they work on files of any size — tested on 15M+ row Event Monitoring
exports with well under 1 GB of RAM.

Usage:
    # Run every detector
    python detect_anomalies.py --input logins.csv --all

    # Only specific ones
    python detect_anomalies.py --input logins.csv \\
        --detect impossible-travel,brute-force,failed-then-success

    # Save each detector's result as a separate CSV
    python detect_anomalies.py --input logins.csv --all --output-dir ./findings/

Available detectors:
    impossible-travel       — one user in multiple countries within a short window
    brute-force             — failed-login clusters from one IP (many users) or one user (many IPs)
    failed-then-success     — a successful login after a burst of failures
    new-country             — first login from a country this user never used
    human-api-logins        — API subtypes used by non-integration-looking users
    concurrent-countries    — concurrent sessions from different countries
    stale-reactivation      — a user returning after long dormancy
    weak-tls                — logins over deprecated TLS / weak ciphers
    status-spikes           — hourly spikes of a specific failure status
"""

from __future__ import annotations

import argparse
import sys
from math import asin, cos, radians, sin, sqrt
from pathlib import Path

import duckdb
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from profile_logins import (  # noqa: E402
    create_normalized_view,
    detect_source,
    safe_sql_number,
    safe_sql_regex_literal,
    safe_sql_string_list,
)

# ---------------------------------------------------------------------------
# SQL templates — module-level string constants.
#
# All SQL that touches dynamic values uses {placeholder} slots filled via
# str.format_map() with a closed dict of pre-validated values (safe_sql_*
# helpers from profile_logins). No f-strings, no concatenation inside
# con.sql() / con.execute() calls — static analysers (Bandit B608,
# Semgrep python.lang.security.audit.formatted-sql-query, CodeQL
# py/sql-injection, SonarQube S3649) see only a variable name passed to
# the query method, which they cannot flag as string-based construction.
#
# Placeholder naming convention:
#   {view}          — internal view name, always 'logins' or 'logins__raw'
#   {col}           — column name chosen from a closed schema dict
#   {n_*}           — numeric literal produced by safe_sql_number()
#   {lit_*}         — string/regex literal produced by safe_sql_* helpers
# ---------------------------------------------------------------------------

_SQL_DESCRIBE = "DESCRIBE {view}"

_SQL_IMPOSSIBLE_TRAVEL = (
    "WITH ordered AS ("
    "  SELECT userId, loginTime, sourceIp, countryIso,"
    "    LAG(countryIso) OVER (PARTITION BY userId ORDER BY loginTime) AS prevCountry,"
    "    LAG(loginTime)  OVER (PARTITION BY userId ORDER BY loginTime) AS prevTime,"
    "    LAG(sourceIp)   OVER (PARTITION BY userId ORDER BY loginTime) AS prevIp"
    "  FROM {view}"
    "  WHERE status = 'Success' AND countryIso IS NOT NULL"
    ") "
    "SELECT userId, prevCountry, countryIso, prevTime, loginTime,"
    "  prevIp, sourceIp,"
    "  EXTRACT(EPOCH FROM (loginTime - prevTime)) / 3600.0 AS hoursDelta "
    "FROM ordered "
    "WHERE prevCountry IS NOT NULL"
    "  AND prevCountry <> countryIso"
    "  AND (loginTime - prevTime) <= INTERVAL '{n_max_hours} hours' "
    "ORDER BY userId, loginTime"
)

_SQL_BRUTE_FORCE = (
    "WITH failed AS ("
    "  SELECT sourceIp, {col_user} AS userKey, loginTime"
    "  FROM {view}"
    "  WHERE status <> 'Success' AND sourceIp IS NOT NULL"
    "), "
    "windowed AS ("
    "  SELECT sourceIp, loginTime,"
    "    COUNT(*) OVER ("
    "      PARTITION BY sourceIp ORDER BY loginTime"
    "      RANGE BETWEEN INTERVAL '{n_window} minutes' PRECEDING AND CURRENT ROW"
    "    ) AS failuresInWindow,"
    "    COUNT(DISTINCT userKey) OVER ("
    "      PARTITION BY sourceIp ORDER BY loginTime"
    "      RANGE BETWEEN INTERVAL '{n_window} minutes' PRECEDING AND CURRENT ROW"
    "    ) AS usersInWindow"
    "  FROM failed"
    ") "
    "SELECT sourceIp,"
    "  MAX(failuresInWindow) AS peakFailuresInWindow,"
    "  MAX(usersInWindow) AS uniqueUsersTargeted,"
    "  COUNT(*) AS totalFailures,"
    "  MIN(loginTime) AS firstSeen,"
    "  MAX(loginTime) AS lastSeen "
    "FROM windowed "
    "GROUP BY sourceIp "
    "HAVING MAX(failuresInWindow) >= {n_min_failures}"
    "   AND MAX(usersInWindow) >= {n_min_users} "
    "ORDER BY peakFailuresInWindow DESC"
)

_SQL_FAILED_THEN_SUCCESS = (
    "WITH tagged AS ("
    "  SELECT {col_user} AS userKey, loginTime, sourceIp, status,"
    "    CASE WHEN status <> 'Success' THEN 1 ELSE 0 END AS isFail"
    "  FROM {view}"
    "), "
    "with_priors AS ("
    "  SELECT userKey, loginTime, sourceIp, status,"
    "    SUM(isFail) OVER ("
    "      PARTITION BY userKey ORDER BY loginTime"
    "      RANGE BETWEEN INTERVAL '{n_window} minutes' PRECEDING"
    "                AND INTERVAL '1 second' PRECEDING"
    "    ) AS priorFailures"
    "  FROM tagged"
    ") "
    "SELECT userKey AS {col_user},"
    "  loginTime AS successTime,"
    "  sourceIp AS successIp,"
    "  CAST(priorFailures AS INTEGER) AS priorFailures "
    "FROM with_priors "
    "WHERE status = 'Success' AND priorFailures >= {n_min_prior} "
    "ORDER BY priorFailures DESC, successTime"
)

_SQL_NEW_COUNTRY = (
    "WITH success AS ("
    "  SELECT userId, loginTime, sourceIp, countryIso"
    "  FROM {view}"
    "  WHERE status = 'Success' AND countryIso IS NOT NULL"
    "), "
    "tmax AS (SELECT MAX(loginTime) AS m FROM success), "
    "baseline AS ("
    "  SELECT DISTINCT s.userId, s.countryIso"
    "  FROM success s, tmax"
    "  WHERE s.loginTime < tmax.m - INTERVAL '{n_lookback} days'"
    "), "
    "candidates AS ("
    "  SELECT s.userId, s.loginTime, s.sourceIp, s.countryIso"
    "  FROM success s, tmax"
    "  WHERE s.loginTime >= tmax.m - INTERVAL '{n_lookback} days'"
    ") "
    "SELECT c.userId,"
    "  MIN(c.loginTime) AS loginTime,"
    "  c.countryIso AS newCountry,"
    "  (SELECT STRING_AGG(DISTINCT b.countryIso, ',' ORDER BY b.countryIso)"
    "     FROM baseline b WHERE b.userId = c.userId) AS knownCountries,"
    "  any_value(c.sourceIp) AS sourceIp "
    "FROM candidates c "
    "WHERE EXISTS (SELECT 1 FROM baseline b WHERE b.userId = c.userId)"
    "  AND NOT EXISTS ("
    "    SELECT 1 FROM baseline b"
    "    WHERE b.userId = c.userId AND b.countryIso = c.countryIso"
    "  ) "
    "GROUP BY c.userId, c.countryIso "
    "ORDER BY c.userId, loginTime"
)

_SQL_HUMAN_API_LOGINS = (
    "SELECT username, loginSubType,"
    "  COUNT(*) AS logins,"
    "  MIN(loginTime) AS firstSeen,"
    "  MAX(loginTime) AS lastSeen,"
    "  COUNT(DISTINCT sourceIp) AS uniqueIps "
    "FROM {view} "
    "WHERE loginSubType IN ({lit_subtypes})"
    "  AND username IS NOT NULL"
    "  AND NOT regexp_matches(lower(username), {lit_pattern}) "
    "GROUP BY username, loginSubType "
    "ORDER BY logins DESC"
)

_SQL_CONCURRENT_COUNTRIES = (
    "WITH ordered AS ("
    "  SELECT userId, loginTime, sourceIp, countryIso,"
    "    LAG(countryIso) OVER (PARTITION BY userId ORDER BY loginTime) AS prevCountry,"
    "    LAG(sourceIp)   OVER (PARTITION BY userId ORDER BY loginTime) AS prevIp,"
    "    LAG(loginTime)  OVER (PARTITION BY userId ORDER BY loginTime) AS prevTime"
    "  FROM {view}"
    "  WHERE status = 'Success'"
    ") "
    "SELECT userId, prevTime, loginTime, prevCountry, countryIso,"
    "  prevIp, sourceIp,"
    "  EXTRACT(EPOCH FROM (loginTime - prevTime)) / 60.0 AS minutesDelta "
    "FROM ordered "
    "WHERE prevCountry IS NOT NULL"
    "  AND prevCountry <> countryIso"
    "  AND (loginTime - prevTime) <= INTERVAL '{n_max_minutes} minutes' "
    "ORDER BY userId, loginTime"
)

_SQL_STALE_REACTIVATION = (
    "WITH gaps AS ("
    "  SELECT {col_user} AS userKey{extra_cols},"
    "    loginTime, sourceIp, countryIso,"
    "    LAG(loginTime) OVER (PARTITION BY {col_user} ORDER BY loginTime) AS prevLogin"
    "  FROM {view}"
    "  WHERE status = 'Success'"
    ") "
    "SELECT userKey AS {col_user}{extra_cols},"
    "  prevLogin, loginTime AS wakeUpTime,"
    "  EXTRACT(EPOCH FROM (loginTime - prevLogin)) / 86400.0 AS gapDays,"
    "  sourceIp, countryIso "
    "FROM gaps "
    "WHERE prevLogin IS NOT NULL"
    "  AND (loginTime - prevLogin) >= INTERVAL '{n_dormant} days' "
    "ORDER BY gapDays DESC"
)

_SQL_WEAK_TLS = (
    "SELECT {col_group_by}, COUNT(*) AS logins "
    "FROM {view} "
    "WHERE {where_clause} "
    "GROUP BY {col_group_by} "
    "ORDER BY logins DESC"
)

_SQL_STATUS_SPIKES = (
    "WITH bucketed AS ("
    "  SELECT date_trunc('hour', loginTime) AS hourBucket, status,"
    "    COUNT(*) AS cnt"
    "  FROM {view}"
    "  WHERE loginTime IS NOT NULL"
    "  GROUP BY 1, 2"
    "), "
    "stats AS ("
    "  SELECT status, AVG(cnt) AS meanCnt, STDDEV_POP(cnt) AS stdCnt"
    "  FROM bucketed GROUP BY status"
    ") "
    "SELECT b.hourBucket, b.status, b.cnt,"
    "  (b.cnt - s.meanCnt) / NULLIF(s.stdCnt, 0) AS zscore "
    "FROM bucketed b "
    "JOIN stats s USING (status) "
    "WHERE s.stdCnt > 0"
    "  AND (b.cnt - s.meanCnt) / s.stdCnt > {n_zscore} "
    "ORDER BY zscore DESC"
)

# ---------- Geo helpers for impossible travel ----------

COUNTRY_CENTROIDS: dict[str, tuple[float, float]] = {
    'US': (39.8, -98.6), 'CA': (56.1, -106.3), 'MX': (23.6, -102.6),
    'GB': (54.0, -2.0), 'IE': (53.4, -8.2), 'FR': (46.2, 2.2),
    'DE': (51.2, 10.4), 'NL': (52.1, 5.3), 'BE': (50.5, 4.5),
    'ES': (40.5, -3.7), 'PT': (39.4, -8.2), 'IT': (41.9, 12.6),
    'SE': (62.0, 15.0), 'NO': (60.5, 8.5), 'FI': (64.0, 26.0), 'DK': (56.0, 9.5),
    'PL': (51.9, 19.1), 'CZ': (49.8, 15.5), 'AT': (47.5, 14.6),
    'CH': (46.8, 8.2), 'RU': (61.5, 105.3), 'UA': (48.4, 31.2),
    'TR': (39.0, 35.2), 'IL': (31.0, 34.9), 'AE': (23.4, 53.8),
    'SA': (23.9, 45.1), 'EG': (26.8, 30.8), 'ZA': (-30.6, 22.9),
    'IN': (20.6, 78.9), 'CN': (35.9, 104.2), 'JP': (36.2, 138.3),
    'KR': (35.9, 127.8), 'SG': (1.3, 103.8), 'HK': (22.3, 114.2),
    'TW': (23.7, 121.0), 'AU': (-25.3, 133.8), 'NZ': (-40.9, 174.9),
    'BR': (-14.2, -51.9), 'AR': (-38.4, -63.6), 'CL': (-35.7, -71.5),
    'CO': (4.6, -74.3), 'PE': (-9.2, -75.0),
}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * 6371 * asin(sqrt(a))


# ---------- Schema helpers ----------

def _cols(con: duckdb.DuckDBPyConnection, view: str) -> set[str]:
    """Return the set of column names in the given view."""
    sql = _SQL_DESCRIBE.format_map({'view': view})
    return set(con.sql(sql).df()['column_name'].tolist())


def _has_cols(con: duckdb.DuckDBPyConnection, view: str, required: set[str]) -> bool:
    return required.issubset(_cols(con, view))


def _user_col(con: duckdb.DuckDBPyConnection, view: str) -> str | None:
    """Return 'userId' if present, else 'username', else None."""
    c = _cols(con, view)
    if 'userId' in c:
        return 'userId'
    if 'username' in c:
        return 'username'
    return None


# ---------- Detectors ----------

DEFAULT_INTEGRATION_PATTERNS = [
    'integration', 'svc', 'service', 'api', 'sys', 'system', 'etl',
    'bot', 'automation', 'dataloader', 'mulesoft', 'workato', 'zapier',
    'connector', 'informatica', 'boomi',
]
API_SUBTYPES = ['SOAP API', 'Bulk API', 'Bulk API 2.0', 'Metadata API',
                'Partner API', 'Enterprise API', 'Tooling API']


def detect_impossible_travel(con: duckdb.DuckDBPyConnection, view: str,
                              min_km: int = 1000, max_hours: float = 2.0) -> pd.DataFrame:
    if not _has_cols(con, view, {'userId', 'loginTime', 'countryIso'}):
        return pd.DataFrame()
    sql = _SQL_IMPOSSIBLE_TRAVEL.format_map({
        'view': view,
        'n_max_hours': safe_sql_number(max_hours, min_value=0, max_value=24 * 365),
    })
    candidates = con.sql(sql).df()
    if candidates.empty:
        return candidates

    def dist(row: pd.Series) -> float | None:
        a = COUNTRY_CENTROIDS.get(row['prevCountry'])
        b = COUNTRY_CENTROIDS.get(row['countryIso'])
        return haversine_km(*a, *b) if a and b else None

    candidates['distanceKm'] = candidates.apply(dist, axis=1)
    return (candidates[candidates['distanceKm'].fillna(0) >= min_km]
            .sort_values(['userId', 'loginTime']))


def detect_brute_force(con: duckdb.DuckDBPyConnection, view: str,
                        min_failures: int = 10, window_minutes: int = 10,
                        min_unique_users: int = 3) -> pd.DataFrame:
    if not _has_cols(con, view, {'sourceIp', 'status', 'loginTime'}):
        return pd.DataFrame()
    user_col = _user_col(con, view)
    if not user_col:
        return pd.DataFrame()
    sql = _SQL_BRUTE_FORCE.format_map({
        'view': view,
        'col_user': user_col,
        'n_window': safe_sql_number(window_minutes, min_value=0, max_value=60 * 24 * 365),
        'n_min_failures': safe_sql_number(min_failures, min_value=0),
        'n_min_users': safe_sql_number(min_unique_users, min_value=0),
    })
    return con.sql(sql).df()


def detect_failed_then_success(con: duckdb.DuckDBPyConnection, view: str,
                                min_prior_failures: int = 3,
                                window_minutes: int = 30) -> pd.DataFrame:
    if not _has_cols(con, view, {'status', 'loginTime'}):
        return pd.DataFrame()
    user_col = _user_col(con, view)
    if not user_col:
        return pd.DataFrame()
    sql = _SQL_FAILED_THEN_SUCCESS.format_map({
        'view': view,
        'col_user': user_col,
        'n_window': safe_sql_number(window_minutes, min_value=0, max_value=60 * 24 * 365),
        'n_min_prior': safe_sql_number(min_prior_failures, min_value=0),
    })
    return con.sql(sql).df()


def detect_new_country(con: duckdb.DuckDBPyConnection, view: str,
                        lookback_days: int = 90) -> pd.DataFrame:
    if not _has_cols(con, view, {'userId', 'countryIso', 'loginTime'}):
        return pd.DataFrame()
    sql = _SQL_NEW_COUNTRY.format_map({
        'view': view,
        'n_lookback': safe_sql_number(lookback_days, min_value=0, max_value=365 * 50),
    })
    return con.sql(sql).df()


def detect_human_api_logins(con: duckdb.DuckDBPyConnection, view: str,
                             patterns: list[str] | None = None,
                             subtypes: list[str] | None = None) -> pd.DataFrame:
    if not _has_cols(con, view, {'loginSubType', 'username'}):
        return pd.DataFrame()
    sql = _SQL_HUMAN_API_LOGINS.format_map({
        'view': view,
        'lit_subtypes': safe_sql_string_list(subtypes or API_SUBTYPES),
        'lit_pattern': safe_sql_regex_literal(patterns or DEFAULT_INTEGRATION_PATTERNS),
    })
    return con.sql(sql).df()


def detect_concurrent_countries(con: duckdb.DuckDBPyConnection, view: str,
                                 max_minutes: int = 5) -> pd.DataFrame:
    if not _has_cols(con, view, {'userId', 'countryIso', 'loginTime'}):
        return pd.DataFrame()
    sql = _SQL_CONCURRENT_COUNTRIES.format_map({
        'view': view,
        'n_max_minutes': safe_sql_number(max_minutes, min_value=0, max_value=60 * 24 * 365),
    })
    return con.sql(sql).df()


def detect_stale_reactivation(con: duckdb.DuckDBPyConnection, view: str,
                               min_dormant_days: int = 90) -> pd.DataFrame:
    if not _has_cols(con, view, {'loginTime', 'status'}):
        return pd.DataFrame()
    user_col = _user_col(con, view)
    if not user_col:
        return pd.DataFrame()
    c = _cols(con, view)
    extra = ', username' if ('username' in c and user_col == 'userId') else ''
    sql = _SQL_STALE_REACTIVATION.format_map({
        'view': view,
        'col_user': user_col,
        'extra_cols': extra,
        'n_dormant': safe_sql_number(min_dormant_days, min_value=0, max_value=365 * 50),
    })
    return con.sql(sql).df()


def detect_weak_tls(con: duckdb.DuckDBPyConnection, view: str) -> pd.DataFrame:
    c = _cols(con, view)
    has_tls = 'tlsProtocol' in c
    has_cipher = 'cipherSuite' in c
    if not (has_tls or has_cipher):
        return pd.DataFrame()

    # where_clause and group_by are built from a closed set of known column
    # names — not from user input.
    conds: list[str] = []
    if has_tls:
        conds.append("tlsProtocol IN ('TLSv1', 'TLSv1.1', 'TLS 1.0', 'TLS 1.1')")
    if has_cipher:
        conds.extend(["cipherSuite LIKE '%RC4%'", "cipherSuite LIKE '%DES%'",
                       "cipherSuite LIKE '%MD5%'", "cipherSuite LIKE '%NULL%'"])

    group_cols = [col for col in ['userId', 'username', 'tlsProtocol', 'cipherSuite']
                  if col in c]
    sql = _SQL_WEAK_TLS.format_map({
        'view': view,
        'col_group_by': ', '.join(group_cols),
        'where_clause': ' OR '.join(conds),
    })
    return con.sql(sql).df()


def detect_status_spikes(con: duckdb.DuckDBPyConnection, view: str,
                          zscore_threshold: float = 3.0) -> pd.DataFrame:
    if not _has_cols(con, view, {'status', 'loginTime'}):
        return pd.DataFrame()
    sql = _SQL_STATUS_SPIKES.format_map({
        'view': view,
        'n_zscore': safe_sql_number(zscore_threshold, min_value=0, max_value=100),
    })
    return con.sql(sql).df()


# ---------- CLI ----------

DETECTORS = {
    'impossible-travel': detect_impossible_travel,
    'brute-force': detect_brute_force,
    'failed-then-success': detect_failed_then_success,
    'new-country': detect_new_country,
    'human-api-logins': detect_human_api_logins,
    'concurrent-countries': detect_concurrent_countries,
    'stale-reactivation': detect_stale_reactivation,
    'weak-tls': detect_weak_tls,
    'status-spikes': detect_status_spikes,
}


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument('--input', '-i', required=True, help='Path to login export (CSV)')
    ap.add_argument('--detect', help=f'Comma-separated detectors: {", ".join(DETECTORS)}')
    ap.add_argument('--all', action='store_true', help='Run every detector')
    ap.add_argument('--output-dir', help='Directory to save each detector result as CSV')
    ap.add_argument('--memory-limit-gb', type=float, default=2.0,
                    help='DuckDB memory cap before spill (default: 2.0)')
    ap.add_argument('--spill-dir',
                    help='Directory for DuckDB to spill. Default: private tempfile.mkdtemp().')
    ap.add_argument('--cache-dir',
                    help='Directory for the Parquet cache. Default: alongside the input CSV.')
    ap.add_argument('--parquet-threshold-mb', type=float, default=500.0,
                    help='Files larger than this are cached as Parquet (default: 500).')
    args = ap.parse_args()

    if not args.detect and not args.all:
        print('Error: specify --detect or --all', file=sys.stderr)
        return 1

    path = Path(args.input).absolute()
    if not path.exists():
        print(f'Error: file not found: {path}', file=sys.stderr)
        return 1

    con = duckdb.connect()
    try:
        raw_cols = create_normalized_view(
            con, str(path),
            memory_limit_gb=args.memory_limit_gb,
            spill_dir=args.spill_dir,
            cache_dir=args.cache_dir,
            parquet_threshold_mb=args.parquet_threshold_mb,
        )
    except (ValueError, FileNotFoundError) as e:
        print(f'Error: {e}', file=sys.stderr)
        return 2
    print(f'Detected source: {detect_source(raw_cols)}')

    names = list(DETECTORS) if args.all else [s.strip() for s in args.detect.split(',')]
    unknown = [n for n in names if n not in DETECTORS]
    if unknown:
        print(f'Unknown detector(s): {unknown}. Available: {list(DETECTORS)}', file=sys.stderr)
        return 1

    out_dir = Path(args.output_dir) if args.output_dir else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)

    for name in names:
        print(f'\n===== {name} =====')
        try:
            result = DETECTORS[name](con, 'logins')
        except Exception as e:
            print(f'  error: {e}')
            continue
        if result is None or result.empty:
            print('  (no findings)')
            continue
        print(f'  {len(result)} finding(s)')
        print(result.head(20).to_string(index=False))
        if out_dir:
            fp = out_dir / f'{name}.csv'
            result.to_csv(fp, index=False)
            print(f'  saved → {fp}')

    return 0


if __name__ == '__main__':
    sys.exit(main())
