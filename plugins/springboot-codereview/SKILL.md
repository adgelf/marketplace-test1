---
name: bizapps-spring-boot-code-review
description: Performs a version-aware code review of Java / Spring Boot changes. Use whenever the user asks for a 'code review', 'review this code', 'review this PR', 'check this change', 'is this safe to merge?', 'look over this diff', or posts a Java / Spring snippet or diff asking for feedback — even if they don't say 'review'. Also use when the user posts Spring Security config, JPA repository/entity code, a `@RestController`, a `@Service`, or a `@Transactional` method and asks any variant of 'how does this look?' or 'anything wrong with this?'. The skill detects the project's Spring Boot / Java / Spring Security / ORM / logging versions first so recommendations match the actual stack, and skips anything Checkstyle or SpotBugs already catches — focusing on design, security, performance, Spring-specific, logging, and test-quality issues.
---

# Spring Boot Code Review

## What this skill is for

Reviewing Java / Spring Boot changes — a single file, a pasted diff, a set of files the user points at, or a PR — and producing a structured, severity-graded report of issues that matter. The point is to catch the things that cause production incidents, security holes, performance cliffs, and maintenance pain: the stuff Checkstyle and SpotBugs don't see because it's about intent, architecture, and framework semantics rather than syntax.

Everything in this skill is built around one principle: **advice that doesn't match the project's actual stack is worse than no advice at all**. Telling a Spring Boot 2.7 / Java 11 team to use `SecurityFilterChain` and records and virtual threads is noise — it burns reviewer trust. So the skill detects first and only then reviews, and the review is always phrased in terms of what the project actually uses plus, separately, what's worth migrating toward.

## The golden rule: detect before you review

Do not start calling things "deprecated" or "wrong" until you know which Spring Boot / Java / Security version the project targets. The same code — `extends WebSecurityConfigurerAdapter`, `javax.persistence.*`, `@Autowired` on a field — can be idiomatic in one repo and tech debt in another. Calibrate, then review.

**Step 1 — build a stack profile.** Read `references/stack-detection.md` and walk through it against the project. You need, at minimum:

- Spring Boot version (`spring-boot` / `spring-boot-starter-parent` in `pom.xml`, or `id("org.springframework.boot")` version in Gradle). 2.x vs 3.x changes a lot: `javax.*` → `jakarta.*`, `WebSecurityConfigurerAdapter` removed, new observability API, native image story, etc.
- Java version (`java.version` / `maven.compiler.release` / `sourceCompatibility`). 11 vs 17 vs 21 changes what you can recommend (records, sealed types, pattern matching, virtual threads).
- Spring Security configuration style — this is the single most common source of "wrong-version advice". See detection checklist.
- ORM / data: is it Spring Data JPA + Hibernate, plain JDBC, Spring Data MongoDB, something else? N+1 advice only makes sense for JPA.
- Logging framework on the classpath (Logback vs Log4j2 — both sit behind SLF4J; the API is the same but config files and async appender patterns differ).
- Whether Micrometer / Actuator are present, so metrics suggestions don't dangle.
- Build system (Maven vs Gradle) — only matters for "how to add X" suggestions.
- A representative neighbour: one existing `@RestController`, one `@Service`, one repository, one security config. Team conventions beat generic best practice; if everyone does constructor injection with Lombok `@RequiredArgsConstructor`, recommend that, not a hand-written constructor.

If you can't determine a signal (e.g. you only got a pasted snippet with no repo access), say so in the report — don't guess. Downgrade to stack-agnostic advice for that dimension and flag it: "Could not determine Spring Security version; advice below assumes 6.x based on `SecurityFilterChain` in the snippet."

**Step 2 — calibrate tone for the detected stack.** A pattern that's "deprecated and should be migrated" in a Spring Boot 3 project is "the correct way for this version" in a Spring Boot 2 project. Never lecture someone for using `WebSecurityConfigurerAdapter` if they're on Security 5 — you can note it as tech debt for a future Spring Boot 3 upgrade, but it's not a bug.

**Step 3 — only now, start reviewing.** Load the relevant checklist files (see "What to look for" below) and walk through the change.

## What not to flag (Checkstyle and SpotBugs handle these)

Skip these — the team's CI already enforces them, and repeating them wastes reviewer attention on the things only you can see:

- Formatting, indentation, import order, brace style, line length.
- Unused imports, unused private fields, unused local variables.
- `==` comparison on boxed types, `equals()` on floats, obvious null-pointer dereferences that SpotBugs catches.
- `System.out.println`, `printStackTrace()` — Checkstyle usually has rules for these.
- Missing `@Override`, missing `final` on obvious immutables.
- Simple "use `StringBuilder` in a loop" type advice.

If you catch yourself writing one of these, stop. Either the team's linter will catch it, or it's already been suppressed for a reason.

## What to look for

Six review dimensions. Each has a checklist reference with concrete patterns, detection heuristics, and fix suggestions that adapt to Spring Boot 2 vs 3.

| Dimension | Read | Typical Critical/Major findings |
|---|---|---|
| Security | `references/security.md` | SQL injection in `@Query`, secrets in logs, missing `@PreAuthorize`, hardcoded credentials, unsafe deserialization, deprecated security APIs |
| Performance | `references/performance.md` | JPA N+1, missing `@Transactional(readOnly = true)`, unpaginated collection loads, blocking calls in `@Async` / reactive, stream anti-patterns |
| Code quality | `references/code-quality.md` | Long methods, SRP violations (too many public methods), magic numbers/strings, catching `Exception`/`Throwable`, empty catch, `return null` where `Optional`/empty collection fits |
| Spring patterns | `references/spring-patterns.md` | Field `@Autowired`, business logic in controllers, direct repo access from controllers, missing `@Transactional` on multi-step writes, wrong propagation, deprecated Spring APIs |
| Logging | `references/logging.md` | Missing context (IDs, user), level misuse (errors as info), string concatenation instead of `{}` placeholders |
| Testing | `references/testing.md` | New code with no tests; tests whose assertions don't actually verify the behaviour (assert-on-mock, assert-not-null only, over-mocked "unit" tests that prove nothing) |

You do not need to read all six files every time. For a diff that only touches `SecurityConfig.java`, reading `security.md` and `spring-patterns.md` is usually enough. For a JPA repository/entity change, `performance.md` and `security.md`. Skim the change first, decide which dimensions are in play, then load those references.

## Severity rubric

A finding is only useful if the reader can tell how much they need to care about it. Use these four levels, and be consistent — don't mark everything Critical, or nothing gets fixed.

- **Critical** — Security vulnerability, data loss risk, correctness bug that will cause an incident. Examples: SQL injection, hardcoded secret committed to source, missing `@Transactional` on a multi-step financial write, auth bypass. Block the merge.
- **Major** — Serious issue the team will regret. Examples: N+1 query on a hot path, catching `Exception` and swallowing it, business logic in a controller that's about to grow, missing authorization on an internal admin endpoint. Should be fixed in this PR or a clear follow-up.
- **Minor** — Real issue but low blast radius. Examples: field injection in a new class (fine today, painful later), magic numbers, missing `readOnly = true` on a read method. Fix if cheap.
- **Suggestion** — Opportunity, not a problem. Examples: "could use a record here", "Optional return would be cleaner", "consider `@EntityGraph`". The author is free to disagree.

When in doubt, go one level lower, not higher. Cry-wolf reviews get ignored.

## Output format

Produce a single structured report. Do not produce anything else first — no "Here's my review:" preamble, no narration of what you looked at. The report is the output.

Use exactly this template. The severity sections and the "Stack detected" block are required; the "Notes" section is optional and should only appear if you actually have something stack-wide worth saying.

````markdown
# Code Review

**Stack detected:** Spring Boot <version>, Java <version>, Spring Security <style>, <ORM>, <logging>, <build>.
<one-line note about anything you couldn't detect, if applicable>

## Critical
<findings, or "None.">

## Major
<findings, or "None.">

## Minor
<findings, or "None.">

## Suggestion
<findings, or "None.">

## Notes
<optional: stack-wide observations, e.g. "Security 5 → 6 migration would unblock removing WebSecurityConfigurerAdapter across the module.">
````

Each finding uses this shape:

````markdown
### <short title>
- **Where:** `path/to/File.java:42` (or `path/to/File.java:42-58` for a range)
- **Issue:** <one or two sentences — what is wrong and why it matters>
- **Fix:** <a concrete suggestion that uses the project's detected stack. Include a minimal code snippet when it clarifies the fix. Reference the current idiom, not a generic one.>
````

A couple of worked examples so the shape is unambiguous:

**Example 1 — Critical, Spring Boot 3 project:**
````markdown
### SQL injection in dynamic @Query
- **Where:** `user/UserRepository.java:47`
- **Issue:** `@Query("SELECT u FROM User u WHERE u.email = '" + email + "'")` concatenates untrusted input into JPQL. An attacker controlling `email` can break out of the literal.
- **Fix:** Use a named or positional parameter — JPA will escape it and the query plan will be cached:
  ```java
  @Query("SELECT u FROM User u WHERE u.email = :email")
  Optional<User> findByEmail(@Param("email") String email);
  ```
  Or — since this is a simple equality — just use the derived-query form `Optional<User> findByEmail(String email);`.
````

**Example 2 — Major, Spring Boot 2 / Security 5 project:**
````markdown
### No authorization on admin endpoint
- **Where:** `admin/AdminController.java:22`
- **Issue:** `DELETE /admin/users/{id}` has no method-level or URL-pattern authorization. Any authenticated user can delete accounts. Module-level `SecurityConfig` only restricts `/admin/**` to `ROLE_ADMIN` on GET, not other verbs.
- **Fix:** Add `@PreAuthorize("hasRole('ADMIN')")` on the handler. Method security is already enabled by `@EnableGlobalMethodSecurity(prePostEnabled = true)` in `SecurityConfig`, so no extra wiring is needed.
````

**Example 3 — Suggestion, Spring Boot 2 / Java 11 project:**
````markdown
### Could migrate config class to Security 6 style
- **Where:** `security/SecurityConfig.java:18`
- **Issue:** Extends `WebSecurityConfigurerAdapter`, which is removed in Spring Security 6. Not a problem today on Security 5, but worth tracking as part of the Spring Boot 3 upgrade.
- **Fix:** When the team moves to Spring Boot 3, refactor to a `SecurityFilterChain` `@Bean`. No action required in this PR.
````

## How to run a review

1. **Read this SKILL.md fully**, then stop and run the detection step on the project (`references/stack-detection.md`). Do not load the other reference files yet.
2. **Read the change.** If given a diff, read it end to end. If given a file or set of files, read them. If given a PR, use whatever tool the environment provides (`gh pr view`, GitHub URL fetch) to pull the diff, then read.
3. **Decide which review dimensions apply.** A security config file doesn't need a JPA performance pass; a repository doesn't need a controller-layer pass. Most changes touch 2-4 of the six.
4. **Load the relevant reference files** and walk through each in order, keeping findings in a scratch list with severity + location.
5. **Sort findings by severity** and write the report using the template above.
6. **Stack-check every fix.** Before finalising, re-read each "Fix:" line and confirm the suggested code actually compiles / works on the detected stack. This is where most embarrassing reviews happen.

## Things worth saying to the user (but only when relevant)

- If the change mixes styles with the rest of the codebase (e.g. a new class uses constructor injection but the surrounding package uses field injection), pick one: recommend matching the neighbours and leave a Suggestion-level note about the codebase-wide inconsistency. Don't try to fix the whole codebase from this review.
- If you detect that Checkstyle / SpotBugs is likely suppressed for the file (`@SuppressWarnings`, `@SuppressFBWarnings`, a `checkstyle-suppressions.xml` entry), mention it once in Notes — suppressions are signals.
- If the project clearly lacks a test file for the new code, that's a single "new code without tests" finding, not one finding per changed method. Don't spam.
- If you couldn't determine the stack (snippet-only review), put that in the Stack detected line — don't invent a version.

Keep these mentions short. Don't narrate the review process in the report itself — findings and fixes only.

## What this skill does NOT do

- It does not run the tests, the build, or any static analyser. The team's CI does that.
- It does not rewrite the code. It suggests fixes; the author applies them.
- It does not duplicate Checkstyle / SpotBugs findings (see "What not to flag").
- It does not open a PR, push a branch, or comment on GitHub. If the user wants inline PR comments, that is a separate action they ask for after reading the report.
- It does not do stylistic / taste review. If a finding can be reasonably disagreed with, it's a Suggestion, not a Major.
