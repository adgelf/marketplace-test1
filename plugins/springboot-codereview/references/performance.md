# Performance Review

Focus on patterns that cause production-scale problems but look innocent in a small PR diff. The theme is that data-access code is where most Spring Boot performance issues live, and they all start cheap.

## JPA N+1 queries

Most common performance bug in Spring Boot code. One query returns N entities; accessing a lazy association on each emits N more queries. Tests pass (small fixture), production melts (thousand-item page).

**Flag when you see:**
- A service method that iterates over a list of entities and accesses a lazy-loaded association inside the loop — collections (`OneToMany`, `ManyToMany`) are lazy by default; `ManyToOne` / `OneToOne` are eager by default but frequently set `fetch = LAZY` by teams who "read somewhere it's better".
- `JpaRepository.findAll()` / `findAllById(...)` returning entities whose mapped fields the caller then traverses.
- Streams in a service that map entities into DTOs via `.map(e -> new Dto(e.getParent().getName(), e.getItems().size()))`.
- `@OneToMany(fetch = EAGER)` — the opposite mistake. Every load of the parent fetches all children, usually not what you want either.

**Fix (all JPA-based, pick one):**
- For query-specific fetch control: add a JPQL `FETCH JOIN`:
  ```java
  @Query("SELECT DISTINCT o FROM Order o LEFT JOIN FETCH o.items WHERE o.customer.id = :id")
  List<Order> findByCustomerIdWithItems(@Param("id") Long id);
  ```
- For reusable fetch planning: `@EntityGraph` (available on Spring Data JPA):
  ```java
  @EntityGraph(attributePaths = {"items", "items.product"})
  List<Order> findByCustomerId(Long customerId);
  ```
- For ad-hoc queries, project straight to a DTO — skip the entity hydration entirely. Spring Data supports interface projections and `@Query` with a constructor expression.
- Keep fetch type LAZY on the mapping; control fetch per query. `EAGER` on entity mappings is almost always wrong at scale.

**Severity:** Major on hot paths (list endpoints, nightly jobs over many rows). Minor on clearly bounded lookups (one parent with a handful of children on a detail page).

**Note for reactive / Spring Data JDBC / Mongo:** N+1 is a JPA-laziness phenomenon. Spring Data JDBC has no lazy loading (it's eager by design — different tradeoff). Mongo's `@DBRef` has its own fetch behaviour; flag `@DBRef` collections traversed in a loop, but the fix is different (embed or batch).

## Missing `@Transactional(readOnly = true)`

Read-only transactions let Hibernate skip dirty checking, allow the JDBC driver to route to a read replica (when configured), and prevent accidental writes. Every repo read should have it.

**Flag when you see:**
- `@Transactional` with no `readOnly` attribute on a method that only reads.
- A `@Service` read method with no `@Transactional` at all, calling into a repository. It "works" because Spring Data wraps the repo call, but each call gets its own tiny transaction — no consistency across multiple repo calls, and LazyInitializationException on any lazy navigation outside the repo frame.
- `@Transactional(readOnly = true)` with writes inside — catches a copy-paste mistake.

**Fix:**
```java
@Transactional(readOnly = true)
public OrderView getOrder(long id) { ... }
```
For classes that are read-heavy, put `@Transactional(readOnly = true)` at the class level and annotate write methods individually with `@Transactional`.

**Severity:** Minor usually; Major for read methods that traverse lazy associations without an outer transaction (they work only because `spring.jpa.open-in-view=true`, which is itself a smell — see below).

## `spring.jpa.open-in-view = true`

Spring Boot's default. Keeps the Hibernate session open through the view render, masking N+1 and forgotten joins. Code that relies on it breaks the moment the property is turned off or when the same service is called from a non-HTTP context (scheduler, message listener).

**Flag when you see:**
- Lazy association traversal in the controller layer (usually via a Jackson serializer walking the entity).
- No explicit `@Transactional` on the service read, relying on OSIV to hold the session open.
- `open-in-view: true` explicitly set (or the default left on) in a non-trivial project.

**Fix:** Turn it off (`spring.jpa.open-in-view: false` in `application.yml`), then fix the fallout — explicit `@Transactional(readOnly = true)` on reads, DTO projections for API responses, fetch joins where needed.

**Severity:** Suggestion (for the config) plus Major (for any specific N+1 exposed by turning it off). Don't flag OSIV as Critical — it's the Spring Boot default and removing it is a cross-cutting change.

## Unbounded collection loads

A `findAll()` or `findByStatus(Status.ACTIVE)` on a growing table is fine on day one and catastrophic on day 365. Memory blows up, GC thrashes, the endpoint times out.

**Flag when you see:**
- Any repository method returning `List<T>` where the underlying table grows with business activity (orders, messages, events, audit rows) and the caller doesn't slice it.
- `findAll()` used by a controller to return a list to a UI.
- `StreamSupport.stream(repository.findAll().spliterator(), false)` — the damage is already done by the `findAll()`.
- Loops that load all IDs then iterate: `repository.findAllIds().forEach(id -> process(id))` for a non-trivial table.

**Fix:**
- Endpoints: return `Page<T>` with a `Pageable` parameter. Spring MVC resolves `Pageable` from query params automatically.
- Background jobs: use `Slice<T>` with a key-based cursor (`findByIdGreaterThanOrderById(...)`), or Spring Batch if it's a real ETL.
- Streaming: `Stream<T>` return types on a repo method with `@QueryHints(@QueryHint(name = HINT_FETCH_SIZE, value = "1000"))` plus a consuming `@Transactional` method. Close the stream.

**Severity:** Major by default; Critical if the endpoint is already in production on a known-large table.

## Blocking calls in async / reactive contexts

Reactor (`Mono` / `Flux`) and Spring WebFlux demand non-blocking operations on the event loop thread. One `Thread.sleep`, one `restTemplate.getForObject`, or one JDBC call, and the thread is gone — latency spikes across all in-flight requests.

**Flag when you see:**
- A `Mono.fromCallable(() -> jdbcTemplate.queryForList(...))` with no `.subscribeOn(Schedulers.boundedElastic())` — looks like it's non-blocking but runs on the reactive thread.
- `RestTemplate` / `HttpClient.send()` inside a `Flux.map(...)` or `.flatMap(...)`.
- `Thread.sleep` anywhere in reactive code — use `Mono.delay(...)`.
- `@Async` methods that call a blocking IO library but with no `Executor` configured, or shared with other `@Async` pools — the default Spring `@Async` executor is a `SimpleAsyncTaskExecutor` that creates a new thread per call (unbounded).
- `CompletableFuture.supplyAsync(...)` in a hot path without a custom executor (uses the common ForkJoinPool — bad for IO-heavy work).

**Fix:**
- Reactive: use `WebClient` instead of `RestTemplate`. For unavoidable blocking, wrap with `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())`.
- `@Async`: define a named `TaskExecutor` bean sized for the workload; reference it as `@Async("myExecutor")`.
- WebFlux: don't introduce JPA — use R2DBC if possible, otherwise offload to a bounded elastic scheduler and document the hop.

**Severity:** Major. Critical when it's a WebFlux endpoint doing synchronous JDBC — that's a production liability.

## Stream / collection anti-patterns

Not Checkstyle's domain; Checkstyle won't flag wasteful chains that look valid.

**Flag when you see:**
- `.collect(toList()).stream()` — materialising then re-streaming. Usually the author wanted `.toList()` (Java 16+) or to keep streaming.
- `list.stream().filter(...).findFirst().isPresent()` — that's `list.stream().anyMatch(...)`.
- `map(Foo::getBar).collect(toList()).size()` — that's `(int) list.stream().map(Foo::getBar).count()` or just `list.size()` if the mapping is 1:1 non-filtering.
- `Collectors.toMap` without a merge function on a stream that could have duplicate keys — throws `IllegalStateException` at runtime on collisions.
- `.parallelStream()` on an IO-bound pipeline (JPA calls, HTTP calls). Parallel streams use the common ForkJoinPool; blocking it starves the whole JVM.
- `list.stream().sorted(...).limit(N)` for a huge list when `N << list.size()` — consider a bounded priority queue.
- `Collection.stream().collect(Collectors.toList())` on Java 16+ — use `.toList()` (returns unmodifiable list; fine for 99% of uses).

**Severity:** Minor unless it's on a hot path or causes a runtime failure (like toMap-without-merge on real data) — then Major.

## Caching opportunities / mistakes

Flag only when caching is explicitly involved — don't speculate.

- `@Cacheable` on a method whose input includes a mutable object without a proper `key = "#user.id"` — silently re-fetches every time because the default key uses `SimpleKey`, which relies on `equals`.
- `@Cacheable` with a `Page<T>` / `Stream<T>` / reactive return type — unsafe; the framework can serialise the cached instance on some backends but semantically breaks pagination.
- `@CachePut` / `@Cacheable` on a method that's called within the same bean — proxies don't self-invoke, the annotation is ignored.
- Caching a reference to a JPA entity — detached from the session, dangerous.

**Severity:** Major when the cache is silently not working; Minor for self-invocation in code that doesn't depend on the cache for correctness.

## Repetitive computation or logging

- Computing the same thing inside a loop: `for (var o : orders) log.info("processing {}", o.getCustomer().getName())` — if `getCustomer()` triggers a fetch, that's an N+1 disguised as logging.
- Building the same `Map` / `List` inside a tight loop instead of hoisting it outside.

These are easy to miss because they look like "normal code". Worth one line in a review when they add up on a hot path.
