---
name: salesforce-security-review
description: Run Salesforce Code Analyzer (sf scanner) to perform security review of Apex, LWC, and Aura code before AppExchange Security Review submission.
argument-hint: "[target-path] [--dfa]"
disable-model-invocation: true
allowed-tools: Bash(sf scanner *) Bash(sf plugins *) Read Glob Grep
---

# Salesforce Security Review

Run Salesforce Code Analyzer to find security vulnerabilities, code quality issues, and best practice violations in Salesforce code (Apex, LWC, Aura, Visualforce).

## Steps

### 1. Verify sf scanner is installed

```!
sf plugins --core 2>/dev/null | grep -i scanner || echo "SCANNER_NOT_FOUND"
```

If the scanner plugin is not installed, inform the user and suggest:
```
sf plugins install @salesforce/sfdx-scanner
```

### 2. Determine the scan target

- If `$ARGUMENTS` is provided and does not start with `--`, use it as the target path
- Otherwise, default to `force-app`

### 3. Run the Security Scan

Run the scanner with the **Security** category focused:

```bash
sf scanner run --target "<target-path>" --category "Security" --format table --severity-threshold 3
```

### 4. If `--dfa` flag is passed in arguments, also run DFA analysis

```bash
sf scanner run:dfa --target "<target-path>" --projectdir . --format table
```

DFA (Data Flow Analysis) performs deeper analysis for issues like CRUD/FLS violations and injection vulnerabilities. It takes longer but catches more issues.

### 5. Generate HTML report

After the table output, also generate a detailed HTML report:

```bash
sf scanner run --target "<target-path>" --category "Security" --format html --outfile security-review-report.html
```

### 6. Analyze and summarize results

After running the scan, provide a structured summary:

**Summary format:**

#### Critical Issues (Severity 1)
List all critical security issues that MUST be fixed before Security Review submission.

#### High Issues (Severity 2)
List high-severity issues that should be fixed.

#### Medium Issues (Severity 3)
List medium-severity issues to consider.

#### Recommendations
- Specific fixes for each issue found
- Links to relevant Salesforce security documentation
- Common patterns that cause Security Review failures

### Common Security Review failure reasons to check for:
- **CRUD/FLS violations** - not checking object/field permissions before DML
- **SOQL/SOSL injection** - dynamic queries without escaping
- **XSS vulnerabilities** - unescaped output in Visualforce/LWC
- **Hardcoded secrets** - credentials, API keys in code
- **Insecure endpoints** - HTTP instead of HTTPS
- **Missing sharing rules** - classes without explicit sharing declaration
- **Open redirects** - unvalidated redirect URLs
- **CSRF vulnerabilities** - missing CSRF tokens in forms
