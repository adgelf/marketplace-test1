#!/usr/bin/env python3
"""
ci_entrypoint.py — CI wrapper for skill-scanner.

Discovers skill directories changed in a PR, runs scan_skill.py against each,
and aggregates results into a single markdown report with separate Safety
and Security sections per skill.

Usage:
  python ci_entrypoint.py [--base-ref origin/main] [--repo-root .]
                          [--output report.md] [--no-llm]

Exit codes:
  0 = pass (no CRITICAL/HIGH in any changed skill, in either dimension)
  1 = fail (CRITICAL/HIGH found in safety or security of any changed skill)
  2 = scanner error

Environment:
  ANTHROPIC_API_KEY — required unless --no-llm
  GITHUB_BASE_REF   — used as default --base-ref when set (GitHub Actions)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

# Allow importing scan_skill from the same directory
sys.path.insert(0, str(Path(__file__).resolve().parent))
import scan_skill  # noqa: E402


def changed_files(base_ref: str, repo_root: Path) -> list[Path]:
    """Return list of files changed vs base_ref."""
    try:
        out = subprocess.check_output(
            ["git", "-C", str(repo_root), "diff", "--name-only",
             f"{base_ref}...HEAD"],
            text=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"ERROR: git diff failed: {e}", file=sys.stderr)
        sys.exit(2)
    return [Path(line.strip()) for line in out.splitlines() if line.strip()]


def find_skill_dirs(files: list[Path], repo_root: Path) -> list[Path]:
    """A skill dir is any ancestor of a changed file that contains SKILL.md."""
    skill_dirs: set[Path] = set()
    for f in files:
        full = (repo_root / f).resolve()
        for parent in [full] + list(full.parents):
            if parent == repo_root.resolve().parent:
                break
            if (parent / "SKILL.md").exists():
                skill_dirs.add(parent)
                break
    return sorted(skill_dirs)


def scan_one(skill_dir: Path, use_llm: bool) -> tuple[list[scan_skill.Finding], str]:
    scan_skill._SEQ_COUNTERS.clear()
    findings = scan_skill.scan_skill(skill_dir, use_llm=use_llm)
    report = scan_skill.render_report(skill_dir, findings)
    return findings, report


def aggregate_report(per_skill: list[tuple[Path, list[scan_skill.Finding], str]]) -> str:
    """Combine per-skill reports into one document with a top-level summary."""
    if not per_skill:
        return "# Skill Scan Report\n\nNo skill directories changed in this PR.\n"

    total_safety = sum(
        len(scan_skill.section_for(f, "Safety")) for _, f, _ in per_skill
    )
    total_security = sum(
        len(scan_skill.section_for(f, "Security")) for _, f, _ in per_skill
    )
    overall_fail = any(
        f.severity in scan_skill.FAIL_SEVERITIES
        for _, fs, _ in per_skill for f in fs
    )

    parts = [
        "# Skill Scan Report — PR Aggregate\n",
        f"**Scanned skills:** {len(per_skill)}",
        f"**Total Safety findings:** {total_safety}",
        f"**Total Security findings:** {total_security}",
        f"**Overall Verdict:** {'FAIL' if overall_fail else 'PASS'}",
        "",
        "---",
        "",
        "## Per-skill reports",
        "",
    ]
    for skill_dir, _findings, report in per_skill:
        parts.append(f"<details><summary><strong>{skill_dir.name}</strong></summary>\n")
        parts.append(report)
        parts.append("\n</details>\n")
    return "\n".join(parts)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run skill-scanner on changed skills in a PR.")
    ap.add_argument("--base-ref", default=os.environ.get("GITHUB_BASE_REF", "origin/main"),
                    help="Git ref to diff against (default: $GITHUB_BASE_REF or origin/main)")
    ap.add_argument("--repo-root", type=Path, default=Path("."),
                    help="Repository root (default: cwd)")
    ap.add_argument("--output", "-o", type=Path, default=None,
                    help="Write aggregate markdown report here (default: stdout)")
    ap.add_argument("--json", type=Path, default=None,
                    help="Write aggregate findings JSON here")
    ap.add_argument("--no-llm", action="store_true",
                    help="Skip LLM safety scans (security checks still run)")
    args = ap.parse_args(argv)

    repo_root = args.repo_root.resolve()
    base_ref = args.base_ref

    # Make sure base ref is fetched (GitHub Actions checkout often only has HEAD)
    subprocess.run(["git", "-C", str(repo_root), "fetch", "--depth=50",
                    "origin", base_ref.replace("origin/", "")],
                   check=False, capture_output=True)

    files = changed_files(base_ref, repo_root)
    skill_dirs = find_skill_dirs(files, repo_root)

    if not skill_dirs:
        report = "# Skill Scan Report\n\nNo skill directories changed in this PR.\n"
        if args.output:
            args.output.write_text(report, encoding="utf-8")
        else:
            print(report)
        return 0

    per_skill: list[tuple[Path, list[scan_skill.Finding], str]] = []
    for sd in skill_dirs:
        findings, report = scan_one(sd, use_llm=not args.no_llm)
        per_skill.append((sd, findings, report))

    aggregate = aggregate_report(per_skill)

    if args.output:
        args.output.write_text(aggregate, encoding="utf-8")
    else:
        print(aggregate)

    if args.json:
        args.json.write_text(
            json.dumps(
                {
                    sd.name: [vars(f) for f in findings]
                    for sd, findings, _ in per_skill
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    overall_fail = any(
        f.severity in scan_skill.FAIL_SEVERITIES
        for _, fs, _ in per_skill for f in fs
    )
    return 1 if overall_fail else 0


if __name__ == "__main__":
    sys.exit(main())
