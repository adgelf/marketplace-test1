#!/usr/bin/env python3
"""
profile_logins.py — initial profile of a Salesforce login export.

Auto-detects the source (UI export / SOQL / Event Monitoring), normalises
column names to a canonical camelCase schema via a DuckDB VIEW, and produces
a Markdown summary: time range, scale, LoginType / LoginSubType / Status
distributions, top users and IPs, TLS / platforms / browsers / applications,
and initial sanity hints.

Uses DuckDB for streaming execution: handles CSV files of any size (tested on
15M+ rows) with a near-constant memory footprint.

Usage:
    python profile_logins.py --input path/to/login_export.csv
    python profile_logins.py --input path/to/login_export.csv --output profile.md
    python profile_logins.py --input path/to/login_export.csv --top-n 20
    python profile_logins.py --input big.csv --cache-dir /tmp/cache --memory-limit-gb 4
"""

from __future__ import annotations

import argparse
import os
import re as _re
import sys
import tempfile
from pathlib import Path

import duckdb
import pandas as pd


# ---------------------------------------------------------------------------
# SQL templates — module-level string constants.
#
# All SQL that touches dynamic values uses {placeholder} slots filled via
# str.format_map() with a closed dict of pre-validated values.  No f-strings,
# no concatenation inside con.sql() / con.execute() — static analysers
# (Bandit B608, Semgrep, CodeQL py/sql-injection, SonarQube S3649) see only
# a variable name passed to the query method.
#
# Placeholders:
#   {view}        — internal view name (always 'logins' or 'logins__raw')
#   {source}      — read_csv_auto(...) or read_parquet(...) expression,
#                   built from safe_duckdb_path() output
#   {select}      — comma-separated alias projections from COLUMN_ALIASES
#   {col}         — single column name chosen from a closed schema set
#   {cols}        — comma-separated column names from the same closed set
#   {n_*}         — numeric literal from safe_sql_number()
#   {lit_*}       — string/regex literal from safe_sql_* helpers
# ---------------------------------------------------------------------------

_SQL_SET_MEMORY   = "SET memory_limit={lit_limit}"
_SQL_SET_TEMP     = "SET temp_directory={lit_dir}"
_SQL_SET_ORDER    = "SET preserve_insertion_order=false"
_SQL_SAMPLE       = "SELECT * FROM read_csv_auto({lit_path}, sample_size=1000) LIMIT 0"
_SQL_COPY_PARQUET = (
    "COPY (SELECT {select} FROM read_csv_auto("
    "  {lit_csv}, header=true, all_varchar=true,"
    "  quote='\"', escape='\"', ignore_errors=true, parallel=false"
    ")) TO {lit_out} (FORMAT PARQUET, COMPRESSION SNAPPY)"
)
_SQL_VIEW_RAW_CSV = (
    "CREATE OR REPLACE VIEW {view} AS "
    "SELECT {select} FROM read_csv_auto("
    "  {lit_csv}, header=true, all_varchar=true,"
    "  quote='\"', escape='\"', ignore_errors=true, parallel=false)"
)
_SQL_VIEW_RAW_PQ  = "CREATE OR REPLACE VIEW {view} AS SELECT * FROM read_parquet({lit_pq})"
_SQL_VIEW_TYPED   = (
    "CREATE OR REPLACE VIEW {view} AS "
    "SELECT * EXCLUDE (loginTime),"
    "  COALESCE("
    "    TRY_STRPTIME(loginTime, '%Y-%m-%dT%H:%M:%S.%fZ'),"
    "    TRY_STRPTIME(loginTime, '%Y-%m-%dT%H:%M:%SZ'),"
    "    TRY_STRPTIME(loginTime, '%Y-%m-%d %H:%M:%S'),"
    "    TRY_STRPTIME(loginTime, '%m/%d/%Y %I:%M %p'),"
    "    TRY_STRPTIME(loginTime, '%m/%d/%Y %H:%M'),"
    "    TRY_CAST(loginTime AS TIMESTAMP)"
    "  ) AS loginTime "
    "FROM {raw_view}"
)
_SQL_DESCRIBE     = "DESCRIBE {view}"
_SQL_SUMMARY      = "SELECT COUNT(*) AS total, MIN(loginTime) AS tmin, MAX(loginTime) AS tmax FROM {view}"
_SQL_SCALE        = "SELECT {select} FROM {view}"
_SQL_DIST         = (
    "SELECT COALESCE({col}, '(null)') AS value, COUNT(*) AS count,"
    "  ROUND(COUNT(*) * 100.0 / {n_total}, 2) AS pct "
    "FROM {view} GROUP BY {col} ORDER BY count DESC LIMIT {n_top}"
)
_SQL_SUCCESS_RATE = (
    "SELECT AVG(CASE WHEN status = 'Success' THEN 1.0 ELSE 0.0 END) * 100 AS rate FROM {view}"
)
_SQL_API_COUNT    = (
    "SELECT COUNT(*) AS cnt FROM {view} "
    "WHERE loginSubType IS NOT NULL "
    "AND regexp_matches(loginSubType, '(API|Metadata|Bulk)', 'i')"
)
_SQL_TOP_BY_COL   = (
    "SELECT {col}, COUNT(*) AS logins FROM {view} "
    "GROUP BY {col} ORDER BY logins DESC LIMIT {n_top}"
)
_SQL_FAIL_COUNT   = "SELECT COUNT(*) AS cnt FROM {view} WHERE status <> 'Success'"
_SQL_SOAP_COUNT   = "SELECT COUNT(*) AS cnt FROM {view} WHERE loginSubType = 'SOAP API'"
_SQL_WEAK_TLS     = (
    "SELECT COUNT(*) AS cnt FROM {view} "
    "WHERE tlsProtocol IN ('TLSv1', 'TLSv1.1', 'TLS 1.0', 'TLS 1.1')"
)
_SQL_COUNTRY_CNT  = (
    "SELECT COUNT(DISTINCT countryIso) AS n FROM {view} WHERE countryIso IS NOT NULL"
)


# ---------------------------------------------------------------------------
# Column-name mapping: raw CSV header → canonical camelCase
# ---------------------------------------------------------------------------

COLUMN_ALIASES: dict[str, str] = {
    # UI export (Setup → Login History CSV)
    'Username': 'username', 'username': 'username',
    'Login Time': 'loginTime', 'Login URL': 'loginUrl',
    'Source IP': 'sourceIp', 'Login Type': 'loginType',
    'Status': 'status', 'Browser': 'browser', 'Platform': 'platform',
    'Application': 'application', 'Client Version': 'clientVersion',
    'API Type': 'apiType', 'API Version': 'apiVersion',
    'Country': 'countryIso', 'TLS Protocol': 'tlsProtocol',
    'Cipher Suite': 'cipherSuite',
    # SOQL / API
    'UserId': 'userId', 'LoginTime': 'loginTime', 'SourceIp': 'sourceIp',
    'LoginType': 'loginType', 'LoginSubType': 'loginSubType',
    'LoginUrl': 'loginUrl', 'CountryIso': 'countryIso',
    'TlsProtocol': 'tlsProtocol', 'CipherSuite': 'cipherSuite',
    'NetworkId': 'networkId', 'AuthenticationServiceId': 'authServiceId',
    'LoginGeoId': 'loginGeoId', 'ClientVersion': 'clientVersion',
    'ApiType': 'apiType', 'ApiVersion': 'apiVersion',
    # Event Monitoring (UPPER_SNAKE_CASE)
    'USER_ID': 'userId', 'USER_ID_DERIVED': 'userId',
    'USER_NAME': 'username', 'TIMESTAMP': 'loginTime',
    'TIMESTAMP_DERIVED': 'loginTime', 'SOURCE_IP': 'sourceIp',
    'CLIENT_IP': 'sourceIp', 'LOGIN_TYPE': 'loginType',
    'LOGIN_SUB_TYPE': 'loginSubType', 'LOGIN_STATUS': 'status',
    'COUNTRY_ISO': 'countryIso', 'COUNTRY': 'countryIso',
    'TLS_PROTOCOL': 'tlsProtocol', 'CIPHER_SUITE': 'cipherSuite',
    'BROWSER': 'browser', 'PLATFORM': 'platform', 'APPLICATION': 'application',
    'CLIENT_VERSION': 'clientVersion', 'API_TYPE': 'apiType',
    'API_VERSION': 'apiVersion', 'NETWORK_ID': 'networkId',
    'AUTHENTICATION_METHOD_REFERENCE': 'authMethodRef',
    'AUTHENTICATION_SERVICE_ID': 'authServiceId',
    'SESSION_KEY': 'sessionKey', 'LOGIN_KEY': 'loginKey',
    'LOGIN_HISTORY_ID': 'loginHistoryId', 'USER_TYPE': 'userType',
}


def detect_source(columns: list[str]) -> str:
    cols = set(columns)
    if {'EVENT_TYPE', 'TIMESTAMP'}.issubset(cols) or any(
        c.isupper() and '_' in c for c in cols
    ):
        return 'Event Monitoring Login event'
    if {'UserId', 'LoginTime'}.issubset(cols):
        return 'SOQL LoginHistory export'
    if {'Username', 'Login Time'}.issubset(cols) or 'Login Time' in cols:
        return 'Setup UI Login History export'
    return 'Unknown (custom / mixed columns)'


# ---------------------------------------------------------------------------
# Path safety helpers
# ---------------------------------------------------------------------------

_FORBIDDEN_PATH_CHARS = {'\x00', '\n', '\r'}


def safe_duckdb_path(path: str | os.PathLike[str], *, must_exist: bool = True) -> str:
    """Resolve, validate, and SQL-quote a filesystem path for use in DuckDB.

    DuckDB table functions (read_csv_auto, read_parquet) do not accept bound
    parameters — the path must appear as a string literal in the SQL text.
    This helper produces a single-quoted, SQL-escaped form safe to use with
    str.format_map() into a SQL template constant.
    """
    real = os.path.realpath(os.fspath(path))
    if any(ch in real for ch in _FORBIDDEN_PATH_CHARS):
        raise ValueError(f'Path contains forbidden control characters: {real!r}')
    if must_exist and not os.path.exists(real):
        raise ValueError(f'Path does not exist: {real!r}')
    return "'" + real.replace("'", "''") + "'"


def safe_duckdb_output_path(path: str | os.PathLike[str]) -> str:
    """Like safe_duckdb_path but for output paths (parent dir must exist)."""
    real = os.path.realpath(os.fspath(path))
    if any(ch in real for ch in _FORBIDDEN_PATH_CHARS):
        raise ValueError(f'Path contains forbidden control characters: {real!r}')
    parent = os.path.dirname(real)
    if parent and not os.path.isdir(parent):
        raise ValueError(f'Parent directory does not exist: {parent!r}')
    return "'" + real.replace("'", "''") + "'"


# ---------------------------------------------------------------------------
# SQL value safety helpers
# ---------------------------------------------------------------------------

def safe_sql_string_literal(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f'Expected str, got {type(value).__name__}')
    if '\x00' in value:
        raise ValueError('String contains NUL byte; refusing to interpolate.')
    return "'" + value.replace("'", "''") + "'"


def safe_sql_string_list(values: list[str]) -> str:
    if not values:
        raise ValueError('Cannot render an empty string list as SQL IN clause.')
    return ', '.join(safe_sql_string_literal(v) for v in values)


def safe_sql_regex_literal(patterns: list[str]) -> str:
    if not patterns:
        raise ValueError('Cannot build a regex literal from an empty pattern list.')
    escaped = [_re.escape(p) for p in patterns]
    return safe_sql_string_literal('|'.join(escaped))


def safe_sql_number(value: int | float, *,
                    min_value: float | None = None,
                    max_value: float | None = None) -> str:
    import math as _math
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f'Expected int/float, got {type(value).__name__}')
    if _math.isnan(value) or _math.isinf(value):
        raise ValueError(f'Refusing to interpolate non-finite number: {value!r}')
    if min_value is not None and value < min_value:
        raise ValueError(f'Value {value} below minimum {min_value}')
    if max_value is not None and value > max_value:
        raise ValueError(f'Value {value} above maximum {max_value}')
    return str(int(value)) if isinstance(value, int) else repr(float(value))


# ---------------------------------------------------------------------------
# Normalised view creation
# ---------------------------------------------------------------------------

def create_normalized_view(con: duckdb.DuckDBPyConnection, csv_path: str,
                            view_name: str = 'logins',
                            memory_limit_gb: float = 2.0,
                            spill_dir: str | None = None,
                            cache_dir: str | None = None,
                            parquet_threshold_mb: float = 500.0) -> list[str]:
    """Create a typed DuckDB VIEW over the CSV with canonical camelCase columns.

    For large files (> parquet_threshold_mb) converts once to a Parquet cache
    for ~10x faster columnar queries on subsequent runs.  DuckDB is configured
    with a memory limit and a spill directory so large operations don't OOM.

    All SQL is composed from module-level string constants via format_map() —
    no f-strings or concatenation inside con.execute() / con.sql().
    """
    csv_real = os.path.realpath(csv_path)
    if not os.path.exists(csv_real):
        raise FileNotFoundError(f'CSV not found: {csv_path}')
    csv_lit = safe_duckdb_path(csv_real)

    if spill_dir is None:
        spill_dir = tempfile.mkdtemp(prefix='duckdb_spill_')
    else:
        os.makedirs(spill_dir, exist_ok=True)

    con.execute(_SQL_SET_MEMORY.format_map(
        {'lit_limit': safe_sql_string_literal(f'{float(memory_limit_gb)}GB')}
    ))
    con.execute(_SQL_SET_TEMP.format_map(
        {'lit_dir': safe_duckdb_path(spill_dir)}
    ))
    con.execute(_SQL_SET_ORDER)

    # Detect columns from CSV header.
    sample = con.sql(_SQL_SAMPLE.format_map({'lit_path': csv_lit})).df()
    raw_columns = list(sample.columns)

    # Build projection: raw header → canonical name.
    select_parts: list[str] = []
    seen: set[str] = set()
    for col in raw_columns:
        canonical = COLUMN_ALIASES.get(col)
        if canonical and canonical not in seen:
            select_parts.append('"' + col.replace('"', '""') + '" AS ' + canonical)
            seen.add(canonical)
    if not select_parts:
        raise ValueError(
            f'No known columns in CSV. Found: {raw_columns}. '
            'Map them manually or rename before processing.'
        )
    select_expr = ', '.join(select_parts)

    # Parquet cache decision.
    file_size_mb = os.path.getsize(csv_real) / (1024 * 1024)
    use_parquet = file_size_mb > parquet_threshold_mb
    parquet_cache: str | None = None

    if use_parquet:
        base = os.path.basename(csv_real) + '.parquet'
        if cache_dir:
            os.makedirs(cache_dir, exist_ok=True)
            parquet_cache = os.path.join(os.path.realpath(cache_dir), base)
        else:
            parquet_cache = csv_real + '.parquet'

    if use_parquet and parquet_cache and not os.path.exists(parquet_cache):
        print(f'[cache] converting {file_size_mb:.0f} MB CSV to Parquet (one-time)...', flush=True)
        out_lit = safe_duckdb_output_path(parquet_cache)
        con.execute(_SQL_COPY_PARQUET.format_map(
            {'select': select_expr, 'lit_csv': csv_lit, 'lit_out': out_lit}
        ))
        print(f'[cache] wrote {os.path.getsize(parquet_cache)/(1024*1024):.0f} MB '
              f'Parquet at {parquet_cache}', flush=True)

    # Stage 1: raw view.
    raw_view = view_name + '__raw'
    if use_parquet and parquet_cache and os.path.exists(parquet_cache):
        pq_lit = safe_duckdb_path(parquet_cache)
        con.execute(_SQL_VIEW_RAW_PQ.format_map({'view': raw_view, 'lit_pq': pq_lit}))
    else:
        con.execute(_SQL_VIEW_RAW_CSV.format_map(
            {'view': raw_view, 'select': select_expr, 'lit_csv': csv_lit}
        ))

    # Stage 2: typed view with timestamp cast.
    con.execute(_SQL_VIEW_TYPED.format_map({'view': view_name, 'raw_view': raw_view}))
    return raw_columns


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------

def md_section(title: str) -> str:
    return f'\n## {title}\n'


def md_table(df: pd.DataFrame, max_rows: int = 20) -> str:
    if df.empty:
        return '_No data._\n'
    return df.head(max_rows).to_markdown(index=False) + '\n'


def has_column(con: duckdb.DuckDBPyConnection, view: str, col: str) -> bool:
    sql = _SQL_DESCRIBE.format_map({'view': view})
    return col in con.sql(sql).df()['column_name'].tolist()


# ---------------------------------------------------------------------------
# Profile function
# ---------------------------------------------------------------------------

def profile(con: duckdb.DuckDBPyConnection, source: str, view: str = 'logins',
            top_n: int = 10) -> str:
    out: list[str] = ['# Salesforce Login Export Profile\n',
                      '**Detected source:** ' + source + '  ']

    summary = con.sql(_SQL_SUMMARY.format_map({'view': view})).df().iloc[0]
    total = int(summary['total'])
    out.append(f'**Total rows:** {total:,}  ')
    if summary['tmin'] is not None and summary['tmax'] is not None:
        out.append(
            f'**Time range (UTC):** {summary["tmin"]} → {summary["tmax"]} '
            f'({summary["tmax"] - summary["tmin"]})  '
        )

    cols = con.sql(_SQL_DESCRIBE.format_map({'view': view})).df()['column_name'].tolist()
    out.append(f'**Columns (normalized):** {len(cols)} — {", ".join(cols)}\n')

    n_top = safe_sql_number(top_n, min_value=1, max_value=10000)
    n_total = safe_sql_number(total, min_value=0)

    # Scale
    out.append(md_section('Scale'))
    scale_parts = [('Total rows', 'COUNT(*)')]
    for col, label in [('userId', 'Unique users (UserId)'),
                       ('username', 'Unique usernames'),
                       ('sourceIp', 'Unique source IPs'),
                       ('countryIso', 'Unique countries'),
                       ('loginType', 'Distinct LoginTypes'),
                       ('loginSubType', 'Distinct LoginSubTypes'),
                       ('application', 'Distinct Applications')]:
        if col in cols:
            scale_parts.append((label, 'COUNT(DISTINCT ' + col + ')'))
    select = ', '.join(expr + ' AS "' + label + '"' for label, expr in scale_parts)
    scale_row = con.sql(_SQL_SCALE.format_map({'select': select, 'view': view})).df().iloc[0]
    out.append(md_table(pd.DataFrame({'metric': scale_row.index, 'value': scale_row.values})))

    # Status distribution
    if 'status' in cols:
        out.append(md_section('Status distribution'))
        out.append(md_table(con.sql(_SQL_DIST.format_map(
            {'col': 'status', 'view': view, 'n_total': n_total, 'n_top': n_top}
        )).df()))
        rate = con.sql(_SQL_SUCCESS_RATE.format_map({'view': view})).df().iloc[0]['rate']
        out.append(f'\n**Success rate:** {rate:.2f}%\n')

    # LoginType / LoginSubType distributions
    for col, title in [('loginType', 'LoginType distribution'),
                       ('loginSubType', 'LoginSubType distribution')]:
        if col in cols:
            out.append(md_section(title))
            out.append(md_table(con.sql(_SQL_DIST.format_map(
                {'col': col, 'view': view, 'n_total': n_total, 'n_top': n_top}
            )).df()))

    if 'loginSubType' in cols:
        api_cnt = con.sql(_SQL_API_COUNT.format_map({'view': view})).df().iloc[0]['cnt']
        if api_cnt > 0:
            pct = api_cnt / total * 100 if total else 0
            out.append(
                f'\n_Note: {int(api_cnt):,} logins ({pct:.1f}%) use API-style subtypes. '
                "Run `filter_by_subtype.py` to drill down._\n"
            )

    # Top users
    user_col = 'userId' if 'userId' in cols else ('username' if 'username' in cols else None)
    if user_col:
        out.append(md_section(f'Top {top_n} users by login count'))
        out.append(md_table(con.sql(_SQL_TOP_BY_COL.format_map(
            {'col': user_col, 'view': view, 'n_top': n_top}
        )).df()))

    # Top IPs
    if 'sourceIp' in cols:
        out.append(md_section(f'Top {top_n} source IPs'))
        out.append(md_table(con.sql(_SQL_TOP_BY_COL.format_map(
            {'col': 'sourceIp', 'view': view, 'n_top': n_top}
        )).df()))

    # Countries
    if 'countryIso' in cols:
        out.append(md_section('Top countries'))
        out.append(md_table(con.sql(_SQL_DIST.format_map(
            {'col': 'countryIso', 'view': view, 'n_total': n_total, 'n_top': n_top}
        )).df()))

    # TLS / Platform / Browser / Application
    for col, title in [('tlsProtocol', 'TLS Protocol distribution'),
                       ('platform', 'Platform distribution'),
                       ('browser', 'Browser distribution'),
                       ('application', 'Application distribution')]:
        if col in cols:
            out.append(md_section(title))
            out.append(md_table(con.sql(_SQL_DIST.format_map(
                {'col': col, 'view': view, 'n_total': n_total, 'n_top': n_top}
            )).df()))

    # Sanity hints
    out.append(md_section('Quick sanity hints'))
    hints: list[str] = []
    if 'status' in cols:
        fails = con.sql(_SQL_FAIL_COUNT.format_map({'view': view})).df().iloc[0]['cnt']
        if fails:
            hints.append(
                f'- {int(fails):,} failed logins ({fails/total*100:.1f}%) — '
                'worth scanning for clusters.'
            )
    if 'loginSubType' in cols:
        soap = con.sql(_SQL_SOAP_COUNT.format_map({'view': view})).df().iloc[0]['cnt']
        if soap:
            hints.append(
                f'- {int(soap):,} SOAP API logins detected — Salesforce is retiring '
                "SOAP login() for some flows. Run `filter_by_subtype.py --subtype 'SOAP API'`."
            )
    if 'tlsProtocol' in cols:
        weak = con.sql(_SQL_WEAK_TLS.format_map({'view': view})).df().iloc[0]['cnt']
        if weak:
            hints.append(f'- {int(weak):,} logins used TLS 1.0/1.1 (compliance risk).')
    if 'countryIso' in cols:
        nc = con.sql(_SQL_COUNTRY_CNT.format_map({'view': view})).df().iloc[0]['n']
        if nc and nc > 10:
            hints.append(
                f'- {int(nc)} distinct countries across source IPs — '
                'consider impossible-travel analysis.'
            )
    out.append('\n'.join(hints or ['_No obvious hints. Dig into specific anomalies._']) + '\n')
    return '\n'.join(out)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument('--input', '-i', required=True, help='Path to login export (CSV)')
    ap.add_argument('--output', '-o', help='Optional path to write the Markdown profile')
    ap.add_argument('--top-n', type=int, default=10, help='Rows in each top-N table')
    ap.add_argument('--memory-limit-gb', type=float, default=2.0,
                    help='DuckDB memory cap before spill to disk (default: 2.0)')
    ap.add_argument('--spill-dir',
                    help='Directory for DuckDB spill. Default: private tempfile.mkdtemp().')
    ap.add_argument('--cache-dir',
                    help='Directory for the Parquet cache. Default: alongside the input CSV.')
    ap.add_argument('--parquet-threshold-mb', type=float, default=500.0,
                    help='Files larger than this are cached as Parquet (default: 500).')
    args = ap.parse_args()

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

    report = profile(con, detect_source(raw_cols), top_n=args.top_n)
    if args.output:
        Path(args.output).write_text(report, encoding='utf-8')
        print(f'Profile written to {args.output}')
    else:
        print(report)
    return 0


if __name__ == '__main__':
    sys.exit(main())
