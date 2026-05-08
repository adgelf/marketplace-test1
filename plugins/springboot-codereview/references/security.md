# Security Review

Focus on what Checkstyle / SpotBugs miss: semantics of authentication/authorization, data handling, and version-specific Spring Security mistakes.

## SQL / JPQL injection

Spring Data makes this *easy to do wrong* because `@Query` feels like an annotation, not a string. It is a string.

**Flag when you see:**
- String concatenation inside `@Query` or `@NamedQuery` — either JPQL or native — using any value that comes from a controller input, a header, or any external source.
- Native queries (`@Query(value = "...", nativeQuery = true)`) built with `String.format`, `+`, or `StringBuilder`.
- Dynamic sort / order-by assembled from request params without a whitelist.
- `EntityManager.createNativeQuery(...)` with concatenated strings.
- `JdbcTemplate.queryForList("SELECT ... WHERE name = '" + name + "'")` — yes, this still shows up.

**Fix:** Named parameters (`:name`) or positional (`?1`) for JPQL and native queries. Use `Pageable` with `Sort` and validate allowed sort fields against a whitelist. For programmatic dynamic queries, use the JPA Criteria API or Querydsl — both produce parameterized SQL.

**Severity:** If external input flows into the concatenation, Critical. If the inputs come from trusted internal callers only, Major (still wrong, because the class of bug moves with the code).

## Sensitive data in logs

Even at DEBUG, anything logged eventually ends up in ELK, Datadog, or an archive somebody grep's through. PII and secrets in logs are a compliance incident waiting to happen.

**Flag when you see:**
- Logging a full request or response body: `log.info("request: {}", request)` where `request` contains passwords, tokens, card numbers, health data, addresses.
- Logging an entity via `.toString()` when the entity has sensitive fields — check for `@ToString` on Lombok classes or a custom `toString` that dumps everything.
- Logging authentication-related objects: `Authentication`, `UserDetails`, `OAuth2AccessToken`, JWT claims, session tokens.
- Logging `Map<String, Object>` / headers blindly — `Authorization`, `Cookie`, `Set-Cookie` are usually in there.
- Logging stack traces that include credentials in query strings (JDBC URLs, HTTP URLs).

**Fix:** Log identifiers, not payloads (`log.info("login attempt for userId={}", userId)`). If a field is sensitive on an entity, use Lombok's `@ToString.Exclude` or hand-roll `toString`. For structured logging, use a masking filter / marker. For request/response logging, use a filter that redacts known headers.

**Severity:** Major by default. Critical if it's a password, token, full card number, or PHI.

## Missing authorization

Authentication gates "is this a logged-in user" — authorization gates "are they allowed to do this". Teams often rely on URL-level auth and forget method-level controls, especially for admin features.

**Flag when you see:**
- A controller method that returns or mutates another user's data and there's no `@PreAuthorize`, no ownership check in the service, and no `@PostAuthorize` filter (e.g. `GET /orders/{id}` returning any order by ID).
- An `@Service` method that's clearly privileged (deletes users, refunds money, grants roles) with no `@PreAuthorize` and no explicit check.
- `@PreAuthorize("hasRole('USER')")` on endpoints where every authenticated user implicitly has `ROLE_USER` — that's equivalent to `authenticated()` and gives false reassurance.
- `@PreAuthorize("isAuthenticated()")` on admin endpoints.
- Security config that `.permitAll()` on `/actuator/**` or `/api/internal/**` without an explicit reason.

**Fix:** Prefer method-level `@PreAuthorize` on service methods that enforce business rules (it stays close to the logic). For ownership checks, pass the principal in: `@PreAuthorize("#order.owner == authentication.name")` or add an explicit check inside the service with a clear exception. Enable method security (`@EnableMethodSecurity` on Security 6, `@EnableGlobalMethodSecurity(prePostEnabled = true)` on Security 5).

**Severity:** Critical for missing authorization on mutating endpoints or endpoints that expose other users' data. Major for redundant/weak checks (`hasRole('USER')` everywhere).

## Hardcoded secrets

A password in a test resource is still a committed password. Rotation is the only fix, which is expensive.

**Flag when you see:**
- String literals matching password-, token-, key-, secret-, apikey-shaped names — even in `@Value` defaults (`@Value("${db.password:root}")` is a red flag if `root` is a real default used in any environment).
- Credentials in `application.yml`, `application.properties`, or a `bootstrap.*` file committed to source. The only legitimate values are `${DB_PASSWORD}`-style placeholders or dev-only defaults like `changeme`.
- AWS access key patterns (`AKIA...`), JWT-looking literals, PEM headers (`-----BEGIN`).
- A `KeyPair` / `SecretKey` constructed from a constant `String`.

**Fix:** Move to environment variables, Spring Cloud Config, Vault, AWS Secrets Manager, or whatever the team uses. Replace the constant with a `@Value("${...}")` binding and document where the real value comes from. If the secret was committed, say so in the finding — rotation is needed even after removing the literal.

**Severity:** Critical for anything that looks like a real secret. Major for weak defaults used in dev that could leak to prod via config layering.

## Unsafe deserialization

Less common than it used to be, but the primitives are still there.

**Flag when you see:**
- `ObjectInputStream` / `readObject` on untrusted input. Java native serialization of anything coming from the network or a user.
- Jackson configured with default typing enabled: `ObjectMapper.enableDefaultTyping()`, `activateDefaultTyping(..., LaissezFaireSubTypeValidator.instance, ...)`, or `@JsonTypeInfo(use = Id.CLASS)` on a public API type.
- XStream, SnakeYAML `Yaml()` with no `SafeConstructor`, Kryo on untrusted data.
- `@RequestBody` binding to `Object`, `Map<String, Object>`, or an abstract type with `@JsonTypeInfo` exposed.

**Fix:** Prefer concrete DTOs. For polymorphism, use `BasicPolymorphicTypeValidator` with an allowlist of base types. Replace `Yaml()` with `new Yaml(new SafeConstructor(new LoaderOptions()))`. Never accept Java-serialized blobs from the outside.

**Severity:** Critical when an external input reaches an unsafe deserializer.

## Deprecated security APIs (version-dependent)

**On Spring Security 5:**
- `WebSecurityConfigurerAdapter` is deprecated but not removed. Flag only if the team is planning Spring Boot 3 migration — otherwise it's idiomatic.
- `antMatchers(...)` / `mvcMatchers(...)` are available. Preferred over `regexMatchers`.
- `NoOpPasswordEncoder` usage for "simplicity" — flag as Critical regardless of version.

**On Spring Security 6:**
- `WebSecurityConfigurerAdapter` is removed — if somehow it's in use, the code doesn't compile. Critical if you see it.
- `antMatchers` / `mvcMatchers` / `regexMatchers` are removed. Use `requestMatchers(...)`. Flag any remaining calls as Major (compiler won't catch with the old `HttpSecurity` overload if a shim is around; will at runtime).
- `authorizeRequests()` is deprecated — use `authorizeHttpRequests()`. Flag as Minor (deprecation, not break).
- `@EnableGlobalMethodSecurity` is deprecated in favour of `@EnableMethodSecurity`. Flag as Minor.
- `and()` chain-style DSL still works but the lambda DSL is idiomatic. Leave as Suggestion — don't create churn.

## CSRF, CORS, headers

**Flag when you see:**
- `.csrf().disable()` on a UI-backed app (browser clients). CSRF is safe to disable for pure stateless JWT APIs consumed only by non-browser clients; the surrounding context tells you which.
- `.cors()` configured as permissive (`allowedOrigins("*")` with `allowCredentials(true)`) — that combination is invalid per spec and a clear sign of copy-paste.
- Missing security headers when handling HTML (no HSTS config, `X-Frame-Options` not set on an HTML-serving app).
- Session fixation protection disabled without explanation.

## JWT-specific (common in this codebase)

- Signing with `HS256` + a short string secret ("secret", "mysecret") — Critical.
- Skipping signature verification (`Jwts.parser()` without `.setSigningKey(...)` / `.verifyWith(...)`) — Critical.
- Using `none` algorithm — Critical.
- Not validating `exp`, `iss`, `aud` when the business expects them — Major.
- Caching the parsed claims without cache invalidation on logout/revocation, in a system that has revocation — Major.
- Logging the raw JWT — Major to Critical depending on scope (see "Sensitive data in logs").
