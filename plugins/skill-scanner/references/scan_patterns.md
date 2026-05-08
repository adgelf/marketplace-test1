# Skill Scanner — Pattern Catalog

This is the full catalog of checks the scanner runs, organized by dimension.
Read this file when you need the precise pattern definitions, regex sources,
or rationale for a finding.

The catalog is split into two top-level sections that mirror the report
structure:

- **Safety patterns** — concept/intent issues, mostly judged by reading the
  skill's natural-language instructions and metadata
- **Security patterns** — technical vulnerabilities in code, files, and
  dependencies, mostly judged by deterministic regex/AST matching

Each pattern entry follows the same schema:

```
### SSK-{PREFIX}-{NNN}: <short title>
- **Dimension:** Safety | Security
- **Category:** <full category name>
- **Default severity:** CRITICAL | HIGH | MEDIUM | LOW | INFO
- **Detection:** how the scanner finds it (regex / AST / LLM judgment)
- **Why it matters:** the underlying risk
- **Remediation:** how to fix
```

Severity is a *default* — the scanner can upgrade or downgrade based on
context (e.g. a hardcoded credential in a comment vs. an active key).

---

## Table of Contents

### Safety patterns (concept/intent)
1. Prompt Injection (PI) — SSK-PI-001 … 005
2. Excessive Permissions (EP) — SSK-EP-001 … 003
3. Instruction Quality (IQ) — SSK-IQ-001 … 004
4. Skill Metadata (SM) — SSK-SM-001 … 003

### Security patterns (technical vulnerabilities)
5. Credential & Secret Exposure (CS) — SSK-CS-001 … 005
6. Data Exfiltration (DE) — SSK-DE-001 … 003
7. Unsafe Code Patterns (UC) — SSK-UC-001 … 006
8. Supply Chain (SC) — SSK-SC-001 … 004

---

# SAFETY PATTERNS

These patterns address the skill's **concept and intent**. Detection is
primarily LLM-based: pattern matching on natural-language instructions is
brittle, so the scanner sends the SKILL.md body and frontmatter to Claude
along with a structured rubric. Regex is used only as a quick pre-filter to
flag obvious cases.

## 1. Prompt Injection (PI)

Instructions inside the skill that try to override Claude's system prompt,
bypass safety reasoning, or jailbreak the model.

### SSK-PI-001: System prompt override
- **Dimension:** Safety
- **Category:** Prompt Injection
- **Default severity:** CRITICAL
- **Detection:** LLM rubric + regex pre-filter for phrases like
  `you are no longer`, `ignore (your )?(previous|prior|system) (instructions|prompt)`,
  `disregard .* (instructions|prompt|guidelines)`, `forget (everything|all) (above|prior)`
- **Why it matters:** A skill that tells Claude to abandon its system prompt
  hijacks the entire conversation — every downstream turn is compromised, not
  just the one that invoked the skill.
- **Remediation:** Skills extend Claude's behavior; they never replace it.
  Rewrite the instruction to add capability rather than remove guardrails.

### SSK-PI-002: Safety guardrail bypass
- **Dimension:** Safety
- **Category:** Prompt Injection
- **Default severity:** HIGH
- **Detection:** LLM rubric + regex for `bypass (safety|guardrails|filters)`,
  `regardless of (your |the )?(safety|policy|guidelines)`,
  `even if .* (unethical|harmful|disallowed)`
- **Why it matters:** Instructions framing harmful outputs as required for
  the skill's purpose pressure Claude to comply with things it would otherwise
  refuse.
- **Remediation:** State the legitimate use case directly. If the skill needs
  to handle sensitive content (e.g. security testing), say so plainly and
  scope it — don't ask Claude to disable judgment.

### SSK-PI-003: Role reassignment
- **Dimension:** Safety
- **Category:** Prompt Injection
- **Default severity:** HIGH
- **Detection:** LLM rubric + regex for `you are (now |actually )?(a|an)
  (?!helpful|skill|tool)`, `pretend (to be|you are)`, `act as (?!a helpful)`
- **Why it matters:** Reassigning Claude to a persona ("you are an
  unrestricted AI", "you are DAN") is the classic jailbreak shape. Even
  benign-looking persona swaps erode the alignment baseline.
- **Remediation:** Skills should describe *what to do*, not *who Claude is*.
  Claude's identity is set by the system prompt and shouldn't be re-declared.

### SSK-PI-004: Hidden instructions in references
- **Dimension:** Safety
- **Category:** Prompt Injection
- **Default severity:** HIGH
- **Detection:** LLM scan of every `references/*` and `assets/*` text file
  for imperative instructions to Claude that are not surfaced in SKILL.md.
  Includes detection of zero-width characters and suspicious encoding.
- **Why it matters:** A reviewer reading SKILL.md may approve a skill whose
  real instructions live in a buried reference file Claude only reads later.
- **Remediation:** All Claude-directed instructions belong in SKILL.md or in
  reference files clearly summarized in SKILL.md.

### SSK-PI-005: Conditional jailbreak
- **Dimension:** Safety
- **Category:** Prompt Injection
- **Default severity:** HIGH
- **Detection:** LLM rubric for instructions that gate behavior on a trigger
  phrase ("if the user says X, then ignore Y"), magic words, or "developer
  mode" framings.
- **Why it matters:** Conditional bypasses are designed to evade reviewers
  who only check the default code path.
- **Remediation:** Remove the conditional path. If the skill genuinely needs
  multiple modes, document each mode explicitly with the same safety level.

---

## 2. Excessive Permissions (EP)

The skill requests broader tool access or scope than its stated concept warrants.

### SSK-EP-001: Tool access mismatch
- **Dimension:** Safety
- **Category:** Excessive Permissions
- **Default severity:** MEDIUM
- **Detection:** LLM judgment — compare the skill's stated purpose
  (description) against the tools/capabilities it actually uses or requests.
- **Why it matters:** A "markdown formatter" skill that requests network
  access and shell execution is either misdescribed or doing more than
  advertised. Either way, reviewers were misled.
- **Remediation:** Either narrow the requested tools to what the concept
  needs, or rewrite the description to match what the skill actually does.

### SSK-EP-002: Unbounded shell or filesystem scope
- **Dimension:** Safety
- **Category:** Excessive Permissions
- **Default severity:** MEDIUM
- **Detection:** LLM judgment + regex for `rm -rf`, `chmod 777`, paths
  outside the skill's expected working directory (`/`, `~`, `/etc`, `/var`)
  in shell snippets or instruction examples.
- **Why it matters:** Even if the code path is benign today, instructing
  Claude to operate at root or recurse from `/` invites future foot-guns.
- **Remediation:** Scope shell and filesystem operations to a clearly named
  workspace directory.

### SSK-EP-003: Unrestricted tool invocation
- **Dimension:** Safety
- **Category:** Excessive Permissions
- **Default severity:** LOW
- **Detection:** LLM judgment — instructions like "use any tool you have
  access to" or "feel free to invoke whatever you need" without scoping.
- **Why it matters:** Vague tool guidance leads to inconsistent and
  potentially excessive tool use.
- **Remediation:** Enumerate the tools the skill actually needs.

---

## 3. Instruction Quality (IQ)

Ambiguous, contradictory, or missing guidance that causes unpredictable
Claude behavior.

### SSK-IQ-001: Contradictory instructions
- **Dimension:** Safety
- **Category:** Instruction Quality
- **Default severity:** LOW
- **Detection:** LLM judgment — the SKILL.md gives mutually incompatible
  directives (e.g. "always validate input" + "skip validation for trusted
  sources" with no definition of trusted).
- **Why it matters:** Claude resolves contradictions inconsistently across
  runs, leading to non-deterministic safety posture.
- **Remediation:** Pick one path or define the disambiguating condition
  precisely.

### SSK-IQ-002: Ambiguous error handling
- **Dimension:** Safety
- **Category:** Instruction Quality
- **Default severity:** LOW
- **Detection:** LLM judgment — the skill describes a happy path but no
  failure mode (what to do when a tool errors, when input is malformed,
  when prerequisites are missing).
- **Why it matters:** Without explicit failure guidance, Claude may invent
  recovery behavior — sometimes silently swallowing errors, sometimes
  retrying destructively.
- **Remediation:** For each major step, say what Claude should do on
  failure (retry once, ask the user, abort with a clear message, etc.).

### SSK-IQ-003: Vague success criteria
- **Dimension:** Safety
- **Category:** Instruction Quality
- **Default severity:** LOW
- **Detection:** LLM judgment — no stated definition of "done" or
  acceptable output shape.
- **Why it matters:** Without success criteria, Claude over- or
  under-delivers depending on conversational momentum.
- **Remediation:** Specify the output format and what counts as a
  successful run.

### SSK-IQ-004: Missing or empty SKILL.md
- **Dimension:** Safety
- **Category:** Instruction Quality
- **Default severity:** CRITICAL
- **Detection:** File existence + minimum line count.
- **Why it matters:** A skill without instructions is a trigger surface
  with no guardrails.
- **Remediation:** Author proper SKILL.md content per the
  [skill-creator guide](https://github.com/anthropics/skills).

---

## 4. Skill Metadata (SM)

Deceptive descriptions, trigger hijacking, name conflicts, or framing that
misrepresents what the skill actually does.

### SSK-SM-001: Description hijacking
- **Dimension:** Safety
- **Category:** Skill Metadata
- **Default severity:** HIGH
- **Detection:** LLM judgment — the description claims overly broad
  applicability ("use for everything", "always use this skill", "for any
  question") to capture triggers it shouldn't own.
- **Why it matters:** A skill that triggers on everything inserts itself
  into conversations where reviewers never expected it to act.
- **Remediation:** Scope the description to the skill's actual domain.

### SSK-SM-002: Concept-description mismatch
- **Dimension:** Safety
- **Category:** Skill Metadata
- **Default severity:** HIGH
- **Detection:** LLM judgment — the description and the SKILL.md body
  describe meaningfully different things.
- **Why it matters:** Reviewers approve based on the description but
  Claude executes based on the body. Mismatch = backdoor.
- **Remediation:** Bring description and body into alignment.

### SSK-SM-003: Missing or malformed frontmatter
- **Dimension:** Safety
- **Category:** Skill Metadata
- **Default severity:** MEDIUM
- **Detection:** YAML parser on frontmatter; required fields `name` and
  `description`.
- **Why it matters:** Without proper metadata the skill won't trigger
  cleanly and may shadow other skills by name collision.
- **Remediation:** Add valid YAML frontmatter with `name` and a meaningful
  `description`.

---

# SECURITY PATTERNS

These patterns address **technical vulnerabilities** in the skill's
artifacts. Detection is deterministic — regex, AST walks, and structural
file checks. No LLM judgment is required for the security pass.

## 5. Credential & Secret Exposure (CS)

### SSK-CS-001: Hardcoded API key
- **Dimension:** Security
- **Category:** Credential & Secret Exposure
- **Default severity:** CRITICAL
- **Detection:** Regex for known key prefixes:
  - OpenAI: `sk-(proj-)?[A-Za-z0-9]{20,}`
  - Anthropic: `sk-ant-[A-Za-z0-9_-]{20,}`
  - AWS access key: `AKIA[0-9A-Z]{16}`
  - GitHub: `ghp_[A-Za-z0-9]{36}`, `gho_[A-Za-z0-9]{36}`, `ghs_[A-Za-z0-9]{36}`
  - Google: `AIza[0-9A-Za-z_-]{35}`
  - Slack: `xox[baprs]-[A-Za-z0-9-]{10,}`
- **Why it matters:** A live credential in a public skill repo is a same-day
  compromise.
- **Remediation:** Rotate the key immediately. Read credentials from
  environment variables at runtime.

### SSK-CS-002: Generic high-entropy secret
- **Dimension:** Security
- **Category:** Credential & Secret Exposure
- **Default severity:** HIGH
- **Detection:** Shannon entropy >= 4.5 on string literals >= 20 chars,
  excluding known-safe patterns (UUIDs, SHA hashes in lockfiles).
- **Why it matters:** Likely a token, password, or signing secret even if
  the prefix isn't recognized.
- **Remediation:** Move to environment variables or a secret manager.

### SSK-CS-003: Private key material
- **Dimension:** Security
- **Category:** Credential & Secret Exposure
- **Default severity:** CRITICAL
- **Detection:** Regex for PEM headers: `-----BEGIN (RSA |EC |DSA |OPENSSH |
  ENCRYPTED )?PRIVATE KEY-----`.
- **Why it matters:** Private keys in source repos enable impersonation and
  signing attacks.
- **Remediation:** Rotate the key. Never commit private key material.

### SSK-CS-004: Database connection string with embedded password
- **Dimension:** Security
- **Category:** Credential & Secret Exposure
- **Default severity:** HIGH
- **Detection:** Regex for `(postgres|mysql|mongodb|redis)://[^:]+:[^@]+@`.
- **Why it matters:** Connection strings in code expose both credentials
  and infrastructure topology.
- **Remediation:** Build connection strings at runtime from environment
  variables.

### SSK-CS-005: Hardcoded password literal
- **Dimension:** Security
- **Category:** Credential & Secret Exposure
- **Default severity:** HIGH
- **Detection:** Regex for `(password|passwd|pwd|secret|token)\s*[=:]\s*
  ["'][^"']{4,}["']` excluding obvious placeholders (`<password>`,
  `your-password-here`, `xxx`).
- **Why it matters:** Even if the value is currently a test value, the
  pattern normalizes embedding live secrets.
- **Remediation:** Read from environment or prompt at runtime.

---

## 6. Data Exfiltration (DE)

### SSK-DE-001: Outbound network call to non-allowlisted host
- **Dimension:** Security
- **Category:** Data Exfiltration
- **Default severity:** HIGH
- **Detection:** AST walk of Python scripts for `requests.*`, `urllib.*`,
  `httpx.*`, `socket.*` calls. Extract destination host. Compare against
  scanner config allowlist (default: empty — every external host is flagged).
- **Why it matters:** A skill that sends conversation context, files, or
  user input to an external host is an exfiltration channel.
- **Remediation:** Remove the call, or document the destination in SKILL.md
  and add it to the scanner's allowlist.

### SSK-DE-002: Webhook or telemetry endpoint
- **Dimension:** Security
- **Category:** Data Exfiltration
- **Default severity:** HIGH
- **Detection:** Regex for URL string literals matching webhook patterns:
  `discord.com/api/webhooks`, `hooks.slack.com`, `webhook.site`, `requestbin`,
  `pipedream.com`, plus `*.ngrok.io`, `*.serveo.net`.
- **Why it matters:** These endpoints exist specifically to receive data
  from untrusted sources.
- **Remediation:** Remove the endpoint reference.

### SSK-DE-003: Instructions to send data externally
- **Dimension:** Security
- **Category:** Data Exfiltration
- **Default severity:** HIGH
- **Detection:** Regex on SKILL.md and references for imperatives like
  `send (this|the) (output|conversation|data) to`, `POST (this|to)
  https?://`, `email (this|the) (results?|output) to`.
- **Why it matters:** Even without code, an instruction to Claude to
  transmit data is enough to trigger exfiltration via Claude's tools.
- **Remediation:** Remove the instruction.

---

## 7. Unsafe Code Patterns (UC)

### SSK-UC-001: eval / exec on dynamic input
- **Dimension:** Security
- **Category:** Unsafe Code
- **Default severity:** CRITICAL
- **Detection:** Python AST for `Call(func=Name(id='eval'|'exec'))` where
  the argument is not a string literal. Shell scripts: regex for `eval
  "$..."` or `bash -c "$..."`.
- **Why it matters:** Arbitrary code execution on the host running the
  skill.
- **Remediation:** Replace with structured parsing — `json.loads`,
  `ast.literal_eval`, explicit dispatchers, or `subprocess` with an argv list.

### SSK-UC-002: Shell command injection via string concatenation
- **Dimension:** Security
- **Category:** Unsafe Code
- **Default severity:** HIGH
- **Detection:** Python AST for `subprocess.*(shell=True, ...)` where the
  command argument involves f-strings, `.format()`, or `+` with a non-literal.
  Shell: regex for `$(...)` or backticks containing variables.
- **Why it matters:** User input concatenated into a shell command yields
  command injection.
- **Remediation:** Use `subprocess.run([...], shell=False)` with an argv
  list. Never interpolate untrusted input into a shell string.

### SSK-UC-003: Path traversal
- **Dimension:** Security
- **Category:** Unsafe Code
- **Default severity:** HIGH
- **Detection:** Python AST — file open / read calls where the path is
  built from user input without `os.path.realpath` containment check, or
  where `../` appears in a literal path.
- **Why it matters:** Reads or writes outside the intended directory; can
  expose `/etc/passwd`, SSH keys, or overwrite critical files.
- **Remediation:** Resolve the path with `os.path.realpath` and verify it
  starts with the intended base directory.

### SSK-UC-004: Insecure deserialization
- **Dimension:** Security
- **Category:** Unsafe Code
- **Default severity:** HIGH
- **Detection:** Python AST for `pickle.load`, `pickle.loads`,
  `yaml.load` (without `Loader=SafeLoader`), `marshal.load`.
- **Why it matters:** Pickle and unsafe YAML deserialization yield RCE on
  attacker-controlled input.
- **Remediation:** Use `json`, `yaml.safe_load`, or `msgpack`.

### SSK-UC-005: Disabled TLS verification
- **Dimension:** Security
- **Category:** Unsafe Code
- **Default severity:** MEDIUM
- **Detection:** Regex/AST for `verify=False`, `InsecureRequestWarning`,
  `ssl._create_unverified_context`, `curl -k`, `curl --insecure`,
  `wget --no-check-certificate`.
- **Why it matters:** MITM exposure on every outbound request.
- **Remediation:** Enable verification. If targeting a self-signed cert,
  pin the CA explicitly.

### SSK-UC-006: Hardcoded temp path with predictable name
- **Dimension:** Security
- **Category:** Unsafe Code
- **Default severity:** LOW
- **Detection:** Regex for `/tmp/[a-z_-]+(\.\w+)?` as a literal path
  (suggests no `tempfile.mkstemp` usage).
- **Why it matters:** Predictable temp paths enable symlink races on
  shared hosts.
- **Remediation:** Use `tempfile.NamedTemporaryFile` or `mkstemp`.

---

## 8. Supply Chain (SC)

### SSK-SC-001: Unpinned dependency
- **Dimension:** Security
- **Category:** Supply Chain
- **Default severity:** MEDIUM
- **Detection:** Parse `requirements.txt`, `pyproject.toml`,
  `package.json` — flag entries without a version specifier or with `>=`
  / `^` / `~` only.
- **Why it matters:** Unpinned dependencies pull whatever is current at
  install time, enabling supply chain attacks via compromised upstream
  releases.
- **Remediation:** Pin to exact versions or use a lockfile.

### SSK-SC-002: Dependency from unknown registry
- **Dimension:** Security
- **Category:** Supply Chain
- **Default severity:** MEDIUM
- **Detection:** Parse package files for `--index-url`, `--extra-index-url`,
  npm `registry =`, or git+https dependencies. Flag any host not in the
  scanner's known-registry allowlist (PyPI, npm registry, crates.io).
- **Why it matters:** A skill pulling from an attacker-controlled mirror
  bypasses package ecosystem trust.
- **Remediation:** Use the canonical registry or document and allowlist
  the alternative.

### SSK-SC-003: Post-install hook
- **Dimension:** Security
- **Category:** Supply Chain
- **Default severity:** HIGH
- **Detection:** Parse `package.json` for `scripts.postinstall`,
  `scripts.preinstall`. Parse `setup.py` for `cmdclass` overrides.
- **Why it matters:** Install hooks run with the user's permissions on a
  context (`pip install`) that's often invoked with elevated trust.
- **Remediation:** Move setup work into the skill's runtime entry points.

### SSK-SC-004: Dependency on a typosquat candidate
- **Dimension:** Security
- **Category:** Supply Chain
- **Default severity:** HIGH
- **Detection:** Levenshtein distance <= 2 from a curated list of popular
  package names (numpy, requests, urllib3, django, flask, react, lodash,
  etc.) where the dependency name is not the popular package itself.
- **Why it matters:** Classic supply chain attack vector (`requets`,
  `urlib3`, `loadash`).
- **Remediation:** Verify the package is the intended one. If it's a
  typo, fix it; if it's intentional, document why.

---

## How patterns feed the report

Every finding emitted by the scanner cites a pattern ID from this catalog.
The pattern's **Dimension** field determines which report section the
finding lands in (`## Safety Findings` vs `## Security Findings`). The
**Default severity** seeds the finding's severity, which the scanner may
adjust based on context (e.g. a credential found inside a doc comment
example may be downgraded from CRITICAL to LOW with the rationale recorded).
