# Integration tests (@SpringBootTest)

## When to use this test type

Use `@SpringBootTest` when the behaviour under test can only be verified with the full application context — request going through the real filter chain, real service, real transaction, real repository, against a real (or realistic) database. Typical cases: "creating a user persists the row and publishes an event", "an auth-protected endpoint rejects requests without a valid JWT", "the retry policy actually retries".

These tests are slow — start with slice tests (`@WebMvcTest`, `@DataJpaTest`) where possible and reach for `@SpringBootTest` only when you need the full wiring.

## Naming: `*IT.java` vs `*Test.java`

If the project uses Maven with both `surefire` (unit) and `failsafe` (integration) plugins, name the class `*IT.java` and it'll run in the `verify` phase — not on every `mvn test`. Check the `pom.xml`. Gradle projects often keep everything in `src/test/java` and rely on test tags / `@Tag` to split.

## The shape — JUnit 5, Spring Boot 3, Testcontainers

```java
import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@Testcontainers
@ActiveProfiles("test")
class UserFlowIT {

    @Container
    static final PostgreSQLContainer<?> postgres = new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    private final TestRestTemplate restTemplate;
    private final UserRepository userRepository;

    UserFlowIT(@Autowired TestRestTemplate restTemplate,
               @Autowired UserRepository userRepository) {
        this.restTemplate = restTemplate;
        this.userRepository = userRepository;
    }

    @AfterEach
    void tearDown() {
        userRepository.deleteAll();
    }

    @Test
    @DisplayName("should persist user and return 201 when request is valid")
    void shouldPersistUserAndReturn201WhenRequestIsValid() {
        // given
        CreateUserRequest request = CreateUserRequestTestDataFactory.createDefault();

        // when
        ResponseEntity<UserResponse> response = restTemplate.postForEntity(
            "/api/users", request, UserResponse.class);

        // then
        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.CREATED);
        assertThat(userRepository.findByEmail(request.getEmail())).isPresent();
    }
}
```

## Shared container pattern

Starting a Postgres container per test class is slow. Two common patterns:

**1. A singleton container held in an abstract base class** — the container is `static`, started manually, and reused across every subclass in the JVM:

```java
public abstract class AbstractIntegrationTest {
    static final PostgreSQLContainer<?> POSTGRES = new PostgreSQLContainer<>("postgres:16-alpine");
    static { POSTGRES.start(); }

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", POSTGRES::getJdbcUrl);
        registry.add("spring.datasource.username", POSTGRES::getUsername);
        registry.add("spring.datasource.password", POSTGRES::getPassword);
    }
}
```

**2. Testcontainers reuse** (`withReuse(true)` + `testcontainers.reuse.enable=true` in `~/.testcontainers.properties`). Survives JVM restarts on the dev machine; CI usually turns it off.

If the codebase already has a base class, use it — don't set up containers a second way.

## Kafka: Testcontainers vs EmbeddedKafka

If the project has `org.testcontainers:kafka`, use it:

```java
@Container
static final KafkaContainer kafka = new KafkaContainer(DockerImageName.parse("confluentinc/cp-kafka:7.5.0"));

@DynamicPropertySource
static void properties(DynamicPropertyRegistry registry) {
    registry.add("spring.kafka.bootstrap-servers", kafka::getBootstrapServers);
}
```

If not, `@EmbeddedKafka` ships with `spring-kafka-test`:

```java
@SpringBootTest
@EmbeddedKafka(partitions = 1, topics = {"user-events"})
class UserEventIT { ... }
```

## WebTestClient vs TestRestTemplate

- **TestRestTemplate** — simple, blocking. Good default for REST APIs.
- **WebTestClient** — fluent, works for both MVC (`@AutoConfigureWebTestClient`) and WebFlux. Slightly nicer assertion chains for JSON.

Pick based on what the neighbour tests use; both are fine.

## What to cover

Integration tests are expensive — be deliberate about what you cover.

- One or two "critical path" tests per feature: create → read, authenticate → access, publish → consume.
- Cross-cutting concerns: transaction rollback on error, security on protected endpoints, message ordering.
- Anything that touches multiple Spring-wired components where the wiring itself could be wrong.

What NOT to cover with integration tests:
- Every validation rule (those belong in `@WebMvcTest`).
- Every service branch (those belong in Mockito unit tests).
- Every query variant (those belong in `@DataJpaTest`).

## Common gotchas

- **Context caching.** Spring caches the application context per distinct test configuration. Using different `@ActiveProfiles`, `@TestPropertySource`, `@MockBean`, etc. creates separate contexts — each one slow to start. Keep the configuration consistent across integration tests and lean on a base class.
- **`@MockBean` inside `@SpringBootTest` evicts the context.** If you `@MockBean` a different collaborator in each test class, you force context reload between them. Use sparingly.
- **Cleanup between tests.** `@SpringBootTest` does NOT roll back transactions by default (unlike `@DataJpaTest`). Either mark tests `@Transactional` (only works if the production code opens its own outer transaction the way `@DataJpaTest` arranges), or explicitly truncate / `deleteAll()` in `@AfterEach`.
- **Port randomisation.** With `RANDOM_PORT`, inject `@LocalServerPort int port` only if you're building URLs manually. `TestRestTemplate` and `WebTestClient` know the port automatically.
- **Flyway migrations run per context.** They're idempotent, but if they reference external resources (e.g. create a role that already exists), they can break tests. Use a test-only migration location if needed.
