# Stack detection

Before writing any test code, identify six things about the project. Each has a cheap check and affects the annotations, imports, or test style you'll produce.

## The six things to know

| What | Why it matters | Fastest way to check |
|---|---|---|
| Build tool | Tells you where to look for dependencies and how the user will run tests | Is there `pom.xml` (Maven) or `build.gradle` / `build.gradle.kts` (Gradle)? |
| Spring Boot version | Controls `javax.*` vs `jakarta.*` imports and the default JUnit version | In `pom.xml` look for `<parent>spring-boot-starter-parent</parent>` or the `spring-boot.version` property; in Gradle check `plugins { id 'org.springframework.boot' version 'X' }` |
| Java version | Determines which language features (records, pattern matching) are fair game in test helpers | `<java.version>` / `<maven.compiler.release>` in Maven, `sourceCompatibility` / `java { toolchain { ... } }` in Gradle |
| JUnit version | Completely different imports, annotations, runner/extension mechanics | See "JUnit version signals" below |
| Slice-test and extra libraries | Whether you can use `@WebMvcTest`, Testcontainers, Awaitility, `@SpyBean`, `spring-security-test` etc. | Grep dependencies for `testcontainers`, `awaitility`, `spring-security-test`, `spring-boot-starter-test` |
| Database flavour | Repository tests and integration tests depend on this | Check for `org.postgresql:postgresql`, `mysql-connector-j`, `spring-boot-starter-data-mongodb` |

## JUnit version signals

Distinguishing JUnit 4 from JUnit 5 is the single most common source of broken tests. Check multiple signals — they should agree. If they disagree, the neighbour test wins (it's what CI actually runs).

**JUnit 5 (Jupiter) signals:**
- `spring-boot-starter-test` on Spring Boot 2.2+ brings Jupiter transitively
- Explicit `junit-jupiter`, `junit-jupiter-api`, `junit-jupiter-engine` dependencies
- Existing tests import `org.junit.jupiter.api.Test` and use `@ExtendWith`
- Gradle: `test { useJUnitPlatform() }`

**JUnit 4 signals:**
- `junit:junit:4.x` as an explicit dependency
- Explicit `junit-vintage-engine` (means JUnit 4 tests run on the 5 platform — you can write either, but match the neighbour)
- Spring Boot 1.x, or 2.x with `spring-boot-starter-test` excluding the Jupiter artefacts
- Existing tests import `org.junit.Test` and use `@RunWith`

**Mixed / vintage:** if you see `junit-vintage-engine` plus Jupiter, both styles run. Follow the nearest neighbour test in the same module, and if the user said "add tests for X" in a module full of JUnit 4 tests, write JUnit 4 — don't start a solo migration.

## Spring Boot 2 vs 3 — the imports that change

Spring Boot 3 moved off Java EE to Jakarta EE. Getting these wrong produces confusing "cannot find symbol" errors.

| Concern | Spring Boot 2.x | Spring Boot 3.x |
|---|---|---|
| Servlet API | `javax.servlet.*` | `jakarta.servlet.*` |
| Validation | `javax.validation.*` (`@Valid`, `@NotNull`) | `jakarta.validation.*` |
| JPA | `javax.persistence.*` | `jakarta.persistence.*` |
| Annotation `@PostConstruct`, `@PreDestroy` | `javax.annotation.*` | `jakarta.annotation.*` |

Spring Security testing also changed: on Spring Boot 3 / Spring Security 6, `SecurityMockMvcRequestPostProcessors.jwt()` is the modern way to mock JWT auth in MockMvc. Older `@WithMockUser` still works everywhere.

## Reading a nearby existing test

After build inspection, open one or two existing tests in the same module — ideally next to the class under test, or at least in the same package. Specifically note:

- **Imports at the top.** They tell you JUnit version, Jakarta vs javax, and which AssertJ / Mockito entry points the team favours (`org.assertj.core.api.Assertions.assertThat` vs static import everywhere).
- **Class-level annotations.** `@SpringBootTest`, `@WebMvcTest`, `@DataJpaTest`, `@ExtendWith(MockitoExtension.class)`, `@ActiveProfiles("test")`, `@Testcontainers`, custom `@IntegrationTest` meta-annotations.
- **Is there a base test class?** Teams often have `AbstractIntegrationTest` or `IntegrationTestBase` that boots shared Testcontainers. If so, extend it — don't reinvent container lifecycle.
- **How test data is built.** Is there already a `*TestDataFactory` in the module? A shared `src/test/java/.../testutil` package? Extend what exists before creating new factories.
- **Test method style.** `public void` vs package-private, `@DisplayName` presence, `given/when/then` comment style.

## Worked example

You open `pom.xml` and see:

```xml
<parent>
  <artifactId>spring-boot-starter-parent</artifactId>
  <version>3.2.1</version>
</parent>
<properties>
  <java.version>17</java.version>
</properties>
<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
  </dependency>
  <dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>postgresql</artifactId>
    <scope>test</scope>
  </dependency>
</dependencies>
```

And a neighbour test imports `org.junit.jupiter.api.Test` and `jakarta.persistence.EntityManager`.

Profile: Maven, Spring Boot 3.2, Java 17, JUnit 5 (Jupiter), Testcontainers available for Postgres, Jakarta imports. That profile fully determines the annotations and imports you'll use in the rest of the file.
