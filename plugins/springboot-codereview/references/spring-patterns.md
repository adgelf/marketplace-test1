# Spring-Specific Patterns

Framework-level mistakes — things Checkstyle and SpotBugs can't see because they require understanding Spring semantics.

## Field injection vs constructor injection

Field `@Autowired` is the single most common Spring anti-pattern in older code. Modern Spring documentation discourages it; Spring Boot reference guide explicitly recommends constructor injection. It still compiles, still works, still dominates a lot of pre-2020 codebases.

**Flag when you see:**
- `@Autowired` on a field in new code (any file being added or substantially rewritten).
- `@Autowired` on a field in a test class (`@MockBean` on fields is fine — that's not field injection, it's a test-context mechanism).
- `@Autowired` on a `setXxx` setter without a compelling reason (cyclic dependencies being the usual excuse, but cyclic dependencies are themselves a design issue).

**Why it matters:**
- Constructor injection makes dependencies explicit and the class trivially testable without Spring.
- Final fields are guaranteed initialised after construction — no partial objects.
- Cyclic dependencies fail at construction time (loud), not silently at runtime.
- Enables immutability (`private final`), which is one less reason for concurrency bugs.

**Fix:** Convert to constructor injection. In Spring ≥ 4.3, a single constructor is auto-wired — no `@Autowired` needed. In Lombok-using codebases, `@RequiredArgsConstructor` on the class plus `private final` fields is idiomatic.

```java
// Before
@Service
class OrderService {
    @Autowired private OrderRepository orders;
    @Autowired private NotificationService notifications;
}

// After (plain)
@Service
class OrderService {
    private final OrderRepository orders;
    private final NotificationService notifications;
    OrderService(OrderRepository orders, NotificationService notifications) {
        this.orders = orders;
        this.notifications = notifications;
    }
}

// After (Lombok — if the codebase uses it)
@Service
@RequiredArgsConstructor
class OrderService {
    private final OrderRepository orders;
    private final NotificationService notifications;
}
```

**Severity:** Minor for a single field in existing code following the file's existing pattern. Major when new classes are introduced with field injection — that's new debt.

**Note:** Match codebase convention for the fix — if the surrounding module uses Lombok, recommend Lombok; if Lombok is banned, don't suggest it.

## Business logic in controllers

Controllers should translate HTTP into method calls and back. When business logic drifts in (branching on user role to pick different flows, computing totals, transforming domain objects), it becomes hard to test without `MockMvc`, hard to reuse from schedulers / listeners, and couples HTTP concerns to domain concerns.

**Flag when you see:**
- Multi-step logic in a `@RestController` method (validation + computation + persistence + notification).
- Direct `@Autowired` of repositories in controllers — bypasses the service layer.
- `if`-branching on business state inside a controller: `if (order.getStatus() == PENDING) { ... } else { ... }`.
- `@RestController` method longer than ~15 lines that isn't just request/response mapping.
- Transaction management (`@Transactional`) on controller methods — signals that the controller knows it's doing data work.

**Fix:** Move logic into a `@Service` method named after the use case (`placeOrder`, `cancelSubscription`). Controller becomes: validate → call service → map to response. If there's no service layer yet, suggest creating one; don't silently leave the logic sprawling.

**Severity:** Major for significant logic. Minor when it's a small helper that the author legitimately thought was controller-local.

## Direct repository access from controllers

A specific sub-case of the above, common enough to call out. The service layer exists so that cross-cutting concerns (transactions, authorization, audit, validation) have a home.

**Flag when you see:**
- Controllers calling `*Repository` methods.
- Controllers using `EntityManager` or `JdbcTemplate` directly.

**Fix:** Introduce or use an existing `@Service`. Keep the controller's dependency surface narrow.

**Severity:** Major.

## Transactional boundaries and propagation

`@Transactional` has subtle semantics that cause correctness bugs.

**Flag when you see:**
- A service method that performs multiple writes across repositories with no `@Transactional` — they can half-commit.
- `@Transactional` inside a method that's called from the *same bean* — self-invocation bypasses the proxy, so the annotation is silently ignored. Example:
  ```java
  @Service
  class BillingService {
      public void billAll() { orders.forEach(this::bill); } // not transactional
      @Transactional public void bill(Order o) { ... }       // proxy not triggered
  }
  ```
- `@Transactional(propagation = REQUIRES_NEW)` used without a clear reason. It opens a new physical transaction — legit for "record this even if the outer transaction rolls back" (audit trails) but often cargo-culted.
- `@Transactional(propagation = NESTED)` with a data source that doesn't support savepoints (common on non-JDBC stores) — silently falls back to REQUIRED.
- `@Transactional` with `rollbackFor = Exception.class` or the default (rolls back on runtime only) combined with catching the exception internally — the transaction sees no exception and commits happily.
- `@Transactional` with a long-running external call inside (HTTP, file, long sleep) — holds DB connections the whole time.

**Fix:** Put `@Transactional` on the *use case* boundary (typically a service method that represents one unit of business work), not on individual repo methods. For self-invocation, inject `self` via `@Lazy ObjectProvider<BillingService>` or split the classes. For propagation, start with `REQUIRED` (the default); only escalate when you specifically need REQUIRES_NEW semantics and say so in a comment.

**Severity:** Critical for missing `@Transactional` on multi-step writes where partial failure is dangerous (payment, order placement, permission grants). Major for propagation misuse. Minor for long-running work inside a transaction (connection exhaustion is real but usually not load-bearing in a small service).

## Bean scope and state

Controllers, services, and repositories are singletons by default. Making them stateful is a bug waiting for multi-threaded access.

**Flag when you see:**
- Mutable instance fields on a `@Service` / `@RestController` beyond injected collaborators. (A map being populated at runtime, a counter, a cached last-request.)
- `@Scope("prototype")` on a bean that's then injected into a singleton — it's instantiated once, not per call, unless the caller injects an `ObjectProvider` / `Provider`.
- `@Autowired HttpServletRequest` into a singleton — works via scoped proxy but rare outside framework extensions; often a sign of a design that should use method parameters instead.

**Fix:** Keep state in the DB, in caches, or in request-scoped beans. Mutable fields on a singleton controller are almost never what you want.

**Severity:** Major — these cause heisenbugs in production that are painful to diagnose.

## `@Valid` and `@Validated`

Two different annotations, commonly confused.

- `@Valid` is JSR-380 (Bean Validation). Use on controller method parameters and nested fields inside a DTO to cascade validation.
- `@Validated` is a Spring annotation that enables method-level validation on a class and supports validation groups.

**Flag when you see:**
- `@RequestBody` without `@Valid` on a DTO that has JSR-380 constraints — the constraints are declarative decoration that do nothing.
- `@PathVariable @Min(1) Long id` on a controller method without `@Validated` on the class — the parameter-level constraint is ignored.
- `BindingResult` parameter next to `@Valid` without the controller actually using it — the error-handling path has been silently disabled (exceptions turn into 200s with invalid data).

**Severity:** Major. Missing validation at boundaries is how invalid state enters a system.

## `ResponseEntity` vs direct return

Both are fine — don't flag stylistically. Only flag real issues:

- `ResponseEntity.ok(body)` immediately followed by a manually set `Content-Type` header that contradicts `@RestController` defaults — suspicious.
- Returning `ResponseEntity<Void>` then calling `.body(something)` on it — won't compile but shows up when people are fighting the type system.
- Inconsistency within the same controller (some methods return DTOs directly, some wrap in `ResponseEntity`) — Suggestion, not Major.

## Deprecated Spring APIs (version-dependent)

On Spring Boot 2:
- `RestTemplate` is *not* deprecated but the Spring team recommends `WebClient` for new code. Flag as Suggestion only when the new code is reactive-adjacent.
- `javax.persistence.*` is correct — it's the package you should use.
- `org.springframework.boot.test.mock.mockito.MockBean` is the test annotation.

On Spring Boot 3:
- `javax.persistence.*` in code means the file didn't get migrated — Critical, the code doesn't compile.
- `MockBean` is deprecated in Spring Boot 3.4+ in favour of `@MockitoBean`. Flag as Minor on new code in 3.4+.
- `RestTemplate` is still available but officially in maintenance mode — prefer `RestClient` (new in Boot 3.2) or `WebClient`. Suggestion.
- `WebMvcConfigurerAdapter` is long gone — `WebMvcConfigurer` with default methods.
- `HandlerInterceptorAdapter` is removed — just implement `HandlerInterceptor`.

## Configuration properties pattern

- `@Value("${some.value}")` scattered across beans — hard to find, no validation. Prefer `@ConfigurationProperties` binding to a typed class with `@Validated` constraints.
- `@Value` on a primitive with no default, where absence will fail at bean-create time rather than at startup validation — less informative error.
- Properties read via `Environment.getProperty(...)` in business code — the same pattern. Centralise.

**Severity:** Minor / Suggestion. Don't force a huge refactor for a one-off `@Value`; do suggest `@ConfigurationProperties` when more than a handful of related properties show up.

## Actuator and observability

Flag only when actuator is explicitly involved:
- `management.endpoints.web.exposure.include: *` in production config — exposes everything, including `/heapdump`, `/env`. Critical.
- Actuator endpoint without security — the `/actuator/shutdown` endpoint is the classic foot-gun.
- Custom `Filter` or `HandlerInterceptor` added without checking whether it intercepts `/actuator/**` unintentionally.

## `@Scheduled` misuse

- `@Scheduled(fixedRate = 1000)` on a method that does blocking IO — if the method takes longer than the rate, calls pile up (on single-threaded scheduler). Use `fixedDelay` or configure a multi-thread scheduler.
- `@Scheduled` without `@Async` in an environment with multiple instances — every instance runs it. Usually you want a distributed lock (Shedlock is common) or to run from one leader.
- `@Scheduled` on a method with arguments — won't even bind; Spring logs a warning and skips it.
