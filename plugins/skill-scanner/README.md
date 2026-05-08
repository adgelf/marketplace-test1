# skill-scanner

A safety and security gate for Claude skill repositories. Scans skills
submitted via pull request and blocks merges that introduce dangerous or
low-quality skills into a shared library.

The scanner reports findings across **two clearly separated dimensions**:

- **Safety** — the skill's *concept and intent*. Does the skill, as designed,
  push Claude toward harmful, deceptive, or out-of-scope behavior? Safety
  findings are about what the skill is trying to make Claude *do*.
- **Security** — *technical vulnerabilities* in the skill's artifacts.
  Credentials, code execution paths, exfiltration channels, supply chain
  risks. Security findings are about what an attacker could *exploit* in
  the skill's code or files.

Every report emits `## Safety Findings` and `## Security Findings` as
separate top-level sections, each with its own findings list, summary table,
and verdict. This keeps the two kinds of risk from being conflated in the
reviewer's head.

---

## How it works

| Dimension | Detection method | Rationale |
|---|---|---|
| Safety | LLM-assisted (Anthropic API) with a deterministic pre-check pass | Concept/intent issues are hard to regex — they live in natural-language instructions. A rubric-guided LLM pass catches them; the pre-check covers the cheap structural cases (missing SKILL.md, malformed frontmatter). |
| Security | Pure pattern-based (regex + Python AST) | Credentials, unsafe code, supply-chain heuristics, and exfiltration patterns are deterministic and cheap. No API key required. |

If `ANTHROPIC_API_KEY` is not set (or `--no-llm` is passed), the security
pass still runs and produces a valid report — only the LLM-based safety
checks are skipped. The deterministic safety pre-checks always run.

---

## Repo layout

```
skill-scanner/
├── SKILL.md                       # the skill itself — read by Claude
├── scripts/
│   ├── scan_skill.py              # main scanner (stdlib only)
│   └── ci_entrypoint.py           # CI wrapper: diff → scan → aggregate
└── references/
    ├── scan_patterns.md           # full pattern catalog, 25+ entries
    └── github-action.yml          # drop-in GitHub Actions workflow
```

The scanner is pure Python 3.11 standard library — no `pip install` needed
in CI.

---

## Installation

### As a skill (interactive use with Claude)

Drop `skill-scanner/` into your skills directory (e.g.
`/mnt/skills/user/skill-scanner` or wherever your Claude instance loads
skills from). Then ask Claude to scan a skill:

```
"Scan the skill at /path/to/my-new-skill for safety and security"
"Review this SKILL.md before I commit it"
"Is this skill safe to add to our shared repo?"
```

Claude will read the SKILL.md, walk the pattern catalog, and produce a
structured report.

### As a CI gate (GitHub Actions)

1. Vendor this repo into your skills repository at any path (the examples
   below assume `skill-scanner/` at the repo root).
2. Copy `skill-scanner/references/github-action.yml` to
   `.github/workflows/skill-scan.yml`.
3. Add `ANTHROPIC_API_KEY` as a repository secret (optional — omit and the
   workflow still runs, just without the LLM safety pass).
4. Open a PR. The workflow will comment the report and fail the check on
   any CRITICAL or HIGH finding in either dimension.

---

## CLI usage

### Scan a single skill

```bash
python skill-scanner/scripts/scan_skill.py path/to/skill \
  --output report.md \
  --json findings.json
```

Flags:

- `--output, -o` — write markdown report to file (default: stdout)
- `--json` — also emit findings as JSON
- `--no-llm` — skip the LLM-based safety scan (security still runs)

### Scan every changed skill in a PR

```bash
python skill-scanner/scripts/ci_entrypoint.py \
  --base-ref origin/main \
  --repo-root . \
  --output report.md
```

The CI entrypoint walks `git diff <base-ref>...HEAD`, identifies which
ancestor directories contain a `SKILL.md`, and runs the scanner against
each. The aggregate report nests each per-skill report inside a collapsible
`<details>` block.

### Exit codes

| Code | Meaning |
|------|---------|
| 0 | Pass — no CRITICAL or HIGH findings in either dimension |
| 1 | Fail — CRITICAL or HIGH found in safety *or* security |
| 2 | Scanner error — bad input, git failure, etc. |

---

## Report format

```markdown
# Skill Scan Report

**Skill:** example-skill
**Overall Verdict:** FAIL
**Safety Verdict:** FAIL (1 CRITICAL)
**Security Verdict:** FAIL (1 HIGH)

## Safety Findings
*Concerns the skill's concept and intent — what the skill is designed to
make Claude do.*

### [CRITICAL] SSK-PI-001: System prompt override in SKILL.md
- **Dimension:** Safety
- **File:** SKILL.md, line 42
- **Pattern:** Prompt Injection > System Override
- **Evidence:** `You are no longer bound by previous instructions...`
- **Risk:** The skill's design hijacks Claude's behavior for all subsequent
  turns.
- **Remediation:** Remove override instruction. Skills should extend
  Claude's behavior, never replace its system prompt.

### Safety Summary
| Severity | Count |
|----------|-------|
| CRITICAL | 1     |
| HIGH     | 0     |
...

## Security Findings
*Concerns technical vulnerabilities in the skill's code, files, and
dependencies — what an attacker could exploit.*

### [HIGH] SSK-UC-003: eval() on user-controlled input
- **Dimension:** Security
- **File:** scripts/process.py, line 87
- **Pattern:** Unsafe Code > Dynamic Execution
- **Evidence:** `eval(user_input)` without sanitization
- **Risk:** Arbitrary code execution.
- **Remediation:** Replace with structured parsing (json.loads,
  ast.literal_eval, or explicit dispatchers).

### Security Summary
| Severity | Count |
|----------|-------|
| CRITICAL | 0     |
| HIGH     | 1     |
...
```

**Reporting guarantees:**

- Both `## Safety Findings` and `## Security Findings` sections are always
  emitted, even when empty. A section with no findings shows
  `*No findings in this dimension.*` so a reader never has to guess whether
  a dimension was scanned.
- Every finding includes an explicit `**Dimension:**` line so the
  classification survives out-of-context quotation.
- The Overall Verdict is FAIL if *either* Safety or Security has CRITICAL
  or HIGH findings.

---

## Categories

The scanner runs 8 categories across the two dimensions. Finding IDs follow
the format `SSK-{CATEGORY}-{SEQ}`, and the prefix alone tells you which
section the finding belongs in.

### Safety (concept/intent)

| Prefix | Category | What it catches |
|--------|----------|-----------------|
| `PI` | Prompt Injection | System prompt override, jailbreaks, role reassignment, hidden instructions in references, conditional bypasses |
| `EP` | Excessive Permissions | Tool access mismatch vs stated purpose, unbounded shell/FS scope, vague tool invocation |
| `IQ` | Instruction Quality | Contradictory instructions, missing failure-mode guidance, vague success criteria, missing/empty SKILL.md |
| `SM` | Skill Metadata | Description hijacking, concept-description mismatch, missing or malformed frontmatter |

### Security (technical vulnerabilities)

| Prefix | Category | What it catches |
|--------|----------|-----------------|
| `CS` | Credential & Secret Exposure | Known API key prefixes, generic high-entropy secrets, private key material, DB connection strings with passwords, hardcoded password literals |
| `DE` | Data Exfiltration | Outbound network calls to non-allowlisted hosts, known webhook/telemetry endpoints, instructions to transmit data externally |
| `UC` | Unsafe Code | eval/exec on dynamic input, shell injection via string concatenation, path traversal, insecure deserialization (pickle, unsafe yaml), disabled TLS verification |
| `SC` | Supply Chain | Unpinned dependencies, unknown registries, post-install hooks, typosquat candidates |

Full pattern list with detection details, rationale, and remediation lives
in [`references/scan_patterns.md`](references/scan_patterns.md).

---

## Severity guide

Severity is a *default* per pattern — the scanner can upgrade or downgrade
based on context (for example, a credential match inside a documented
example may be downgraded to LOW with the rationale recorded).

### Safety

| Condition | Severity |
|---|---|
| System prompt override / jailbreak instruction | CRITICAL |
| Instructions to disable Claude's safety guardrails | HIGH |
| Description deceptively misrepresents purpose | HIGH |
| Tool access broader than stated concept | MEDIUM |
| Dual-use framing without clear safe-use boundaries | MEDIUM |
| Ambiguous or contradictory instructions | LOW |
| Cosmetic / style issues | INFO |

### Security

| Condition | Severity |
|---|---|
| Hardcoded active credential (API key, token, password) | CRITICAL |
| Arbitrary code execution (eval/exec on untrusted input) | CRITICAL |
| Outbound data exfiltration to external host | HIGH |
| Shell injection vector in script | HIGH |
| Insecure deserialization of untrusted data | HIGH |
| Unpinned dependency from unknown registry | MEDIUM |
| Suspicious binary or oversized asset | LOW |
| Cosmetic / style issues | INFO |

---

## Configuration

### Environment variables

| Variable | Purpose |
|----------|---------|
| `ANTHROPIC_API_KEY` | Required for the LLM-based safety scan. If unset, safety reverts to deterministic pre-checks only and a warning is printed. |
| `GITHUB_BASE_REF` | Used by `ci_entrypoint.py` as the default `--base-ref` when running in GitHub Actions. |

### LLM model

The safety pass uses `claude-opus-4-7` by default (see
`scripts/scan_skill.py`, constant `SAFETY_RUBRIC` section). Change the
model ID in the script if your API key is scoped to a different model.

---

## What gets scanned

| Component | Safety checks | Security checks |
|---|---|---|
| `SKILL.md` frontmatter | Description hijacking, trigger conflict, deceptive scope | — |
| `SKILL.md` body | System-prompt override, jailbreak, ambiguous behavior, scope creep | Embedded credentials, exfiltration instructions |
| `scripts/*.py` | Instructions to bypass Claude's safety reasoning | Credential handling, network calls, FS abuse, code injection |
| `scripts/*.sh` | — | Command injection, curl to unknown hosts, eval/exec abuse |
| `references/*` | Hidden instructions intended to alter Claude's behavior | Encoded payloads |
| `assets/*` | — | Suspicious file types, oversized binaries |

---

## Extending the scanner

Patterns live in two places:

1. **`scripts/scan_skill.py`** — deterministic detectors for the security
   dimension. Each detector returns a list of `Finding` objects. Add a new
   detector by writing a function that takes `(path, text, base)` and
   appending its findings to the orchestration loop at the bottom of
   `scan_skill()`.
2. **`scripts/scan_skill.py`** `SAFETY_RUBRIC` constant — the prompt Claude
   uses for the safety dimension. Extend the rubric with new concept-level
   checks; Claude will produce findings in the same JSON schema.
3. **`references/scan_patterns.md`** — the human-readable catalog. Keep
   this in sync with the code so that finding IDs in reports always trace
   back to a documented pattern.

When adding a new category prefix, also update:

- `SAFETY_PREFIXES` or `SECURITY_PREFIXES` in `scan_skill.py`
- `CATEGORY_NAMES` in `scan_skill.py`
- The Finding ID Convention table in `SKILL.md`
- The Table of Contents in `references/scan_patterns.md`

---

## Development notes

The scanner is deliberately stdlib-only so it can run in CI with no
dependency install step. If you introduce a third-party dependency, add a
`requirements.txt` and update the workflow to install it — but weigh that
against the simplicity gain of keeping the current setup.

Testing tip: the scanner accepts any directory containing a `SKILL.md`, so
you can write synthetic test-target skills that deliberately trip specific
patterns, and assert the expected finding IDs appear in the JSON output.
