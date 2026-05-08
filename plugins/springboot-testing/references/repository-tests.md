# Repository tests (@DataJpaTest / @DataMongoTest)

## When to use this test type

Test a repository when it has custom behaviour that could break — a derived query (`findByEmailIgnoreCase`), a `@Query` (JPQL or native), a `@Modifying` update, an `EntityGraph`, or a query method that depends on JPA relationships being mapped right. Don't write "test `save()` / `findById()`" tests — Spring Data gives those, and testing them tests the framework.

## Choosing the backing database

This is where version agnosticism matters most. Pick based on what the project has on the classpath:

| Project has… | Use | Why |
|---|---|---|
| `org.testcontainers:postgresql` (or mysql, mongodb) | Testcontainers with the real DB image | Fidelity with production; catches PG-specific SQL, Flyway issues, JSONB, arrays |
| No Testcontainers, but `com.h2database:h2` in test scope | H2 in PostgreSQL-compat mode | Fast, zero-setup. Watch for PG-only features that silently pass on H2 |
| `spring-boot-starter-data-mongodb` + no Testcontainers | `de.flapdoodle.embed.mongo` (embedded Mongo) | The classic embedded route |
| Nothing DB-specific, just JPA | H2 is the default, Spring auto-configures it | — |

**Do not add Testcontainers as a dependency without asking.** It's a non-trivial CI impact (Docker-in-CI requirement).

## The shape — @DataJpaTest with Testcontainers (JUnit 5, Spring Boot 3)

```java
import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
@Testcontainers
class UserRepositoryIT {

    @Container
    static final PostgreSQLContainer<?> postgres = new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    private final UserRepository userRepository;
    private final TestEntityManager entityManager;

    UserRepositoryIT(@Autowired UserRepository userRepository,
                     @Autowired TestEntityManager entityManager) {
        this.userRepository = userRepository;
        this.entityManager = entityManager;
    }

    @Test
    @DisplayName("should find user when email matches case-insensitively")
    void shouldFindUserWhenEmailMatchesCaseInsensitively() {
        // given
        User stored = UserTestDataFactory.createWithEmail("Jane@Example.com");
        entityManager.persistAndFlush(stored);

        // when
        Optional<User> found = userRepository.findByEmailIgnoreCase("jane@example.com");

        // then
        assertThat(found).isPresent().get().extracting(User::getEmail).isEqualTo("Jane@Example.com");
    }

    @Test
    @DisplayName("should return empty when email is not present")
    void shouldReturnEmptyWhenEmailIsNotPresent() {
        // given: no users persisted

        // when
        Optional<User> found = userRepository.findByEmailIgnoreCase("nobody@example.com");

        // then
        assertThat(found).isEmpty();
    }
}
```

The naming choice (`*IT` vs `*Test`) often matters: in Maven, `surefire` runs `*Test` and `failsafe` runs `*IT`. Check the `pom.xml` — if a `failsafe` plugin is configured, put Testcontainers-backed tests in `*IT.java` so they run in the `verify` phase, not on every `mvn test`.

## @DataJpaTest with H2 (the fast default)

If there's no Testcontainers, Spring auto-configures H2 if it's on the classpath. The test simplifies:

```java
@DataJpaTest
class UserRepositoryTest {
    // ... same structure, no @Testcontainers or @DynamicPropertySource
}
```

One caveat worth calling out: H2's PostgreSQL mode (`jdbc:h2:...;MODE=PostgreSQL`) is *close* to Postgres, not identical. `jsonb`, array columns, `ON CONFLICT`, regex operators, and most extensions don't work. If the repository uses any of these, a test that passes on H2 can fail in production. In that case either use Testcontainers, or be honest in your test coverage: say "this query is not covered by unit tests; it's exercised only in the end-to-end tests against real Postgres".

## @DataMongoTest

```java
@DataMongoTest
@Testcontainers
class UserRepositoryIT {
    @Container
    static final MongoDBContainer mongo = new MongoDBContainer("mongo:7");

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("spring.data.mongodb.uri", mongo::getReplicaSetUrl);
    }
    // ...
}
```

With no Testcontainers, embedded Mongo (`de.flapdoodle.embed.mongo.spring3x` for Spring Boot 3) kicks in automatically when `@DataMongoTest` runs.

## Flyway / Liquibase interaction

`@DataJpaTest` is opinionated about schema. If the project uses Flyway to manage schema and you're using Testcontainers:

- Add `@AutoConfigureTestDatabase(replace = Replace.NONE)` so Spring doesn't swap in H2.
- Flyway will run migrations against the Testcontainers DB on context startup — this is usually what you want.

If you're on H2, check whether Flyway migrations even run against H2 (they might reference PG syntax). If they don't, either exclude Flyway in tests (`spring.flyway.enabled=false`) and let JPA `ddl-auto: create-drop` build the schema, or point Flyway at a locations override (`spring.flyway.locations=classpath:db/migration-h2`).

## What to cover

- Every derived query method (`findByX`, `existsByX`, `countByX`) the repository declares.
- Every `@Query` (both JPQL and native).
- Every `@Modifying` update — assert the row count returned and a follow-up query confirming the state change.
- Unique / not-null / foreign-key constraint violations if the repository is responsible for translating them (usually it isn't — that's `DataIntegrityViolationException` territory, and lives in service tests).
- Pagination and sorting if the method returns `Page<T>` or takes a `Pageable`.

## Common gotchas

- **`@DataJpaTest` wraps every test in a transaction and rolls it back.** This means `save()` doesn't actually flush SQL. If you're testing something that depends on the SQL hitting the DB (a `@PrePersist`, a constraint check), call `entityManager.flush()` explicitly, or `entityManager.persistAndFlush(entity)`.
- **`@DataJpaTest` doesn't load `@Service` beans.** If you want those, you're in `@SpringBootTest` territory.
- **Lazy loading inside the test works because of the surrounding transaction.** If the real caller is in a non-transactional context, lazy collections would fail with `LazyInitializationException` in production. Tests can mask this — be careful when a repository test inspects a lazy relationship.
- **Reusing containers across tests.** If you have many repository tests, a new container per test class is slow. Use a singleton pattern: declare the container as `static` without `@Container` so it starts once per JVM and reuse across classes. Teams sometimes have an `AbstractIntegrationTest` base class that owns this.
