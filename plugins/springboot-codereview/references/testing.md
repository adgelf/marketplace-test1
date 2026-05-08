# Test-Quality Review

You are not writing tests here — the `spring-boot-testing` skill does that. You are reviewing whether the tests that accompany the change actually verify anything. Missing tests and tests-that-don't-test are the two failure modes.

## Missing tests

New production code with no accompanying test is a Major finding by default. Exceptions exist (trivial getters, DTOs, obvious plumbing), but err on the side of flagging.

**Flag when you see:**
- A new `@Service` method with business logic and no corresponding test method.
- A new `@RestController` endpoint with no controller test or integration test.
- A new `@Query` / repository method with no data-access test.
- A new `@ExceptionHandler` / `@ControllerAdvice` without a test that exercises the mapped error path.
- A new `@Configuration` for Security / Web / anything non-trivial with no test that wires it up (this one is legitimately hard; don't require a full `@SpringBootTest` — a config-wiring slice is enough).

**Shape of the finding:** group it as one finding per changed class, not one per method. "ServiceX has three new methods with no tests" is better signal than three separate findings.

**Severity:** Major. Critical only when the change is in sensitive territory (auth, payments, data migration) and ships without any test.

## Tests that don't actually test

A green test that doesn't assert meaningful behaviour is worse than no test — it's false confidence plus maintenance burden. These are often harder to see than missing tests.

**Flag when you see:**

**Assert-on-mock.** The test stubs a mock to return X, then asserts the method returns X. It verifies the mock works; it doesn't verify the class under test.
```java
// anti-pattern
when(repo.findById(1L)).thenReturn(Optional.of(user));
assertThat(service.findUser(1L)).isEqualTo(user); // tautology if service just returns what repo gave
```
If the method under test only forwards, either test it with a real collaborator or delete the test — the forwarding is visible in the diff.

**Null-or-nothing assertions.** `assertNotNull(result)` with no further assertions, or `assertThat(result).isNotNull()`, stops at existence. If the method returns a computed value, assert on the value. If it returns a shape, assert on the shape.

**Assertion-free tests.** Tests that call the method and never assert. Usually accompanied by "no exception means it worked" reasoning. Real integration paths might pass this way by accident because the exception they care about is silently swallowed.

**Over-mocked "unit tests".** A test that mocks 8 of 8 collaborators and then asserts the order of mock calls. It locks in the current implementation, breaks on every refactor, and doesn't verify behaviour. Legitimate on rare interaction-heavy classes (event publishers); suspicious everywhere else.

**Ignored tests.** `@Ignore` / `@Disabled` with no explanation or TODO. Flag each as Minor — the team needs to decide whether to fix or delete.

**Copy-paste tests.** Five tests that differ only in a literal value, with no parameterization. Not buggy per se, but painful to maintain and hide the real coverage dimension. Suggestion-level — point at `@ParameterizedTest`.

**Broken invariants caught but not asserted.** `try { method(); fail(); } catch (Exception ignored) {}` without asserting the exception type or message — any exception passes, including `NullPointerException` from a bug in setup.

**Severity:** Major for assert-on-mock and assertion-free tests (they mask bugs). Minor for over-mocking and assertion shape issues.

## Test-setup leakage

One test's state contaminating another's.

**Flag when you see:**
- `static` mutable fields on a test class populated by `@BeforeAll`.
- `@TestMethodOrder` used to enforce ordering (unless it's intentional like nested state-machine scenarios, in which case it should be named that way).
- A repository test with no `@Transactional` / `@Rollback` and no explicit cleanup.
- A mock reset missing where a shared mock is used across tests (`@Mock` is fresh per test in JUnit 5; `@MockBean` is cached, so `reset()` between tests is sometimes necessary).

**Severity:** Minor, Major when it's clearly already causing flakes.

## Integration test patterns

If the change is exercised by an integration test:
- Is it using Testcontainers or H2? H2 doesn't support Postgres-specific features (JSONB, arrays, `CITEXT`) — if the production DB is Postgres and H2 is used for tests, changes involving those features won't be caught.
- `@SpringBootTest(webEnvironment = RANDOM_PORT)` vs `MOCK` — if the test relies on real HTTP behaviour (filter ordering, CORS), MOCK won't catch it.
- Real time clocks in tests that involve scheduling / timeouts — flake waiting to happen.

**Severity:** Minor / Suggestion, unless the test is meant to verify a Postgres-specific behaviour (like JSONB querying) and is on H2, in which case Major.

## What NOT to flag

- The testing framework (JUnit 4 vs 5), the assertion library (AssertJ vs Hamcrest), the mocking style (strict vs lenient) — those are team conventions and outside this skill's remit. `spring-boot-testing` covers them.
- Exact `@DisplayName` wording, unless it's a misleading name that claims the test does something it doesn't.
- Coverage percentages — the review doesn't have access to coverage data, and "add tests to hit 80%" is a bad proxy for "test the behaviour that matters".
