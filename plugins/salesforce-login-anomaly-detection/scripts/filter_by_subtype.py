#!/usr/bin/env python3
"""
filter_by_subtype.py — summary of users by a specific LoginSubType.

Typical use: "show all users who logged in via SOAP API (or Bulk API,
Metadata API, etc.)".

Uses DuckDB to stream the CSV without loading it into memory — works on files
with tens of millions of rows.

Usage:
    python filter_by_subtype.py --input logins.csv --subtype "SOAP API"
    python filter_by_subtype.py --input logins.csv --subtype "Bulk API,Metadata API"
    python filter_by_subtype.py --input logins.csv --subtype "SOAP API" \\
        --output-csv soap_users.csv --output-report soap_report.md
    python filter_by_subtype.py --input logins.csv --subtype "SOAP API" \\
        --integration-patterns integration,svc,api,mulesoft
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from profile_logins import (  # noqa: E402
    create_normalized_view,
    detect_source,
    safe_duckdb_output_path,
    safe_sql_string_list,
)

# ---------------------------------------------------------------------------
# SQL templates — module-level string constants.
# All dynamic values inserted via str.format_map() — no f-strings or
# concatenation inside con.sql() / con.execute().
# ---------------------------------------------------------------------------

_SQL_DESCRIBE   = "DESCRIBE {view}"
_SQL_TOTAL      = "SELECT COUNT(*) AS cnt FROM {view} WHERE loginSubType IN ({lit_subtypes})"
_SQL_SUMMARY    = (
    "WITH matched AS (SELECT * FROM {view} WHERE loginSubType IN ({lit_subtypes})) "
    "SELECT {select} FROM matched GROUP BY {col_user} ORDER BY logins DESC"
)
_SQL_STATUS     = (
    "SELECT COALESCE(status, '(null)') AS status, COUNT(*) AS logins,"
    "  ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) AS pct "
    "FROM {view} WHERE loginSubType IN ({lit_subtypes}) "
    "GROUP BY status ORDER BY logins DESC"
)
_SQL_DAILY      = (
    "SELECT CAST(loginTime AS DATE) AS date, COUNT(*) AS logins "
    "FROM {view} WHERE loginSubType IN ({lit_subtypes}) AND loginTime IS NOT NULL "
    "GROUP BY CAST(loginTime AS DATE) ORDER BY date"
)
_SQL_COPY_CSV   = (
    "COPY (SELECT * FROM {view} WHERE loginSubType IN ({lit_subtypes})) "
    "TO {lit_out} (HEADER, DELIMITER ',')"
)
_SQL_COUNT      = "SELECT COUNT(*) AS cnt FROM {view} WHERE loginSubType IN ({lit_subtypes})"

DEFAULT_INTEGRATION_PATTERNS = [
    'integration', 'svc', 'service', 'api', 'sys', 'system',
    'etl', 'bot', 'automation', 'dataloader', 'mulesoft',
    'workato', 'zapier', 'connector', 'informatica', 'boomi',
    'snaplogic', 'talend', 'jitterbit',
]


def build_user_summary(con: duckdb.DuckDBPyConnection, view: str,
                       subtypes: list[str],
                       integration_patterns: list[str]) -> tuple[pd.DataFrame, int]:
    sql_desc = _SQL_DESCRIBE.format_map({'view': view})
    cols = con.sql(sql_desc).df()['column_name'].tolist()
    if 'loginSubType' not in cols:
        raise ValueError(
            'The normalized view has no `loginSubType` column. '
            'This source (likely an old UI export) does not include LoginSubType. '
            'Use an SOQL export or Event Monitoring file instead.'
        )

    lit_subtypes = safe_sql_string_list(subtypes)

    total = int(con.sql(_SQL_TOTAL.format_map(
        {'view': view, 'lit_subtypes': lit_subtypes}
    )).df().iloc[0]['cnt'])
    if total == 0:
        return pd.DataFrame(), 0

    user_key = 'userId' if 'userId' in cols else 'username'
    has_username = 'username' in cols
    has_country = 'countryIso' in cols
    has_ip = 'sourceIp' in cols

    select_parts = [user_key]
    if has_username and user_key != 'username':
        select_parts.append('any_value(username) AS username')
    select_parts.extend([
        'COUNT(*) AS logins',
        "SUM(CASE WHEN status = 'Success' THEN 1 ELSE 0 END) AS successLogins",
        'MIN(loginTime) AS firstSeen', 'MAX(loginTime) AS lastSeen',
    ])
    if has_ip:
        select_parts.append('COUNT(DISTINCT sourceIp) AS uniqueIps')
    if has_country:
        select_parts.append('COUNT(DISTINCT countryIso) AS uniqueCountries')
    select_parts.append("STRING_AGG(DISTINCT loginSubType, ', ' ORDER BY loginSubType) AS subtypesUsed")

    summary = con.sql(_SQL_SUMMARY.format_map({
        'view': view,
        'lit_subtypes': lit_subtypes,
        'select': ', '.join(select_parts),
        'col_user': user_key,
    })).df()

    if 'successLogins' in summary.columns:
        summary['successRatePct'] = (
            summary['successLogins'] / summary['logins'] * 100
        ).round(2)

    if has_username:
        def _is_human(u: object) -> bool | None:
            if u is None or (isinstance(u, float) and pd.isna(u)):
                return None
            s = str(u).lower()
            return not any(p in s for p in integration_patterns)
        col = 'username' if 'username' in summary.columns else user_key
        summary['likelyHuman'] = summary[col].apply(_is_human)

    sort_cols = ['likelyHuman', 'logins'] if 'likelyHuman' in summary.columns else ['logins']
    summary = summary.sort_values(sort_cols, ascending=[False, False], na_position='last')
    return summary, total


def build_status_breakdown(con: duckdb.DuckDBPyConnection, view: str,
                           subtypes: list[str]) -> pd.DataFrame:
    sql_desc = _SQL_DESCRIBE.format_map({'view': view})
    cols = con.sql(sql_desc).df()['column_name'].tolist()
    if 'status' not in cols:
        return pd.DataFrame()
    return con.sql(_SQL_STATUS.format_map(
        {'view': view, 'lit_subtypes': safe_sql_string_list(subtypes)}
    )).df()


def build_daily_timeline(con: duckdb.DuckDBPyConnection, view: str,
                         subtypes: list[str]) -> pd.DataFrame:
    return con.sql(_SQL_DAILY.format_map(
        {'view': view, 'lit_subtypes': safe_sql_string_list(subtypes)}
    )).df()


def export_filtered_csv(con: duckdb.DuckDBPyConnection, view: str,
                        subtypes: list[str], output_path: str) -> int:
    """Write matching rows directly from DuckDB to CSV — streams, no memory spike.

    The COPY ... TO path is resolved via safe_duckdb_output_path() before
    being substituted into the SQL template constant via format_map().
    DuckDB does not accept bound parameters for COPY destinations.
    """
    lit_subtypes = safe_sql_string_list(subtypes)
    lit_out = safe_duckdb_output_path(output_path)
    con.execute(_SQL_COPY_CSV.format_map(
        {'view': view, 'lit_subtypes': lit_subtypes, 'lit_out': lit_out}
    ))
    return int(con.sql(_SQL_COUNT.format_map(
        {'view': view, 'lit_subtypes': lit_subtypes}
    )).df().iloc[0]['cnt'])


def render_markdown_report(subtypes: list[str], total_matched: int,
                            user_summary: pd.DataFrame,
                            status_breakdown: pd.DataFrame,
                            daily: pd.DataFrame, source: str) -> str:
    lines: list[str] = [
        f'# LoginSubType Filter Report: {", ".join(subtypes)}', '',
        f'**Source detected:** {source}  ',
        f'**Matched rows:** {total_matched:,}  ',
    ]
    if not user_summary.empty:
        lines.append(f'**Unique users:** {len(user_summary):,}  ')
        if 'likelyHuman' in user_summary.columns and user_summary['likelyHuman'].notna().any():
            lines.append(f'**Likely human users:** {int(user_summary["likelyHuman"].fillna(False).sum())}  ')
            lines.append(f'**Likely integration users:** {int((~user_summary["likelyHuman"].fillna(True)).sum())}  ')
    lines.append('')

    if user_summary.empty:
        lines.append('_No matching logins found._')
        return '\n'.join(lines)

    lines.append('## Users with matching LoginSubType\n')
    display = user_summary.copy()
    for col in ['firstSeen', 'lastSeen']:
        if col in display.columns:
            display[col] = pd.to_datetime(display[col]).dt.strftime('%Y-%m-%d %H:%M UTC')
    lines.append(display.to_markdown(index=False))
    lines.append('')

    if 'likelyHuman' in user_summary.columns:
        humans = user_summary[user_summary['likelyHuman'] == True]  # noqa: E712
        if not humans.empty:
            lines.append('## ⚠️  Priority review: likely human users\n')
            lines.append(
                'These usernames do not match typical integration patterns. '
                'If they really are people, interactive API use (Data Loader, '
                'WorkBench, scripts) warrants review.\n'
            )
            priority_cols = [c for c in ['username', 'logins', 'successRatePct',
                                          'firstSeen', 'lastSeen'] if c in humans.columns]
            priority = humans[priority_cols].copy()
            for col in ['firstSeen', 'lastSeen']:
                if col in priority.columns:
                    priority[col] = pd.to_datetime(priority[col]).dt.strftime('%Y-%m-%d %H:%M UTC')
            lines.append(priority.to_markdown(index=False))
            lines.append('')

    if not status_breakdown.empty:
        lines.append('## Status breakdown\n')
        lines.append(status_breakdown.to_markdown(index=False))
        lines.append('')

    if not daily.empty:
        lines.append('## Daily timeline\n')
        lines.append(daily.to_markdown(index=False))
        lines.append('')

    lines.append('## Caveats\n')
    lines.append(
        '- The `likelyHuman` flag is a heuristic based on username substrings. '
        'Confirm against your actual list of integration users.'
    )
    lines.append(
        '- 100% failure rate on a matched LoginSubType usually means a broken '
        'integration or a breach attempt — worth investigating either way.'
    )
    return '\n'.join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--input', '-i', required=True, help='Path to login export (CSV)')
    ap.add_argument('--subtype', '-s', required=True,
                    help='LoginSubType value(s) to filter by. Comma-separated for multiple.')
    ap.add_argument('--output-csv', help='Write the full filtered rows to this CSV')
    ap.add_argument('--output-report', help='Write the Markdown report to this file')
    ap.add_argument('--integration-patterns',
                    help=f'Comma-separated integration-user substrings '
                         f'(default: {",".join(DEFAULT_INTEGRATION_PATTERNS)})')
    ap.add_argument('--memory-limit-gb', type=float, default=2.0)
    ap.add_argument('--spill-dir')
    ap.add_argument('--cache-dir')
    ap.add_argument('--parquet-threshold-mb', type=float, default=500.0)
    args = ap.parse_args()

    path = Path(args.input).absolute()
    if not path.exists():
        print(f'Error: file not found: {path}', file=sys.stderr)
        return 1

    subtypes = [s.strip() for s in args.subtype.split(',') if s.strip()]
    if not subtypes:
        print('Error: --subtype must contain at least one value.', file=sys.stderr)
        return 1

    integration_patterns = (
        [p.strip().lower() for p in args.integration_patterns.split(',')]
        if args.integration_patterns else DEFAULT_INTEGRATION_PATTERNS
    )

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

    source = detect_source(raw_cols)
    try:
        user_summary, total = build_user_summary(con, 'logins', subtypes, integration_patterns)
    except ValueError as e:
        print(f'Error: {e}', file=sys.stderr)
        return 2

    status_breakdown = build_status_breakdown(con, 'logins', subtypes)
    daily = build_daily_timeline(con, 'logins', subtypes)
    report = render_markdown_report(subtypes, total, user_summary, status_breakdown, daily, source)

    if args.output_report:
        Path(args.output_report).write_text(report, encoding='utf-8')
        print(f'Report written to {args.output_report}')
    else:
        print(report)

    if args.output_csv and total > 0:
        exported = export_filtered_csv(con, 'logins', subtypes, args.output_csv)
        print(f'\nFull filtered rows written to {args.output_csv} ({exported:,} rows)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
