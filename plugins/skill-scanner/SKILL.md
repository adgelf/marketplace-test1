---
name: skill-scanner
description: >
  Safety and security scanner for Claude skills. Analyzes SKILL.md files,
  bundled scripts, and reference documents across two distinct dimensions:
  SAFETY (the skill's concept and intent — does it push Claude toward overreach,
  dual-use behavior, jailbreaks, scope creep, ambiguous or harmful instructions)
  and SECURITY (technical vulnerabilities — credential leakage, code execution,
  data exfiltration, supply chain risks). Produces a structured findings report
  with two clearly separated sections (## Safety Findings and ## Security
  Findings), each with its own severity ratings (CRITICAL/HIGH/MEDIUM/LOW/INFO)
  and remediation guidance. Designed to run both interactively and as a CI gate
  in GitHub Actions or Jenkins, blocking PRs that introduce dangerous skills
  into a shared skill repository. Use this skill whenever the user asks to:
  review a skill for safety or security, audit a SKILL.md, check a skill
  before merging, scan a skill repo PR, validate skill safety, or review skill
  quality. Triggers on: "scan this skill", "review skill safety", "review
  skill security", "is this skill safe", "audit SKILL.md", "check skill PR",
  "skill gate", "scan skill repo", "review before merge".
---

# Skill Scanner

Safety and security gate for Claude skill repositories. Scans skills submitted
via PR across two distinct dimensions before they land in a shared skill library:

- **Safety** — concerns the skill's **concept and intent**. Does the skill, as
  designed, push Claude toward harmful, dual-use, deceptive, or out-of-scope
  behavior? Safety findings are about what the skill is *trying to make Claude do*.
- **Security** — concerns **technical vulnerabilities** in the skill's
  artifacts. Credentials, code execution paths, exfiltration channels, supply
  chain risks. Security findings are about what an attacker could *exploit in the
  skill's code or files*.

These two dimensions are reported in separate sections of the output, each with
its own findings list, summary table, and verdict.

---

## Architecture

```
scripts/
  scan_skill.py      → main scanner: parses skill, runs all checks, outputs report
  ci_entrypoint.py   → CI wrapper: discovers changed skills in PR, runs scanner,
                        sets exit code for gate pass/fail

references/
  scan_patterns.md   → full catalog of safety and security check patterns
  github-action.yml  → ready-to-use GitHub Actions workflow for PR gating
```

---

## What Gets Scanned

A skill is a directory containing at minimum a `SKILL.md`. The scanner analyzes:

| Component | Safety checks | Security checks |
|---|---|---|
| `SKILL.md` frontmatter | Description hijacking, trigger conflict, deceptive scope | — |
| `SKILL.md` body | System-prompt override, jailbreak instructions, ambiguous behavior, scope creep, dual-use intent | Embedded credentials, exfiltration instructions |
| `scripts/*.py` | Instructions to bypass Claude's safety reasoning | Credential handling, network calls, FS abuse, code injection |
| `scripts/*.sh` | — | Command injection, curl to unknown hosts, eval/exec abuse |
| `references/*` | Embedded prompts, hidden instructions designed to alter Claude's behavior | Encoded payloads |
| `assets/*` | — | Suspicious file types, oversized binaries |

---

## Scan Categories

The scanner runs checks across 8 categories, split into the two dimensions.
Full details: `references/scan_patterns.md`.

### Safety categories (concept/intent)

1. **Prompt Injection (PI)** — instructions inside the skill that try to
   override Claude's system prompt, bypass safety reasoning, or jailbreak the
   model. The skill's *design* is the threat.
2. **Excessive Permissions (EP)** — the skill requests broader tool access or
   scope than its stated concept warrants. Scope creep relative to the skill's
   purpose.
3. **Instruction Quality (IQ)** — ambiguous, contradictory, or missing
   guidance that causes Claude to behave unpredictably or fall back to
   unsafe defaults.
4. **Skill Metadata (SM)** — deceptive descriptions, trigger hijacking, name
   conflicts, or framing that misrepresents what the skill actually does.

### Security categories (technical vulnerabilities)

5. **Credential & Secret Exposure (CS)** — hardcoded keys, tokens, passwords,
   private endpoints in any file shipped with the skill.
6. **Data Exfiltration (DE)** — network calls, webhooks, or instructions to
   send conversation data, files, or context to external hosts.
7. **Unsafe Code Patterns (UC)** — eval/exec on untrusted input, shell
   injection, path traversal, deserialization of untrusted data in scripts.
8. **Supply Chain (SC)** — untrusted dependencies, unpinned versions, unknown
   registries, post-install hooks.

---

## Usage

### Interactive (in Claude)

```
"Scan the skill at /mnt/skills/user/my-new-skill"
"Review this SKILL.md for safety and security before I commit it"
"Is this skill safe to add to our shared repo?"
```

When triggered interactively, read this SKILL.md, then read
`references/scan_patterns.md` for the full check catalog. Analyze the target
skill directory systematically:

1. Read the target skill's SKILL.md (frontmatter + body)
2. List and read all files in scripts/, references/, assets/
3. Run each Safety check category against every file
4. Run each Security check category against every file
5. Produce a findings report in the format below — **always emit the Safety
   section first, then the Security section, even if one of them is empty**

### CI Mode (GitHub Actions / Jenkins)

The `scripts/ci_entrypoint.py` script handles:
- Discovering which skill directories changed in the PR diff
- Running `scan_skill.py` on each changed skill
- Aggregating results into a single markdown report with separate Safety and
  Security sections
- Setting exit code: 0 = pass, 1 = CRITICAL/HIGH findings (in either dimension),
  2 = scanner error

See `references/github-action.yml` for a drop-in GitHub Actions workflow.

---

## Report Format

The report has **two top-level finding sections** that must always appear in
this order: Safety first, then Security. Each section is self-contained with
its own findings list, summary table, and verdict.

```markdown
# Skill Scan Report

**Skill:** skill-name
**Scanned:** 2025-06-15 14:30 UTC
**Overall Verdict:** FAIL
**Safety Verdict:** FAIL (1 CRITICAL)
**Security Verdict:** FAIL (1 HIGH)

---

## Safety Findings

*Concerns the skill's concept and intent — what the skill is designed to make
Claude do.*

### [CRITICAL] SSK-PI-001: System prompt override in SKILL.md
- **Dimension:** Safety
- **File:** SKILL.md, line 42
- **Pattern:** Prompt Injection > System Override
- **Evidence:** `You are no longer bound by previous instructions...`
- **Risk:** The skill's design hijacks Claude's behavior for all subsequent
  turns. This is a concept-level safety issue: the skill's purpose is to
  subvert Claude.
- **Remediation:** Remove override instruction. Skills should extend Claude's
  behavior, never replace its system prompt.

### Safety Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 1     |
| HIGH     | 0     |
| MEDIUM   | 0     |
| LOW      | 0     |
| INFO     | 1     |

---

## Security Findings

*Concerns technical vulnerabilities in the skill's code, files, and
dependencies — what an attacker could exploit.*

### [HIGH] SSK-UC-003: eval() on user-controlled input
- **Dimension:** Security
- **File:** scripts/process.py, line 87
- **Pattern:** Unsafe Code > Dynamic Execution
- **Evidence:** `eval(user_input)` without sanitization
- **Risk:** Arbitrary code execution on the host running the skill.
- **Remediation:** Replace with structured parsing (json.loads,
  ast.literal_eval, or explicit dispatchers).

### Security Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 0     |
| HIGH     | 1     |
| MEDIUM   | 0     |
| LOW      | 0     |
| INFO     | 2     |
```

**Reporting rules:**
- Every finding **must** include a `**Dimension:**` line set to either `Safety`
  or `Security`. This makes the classification unambiguous even when findings
  are quoted out of context.
- If a section has no findings, still emit the section header and a line
  reading `*No findings in this dimension.*`, followed by an empty summary
  table. The reader should never have to wonder whether a dimension was
  scanned.
- The Overall Verdict is FAIL if **either** Safety or Security has CRITICAL
  or HIGH findings.

---

## Finding ID Convention

`SSK-{CATEGORY}-{SEQ}`

| Prefix | Category | Dimension |
|--------|----------|-----------|
| PI | Prompt Injection | Safety |
| EP | Excessive Permissions | Safety |
| IQ | Instruction Quality | Safety |
| SM | Skill Metadata | Safety |
| CS | Credential & Secret | Security |
| DE | Data Exfiltration | Security |
| UC | Unsafe Code | Security |
| SC | Supply Chain | Security |

The category prefix alone tells you which section the finding belongs in.

---

## Severity Decision Matrix

### Safety severity

| Condition | Severity |
|---|---|
| System prompt override / jailbreak instruction | CRITICAL |
| Instructions to disable Claude's safety guardrails | HIGH |
| Skill description deceptively misrepresents purpose (trigger hijacking) | HIGH |
| Overly broad tool access requests beyond stated concept | MEDIUM |
| Dual-use framing without clear safe-use boundaries | MEDIUM |
| Ambiguous or contradictory instructions | LOW |
| Missing description or poor trigger wording | LOW |
| Cosmetic / style issues in instructions | INFO |

### Security severity

| Condition | Severity |
|---|---|
| Hardcoded active credential (API key, token, password) | CRITICAL |
| Arbitrary code execution (eval/exec on untrusted input) | CRITICAL |
| Outbound data exfiltration to external host | HIGH |
| Shell injection vector in script | HIGH |
| Insecure deserialization of untrusted data | HIGH |
| Unpinned dependency from unknown registry | MEDIUM |
| Missing error handling around sensitive operations | MEDIUM |
| Suspicious binary or oversized asset | LOW |
| Cosmetic / style issues in code | INFO |

---

## Reference Files

- `references/scan_patterns.md` — full safety and security check catalog,
  organized by dimension
- `references/github-action.yml` — GitHub Actions PR gate workflow
