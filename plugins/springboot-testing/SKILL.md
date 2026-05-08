---
name: bizapps-spring-boot-testing
description: Writing and modifying unit, slice, and integration tests in Spring Boot / Java projects. Use this skill whenever the user asks to "write tests", "add unit tests", "cover with tests", or "test this controller/service/repository", and whenever a `*Test.java`, `*Tests.java`, or `*IT.java` file is being created or edited. Also use it for any tests involving MockMvc, @WebMvcTest, @DataJpaTest, @SpringBootTest, Mockito, Testcontainers, Spring Security test support, or Awaitility — even if the user doesn't explicitly say the word "test". The skill is version-agnostic (handles Spring Boot 2.x and 3.x, Java 11/17/21, JUnit 4 and 5, Maven and Gradle) and detects the project's actual stack before writing any code.
---

# Spring Boot Testing

## What this skill is for

Generating test code for Spring Boot projects that matches a specific team's conventions and adapts to the project's actual stack. Projects in this codebase mix Spring Boot 2.x and 3.x, Java 11/17/21, Maven and Gradle, and JUnit 4 and 5 — so the skill never assumes a stack. It looks first, then writes.

## The golden rule: detect before you write

Do not guess at annotations, imports, or helpers. Two tests that look nearly identical under JUnit 4 and JUnit 5 import different packages (`org.junit.Test` vs `org.junit.jupiter.api.Test`), use different runner/extension mechanics (`@RunWith(SpringRunner.class)` vs `@ExtendWith(SpringExtension.class)`), and fail silently if mixed. Spring Boot 2 uses `javax.*`; Spring Boot 3 uses `jakarta.*`. Picking the wrong one produces code that compiles on your machine and explodes on someone else's. So before writing a single line of test code, build a short mental stack profile from what's actually in the repo.

**Step 1 — read build configuration.** Open `pom.xml` or `build.gradle(.kts)` and note: Spring Boot version, Java version, JUnit version (JUnit 5 shows up as `junit-jupiter` / `spring-boot-starter-test` on Boot 2.2+; JUnit 4 shows up as `junit:junit` or as an explicit `junit-vintage-engine`), and which of the following are on the classpath: Testcontainers, Spring Security test, Awaitility, MapStruct, Flyway/Liquibase, H2, Embedded Kafka, Spring Data MongoDB.

**Step 2 — read a nearby existing test.** The single most reliable signal for "what does this team actually do" is an existing test next to the class you're testing. Glob for `*Test.java` / `*IT.java` in the same module, pick one or two, and note its imports, base class (if any), and setup style.

**Step 3 — read the class under test.** Note constructors, dependencies, method signatures, checked exceptions, return types, and whether it uses `javax.*` or `jakarta.*`.

If any signal conflicts (e.g. `spring-boot-starter-test` says JUnit 5 but the nearest neighbour test uses `@RunWith`), prefer what the neighbouring test does and mention the mismatch once in your reply — the team may have a migration in progress and consistency within a module beats purity.

For the full detection checklist with concrete snippets, read `references/stack-detection.md`.

## Team conventions (always apply, regardless of stack)

These are hard team norms. They are the whole point of this skill existing — they are enforced in code review and deviating causes rework. Apply them everywhere.

1. **AssertJ, not JUnit assertions.** `assertThat(x).isEqualTo(y)` — never `assertEquals`, `assertTrue`, `assertNotNull`. AssertJ chains read like English and produce better failure messages.
2. **`given / when / then` comments inside every test body.** Even one-line tests get the three comments. They make the intent of each line unambiguous and make skimming diffs fast.
3. **`@DisplayName` on every test**, in the form `"should <expected> when <condition>"`. Example: `"should return 404 when user does not exist"`. This is what shows up in IDE and CI output and it is the first thing a reader sees.
4. **Test data from static factories.** Never hand-build entities inline. Use (or create) `FooTestDataFactory.createDefault()`, `createWithEmail(String)`, etc. Inline construction drifts; factories centralise the shape of a valid entity.
5. **One logical assertion per test.** Multiple physical `assertThat` lines are fine if they verify one behaviour (e.g. an object's shape). If you feel the urge to write "and also" about a test, split it.
6. **Test method names in camelCase only.** Never `snake_case`, never mixed. The `@DisplayName` carries the human-readable description; the method name is just an identifier.
7. **Constructor injection in tests, never field `@Autowired`.** Spring Boot supports this out of the box since 4.3. It keeps tests consistent with production code and surfaces missing dependencies at construction time.
8. **No `System.out.println` ever.** Use SLF4J logger if output is genuinely needed — but in a test, it almost never is.
9. **Tests are independent.** No static mutable state, no test ordering, no `@TestMethodOrder`. Each test sets up what it needs and tears down (or relies on `@Transactional` rollback) what it creates.

For each convention with a before/after example of a violation and a fix, read `references/conventions.md`.

## Choosing the right test type

Before writing, decide which of these you're producing. Picking the wrong type is the most common mistake — a `@SpringBootTest` where a `@WebMvcTest` would do is slow and brittle; a plain Mockito unit test for a repository won't exercise the mapping you actually want to verify.

| If you are testing… | Use | Read |
|---|---|---|
| A `@RestController` / `@Controller`: request mapping, serialization, validation, status codes | `@WebMvcTest` + `MockMvc` + `@MockBean` for service layer | `references/controller-tests.md` |
| A `@Service` / business logic class: branching, error handling, interaction with collaborators | Plain JUnit + Mockito (no Spring context) | `references/service-tests.md` |
| A `@Repository` / Spring Data JPA or Mongo interface: custom queries, derived queries, JPQL | `@DataJpaTest` / `@DataMongoTest` — with Testcontainers if available, otherwise H2 / embedded Mongo | `references/repository-tests.md` |
| An end-to-end flow across controller → service → repo → DB | `@SpringBootTest(webEnvironment = RANDOM_PORT)` + `TestRestTemplate` or `WebTestClient` | `references/integration-tests.md` |
| Anything that hits Spring Security (auth, roles, JWT, method security) | The test type above plus `spring-security-test` (`@WithMockUser`, `SecurityMockMvcRequestPostProcessors.jwt()`, etc.) | `references/security-tests.md` |
| `@Async`, `@Scheduled`, Kafka listeners, or any code where the result is produced on another thread | Awaitility for polling, `CountDownLatch` for "has it run yet", `@SpyBean` + `verify(..., timeout(...))` | `references/async-tests.md` |

A single task often needs more than one of these — e.g. "write tests for `UserController`" almost always means controller tests for the happy path, validation tests for bad input, and a couple of security tests for auth behaviour. Pick the right type per behaviour, not per class.

## Recommended workflow

1. **Inspect.** Read `pom.xml` / `build.gradle`, one or two nearby existing tests, the class under test, and — if present — any existing `*TestDataFactory` in the module. Build the mental stack profile described above.
2. **Decide test type(s).** From the table above, based on what layer the class lives in and what behaviours need covering.
3. **Read the relevant references file.** Open the matching file from `references/`. The examples there are version-agnostic — they show both the JUnit 4 and JUnit 5 shape where it matters.
4. **Check for an existing test data factory.** If `FooTestDataFactory` already exists, extend it. If not, create one alongside the test with a `createDefault()` and whatever named variants the tests need. A factory per aggregate/entity; don't pile unrelated factories into one file.
5. **Write the test.** One `@DisplayName` per test, given/when/then comments, AssertJ assertions, one logical assertion, constructor injection.
6. **Sanity check before returning.** Re-scan your output for the four most common violations (they slip in under pressure): (a) a stray `assertEquals` or `assertTrue`, (b) a test method in `snake_case`, (c) a missing `@DisplayName` or one not in the `should ... when ...` form, (d) `@Autowired` on a field. Fix them silently — don't ask the user.

## Things worth saying out loud to the user

- If the project uses JUnit 4 (or mixes 4 and 5), note it briefly — most readers today default to 5 and will want to know the tests you produced use `@RunWith(SpringRunner.class)` and `org.junit.Test`, not `@ExtendWith` and `org.junit.jupiter.api.Test`.
- If the project has Testcontainers available, use them for repository/integration tests even if a nearby test uses H2 — fidelity to the real DB catches Flyway/PG-specific issues that H2 silently hides. But if the project has no Testcontainers dependency, do not add one without asking; it's a non-trivial dependency and CI impact.
- If you had to create a new `*TestDataFactory`, call that out — it's a new file the user may want to refactor or move.
- If a test requires mocking something unusual (a `Clock`, a `Random`, a static method), mention it. These are the places where tests accidentally grow flaky, and a heads-up helps the reviewer.

Keep these mentions short — one sentence each, only when relevant. Don't narrate every decision.

## What this skill does NOT do

- It does not run tests. After writing, tell the user the command to run them (`mvn test`, `mvn verify`, `./gradlew test`), but don't invoke it unless they ask.
- It does not refactor production code to be "more testable" without explicit permission. If a class is hard to test because of, say, a `new Foo()` call inside a method, say so and propose the refactor — don't just do it.
- It does not add new dependencies (Testcontainers, Awaitility, `spring-security-test`) silently. If a needed dependency is missing, mention it and ask before adding.
