# Code Quality Review

These are judgment calls, not lint findings. They're about what makes code painful to change six months from now. Keep the bar calibrated — flag the real ones, let the borderline ones go.

## Method length and cyclomatic complexity

Long methods and tangled branching make changes risky and reviews slow. There's no magic number, but these thresholds are a useful prompt to look twice:

- **Method longer than ~30 lines of real code** (blank lines, braces, and trivial logging don't count). Usually a sign that multiple responsibilities are glued together with blank lines.
- **Cyclomatic complexity > ~10** (each `if`, `&&`, `||`, `case`, `catch`, ternary adds 1). You can approximate by counting branch keywords. Above 10 there are typically untested paths.

**Flag when you see:**
- A method with 40+ lines doing parse → validate → business logic → persistence → response mapping inline.
- A chain of nested `if` / `else` more than 3 deep.
- A `switch` / `if-else-if` ladder that's really a polymorphism opportunity (dispatch on a type).
- A method that would need a multi-sentence `@DisplayName` to describe.

**Fix:** Pull out private helpers named after what they do (`validateRequest`, `buildResponse`, `applyDiscount`). If the method is pure orchestration of too many collaborators, the class might be doing too much — see SRP below.

**Severity:** Minor usually. Major if the method's complexity is obviously the reason a bug slipped in or is about to.

## Single Responsibility violations (the ~7 public methods heuristic)

A class with more than ~7-8 public methods that aren't trivial getters/setters is usually doing two or three things. Not always — a facade legitimately has many methods — but treat it as a prompt.

**Flag when you see:**
- A `UserService` with `createUser`, `updateUser`, `deleteUser`, `sendWelcomeEmail`, `resetPassword`, `exportUsers`, `importUsers`, `syncWithDirectory`, `generateReport`… That's at least three services wearing one `@Service` hat.
- A `Controller` with 12 endpoints that span very different concerns.
- A `*Helper`, `*Util`, `*Manager` class (the name itself is a smell) that grew by accretion.

**Fix:** Suggest a split along the axes of change. Grouping hint: methods that change for the same reason belong together. Email-sending changes with the email templating system; password reset changes with the auth system; exports change with the admin workflow.

**Severity:** Minor. This is a refactor suggestion, not a bug. Only escalate if the diff is clearly adding more responsibility to an already-overloaded class.

## Magic numbers and strings

Numbers and strings with hidden meaning are a tax every reader pays. Checkstyle flags *some* of these, but it misses contextually meaningful literals that aren't obvious to a regex.

**Flag when you see:**
- `Thread.sleep(300000)` (what is 300000? 5 minutes — but that needs a comment or constant).
- `if (user.getRole().equals("ADMIN"))` — string role names scattered across the code. Use an enum or a constant on `SecurityRoles`.
- `new BigDecimal("0.07")` for a tax rate, sales threshold — put it in config (`@Value("${billing.tax-rate}")`) or a named constant.
- HTTP status codes as integers in custom exception handlers: `return 422;` — use `HttpStatus.UNPROCESSABLE_ENTITY`.
- URL prefixes, header names, event names duplicated as string literals.

**Fix:** Named `private static final` constants, enums, or `@ConfigurationProperties` classes. For shared constants, centralise only when truly shared — premature centralisation causes its own cross-module coupling.

**Severity:** Minor, sometimes Suggestion. Don't be pedantic — `x * 2` or `x + 1` don't need constants. `Thread.sleep(30000)` in test setup code doesn't either.

## Null handling on external inputs

Inside a module, Optional / NonNull conventions handle most of this. The real risk is at boundaries — controller inputs, message listeners, external API responses — where a null can walk in and cause an NPE three layers deep.

**Flag when you see:**
- A `@RequestBody` DTO field used directly without a null check, where the class has no `@NotNull` / `@NotBlank` and the controller method has no `@Valid`.
- A webhook / message listener handler that assumes every field is present.
- An external API client that does `response.getData().getItems().stream()...` with no defensive null handling.
- `@Value("${some.value}")` on a `String` with no default, where absence will silently inject `null` and blow up later rather than at startup.

**Fix:** `@Valid` + JSR-380 annotations (`@NotNull`, `@Size`, `@NotBlank`, etc.) on DTOs — fail fast at the controller boundary with a clear 400. For external APIs, wrap the response type or use `Optional.ofNullable(...)` at the ingestion point. For config, `@Value("${some.value:defaultValue}")` or `@ConfigurationProperties` with explicit non-null fields that fail validation at context refresh.

**Severity:** Major on any external boundary. Minor inside a well-controlled internal flow.

## Exception handling

A lot of bad exception code isn't caught by SpotBugs because it's *syntactically* fine.

**Flag when you see:**
- `catch (Exception e)` or `catch (Throwable t)` where the actual recoverable set is a specific type or two. Swallows `InterruptedException`, `OutOfMemoryError`, `NullPointerException` — including ones you wanted to see.
- Empty catch blocks: `} catch (IOException ignored) {}`. Rare cases are legitimate (a `close()` in cleanup), but each one deserves a comment.
- `catch (Exception e) { log.error("something went wrong", e); return null; }` — logging an exception then returning null erases the failure from upstream code.
- `throw new RuntimeException(e)` as a way to avoid declaring a checked exception. It works but loses the type; prefer a specific runtime exception (`IllegalStateException`, domain-specific, or Spring's `DataAccessException` family).
- `catch (InterruptedException e)` without `Thread.currentThread().interrupt()` — drops the interrupt flag, which breaks cooperative cancellation.
- `@ExceptionHandler` returning 500 for every exception — missing per-type handling (validation errors should be 400, not-found should be 404).

**Fix:** Catch what you can handle, let the rest propagate. For recoverable errors, convert to a domain exception (`UserNotFoundException`) and handle centrally in `@ControllerAdvice`. Always preserve the cause: `throw new DomainException("context", e);`. Always re-interrupt after catching `InterruptedException`.

**Severity:** Major for swallowed exceptions and lost interrupts — they cause production debugging nightmares. Minor for overly-broad catches on low-risk paths.

## Returning null vs Optional / empty collection

`return null` is a contract bomb. The caller has to know — but the method signature doesn't say — that null is a valid return, and they have to remember to null-check everywhere.

**Flag when you see:**
- `public User findByEmail(String email)` returning `null` when not found. Should be `Optional<User>`.
- `public List<Order> getOrders()` returning `null` on "no orders". Should return an empty list.
- `public Map<K, V> getMap()` returning `null`. Same — return `Map.of()` / empty map.
- Service methods that return `null` for "error" while *also* throwing for "other errors" — inconsistent.

**Fix:** `Optional<T>` for absence on single-object returns; empty collection for multi-object returns; exceptions for "couldn't complete the operation". Don't use `Optional` as a method parameter or a field — it's designed for return types.

**Severity:** Minor on internal methods. Major on public API / service layer contracts, especially if other code is already calling the method (changing the return type is now a breaking change — consider additive `findByEmailOptional` for now and plan a deprecation).

## DTO / entity leakage

A quick one that's worth catching: returning JPA entities from controllers leaks database concerns into the API, causes lazy-loading surprises during serialization, and makes evolving the schema risky.

**Flag when you see:**
- `@RestController` methods returning entity types directly (especially with lazy relationships).
- `@RequestBody` binding into entity types — the API now accepts every field of the entity, including IDs and audit columns.

**Fix:** Return a DTO (record or POJO). Use a mapper (MapStruct is common; manual constructor mapping is fine for small projects). Bind requests into a request DTO, not an entity.

**Severity:** Minor to Major depending on the entity's complexity and whether the endpoint is already public.

## Naming and readability

Only flag when it actually hurts readability — these are Suggestion level unless egregious:

- Methods named `process`, `handle`, `doStuff` on a service class with multiple siblings named the same way.
- Boolean-returning methods without `is` / `has` / `can` prefix.
- Booleans stored on entities / DTOs named `status` instead of `active`.
- Abbreviations that aren't domain-standard: `usrRpt`, `tranMgr`.

Don't turn a review into a naming debate. Pick one or two that'll sting, mention them, move on.
