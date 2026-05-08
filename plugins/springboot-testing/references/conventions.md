# Team conventions — the full reference

Every convention listed here is enforced in code review. They exist for a reason; the "why" is included so you can judge edge cases.

## 1. AssertJ, not JUnit assertions

**Why:** AssertJ's fluent chains (`assertThat(user).hasFieldOrPropertyWithValue("email", "a@b.com")`) produce specific failure messages — "expected email to be 'a@b.com' but was 'c@d.com'" — instead of the classic `expected: <true> but was: <false>` from `assertTrue`. They also compose: `assertThat(list).hasSize(3).extracting("name").containsExactly(...)`.

```java
// Bad
assertEquals("foo", result.getName());
assertTrue(result.isActive());
assertNotNull(result.getCreatedAt());

// Good
assertThat(result)
    .extracting(User::getName, User::isActive)
    .containsExactly("foo", true);
assertThat(result.getCreatedAt()).isNotNull();
```

Static import: `import static org.assertj.core.api.Assertions.assertThat;`

## 2. given / when / then comments in every test body

**Why:** They force you to articulate the setup, the action, and the verification as three distinct steps. In diffs, they make it instantly obvious whether a change is to fixture data, to the action, or to expectations. Even in a trivial test they're worth the three lines.

```java
@Test
@DisplayName("should return user when id exists")
void shouldReturnUserWhenIdExists() {
    // given
    User expected = UserTestDataFactory.createDefault();
    when(userRepository.findById(1L)).thenReturn(Optional.of(expected));

    // when
    User actual = userService.findById(1L);

    // then
    assertThat(actual).isEqualTo(expected);
}
```

If a test has no meaningful setup (e.g. pure function test), still write `// given` on a line by itself followed by the comment for the action.

## 3. `@DisplayName` on every test — "should X when Y"

**Why:** This is the test's name in IDE and CI output. The method name is noise; the display name is documentation. The `should ... when ...` form forces you to say what the test verifies and under what conditions.

```java
@Test
@DisplayName("should return 404 when user does not exist")
void shouldReturn404WhenUserDoesNotExist() { ... }

@Test
@DisplayName("should reject request when email format is invalid")
void shouldRejectRequestWhenEmailFormatIsInvalid() { ... }
```

If a test is purely about verifying shape with no conditional ("should return all active users"), that's fine — `when` isn't mandatory, but `should` is.

**JUnit 4 note:** JUnit 4 has no `@DisplayName`. In a JUnit 4 module, keep the same discipline in the method name (`shouldReturn404WhenUserDoesNotExist`) and add a one-line Javadoc with the human-readable version above the method.

## 4. Test data via static factories

**Why:** A realistic entity has ten to twenty fields. If each test builds its own, the notion of a "valid entity" drifts, and when a new required field is added you update it in dozens of places. A factory centralises that.

```java
// UserTestDataFactory.java  (in src/test/java, same package as the test or a testutil package)
public final class UserTestDataFactory {
    private UserTestDataFactory() {}

    public static User createDefault() {
        return User.builder()
            .id(1L)
            .email("jane@example.com")
            .name("Jane Doe")
            .status(UserStatus.ACTIVE)
            .createdAt(Instant.parse("2024-01-01T00:00:00Z"))
            .build();
    }

    public static User createWithEmail(String email) {
        return createDefault().toBuilder().email(email).build();
    }

    public static User createInactive() {
        return createDefault().toBuilder().status(UserStatus.INACTIVE).build();
    }
}
```

Guidelines:
- One factory per aggregate/entity. Don't pile `UserTestDataFactory` and `OrderTestDataFactory` into a single `TestData` class.
- `createDefault()` returns a valid, boring, committed-to-DB-safe instance. Variants (`createInactive`, `createWithEmail(String)`) override only what's relevant.
- Prefer builder-based overrides (`.toBuilder()`) so variants stay short.
- If there's no Lombok `@Builder`, a small `create(Consumer<User> mutator)` style is an acceptable fallback.

If the class under test takes DTOs (e.g. `CreateUserRequest`), create a factory for the DTO too (`CreateUserRequestTestDataFactory`). The same entity factory shouldn't produce both entities and DTOs.

## 5. One logical assertion per test

**Why:** When a test fails, "which behaviour broke?" should be obvious from the test's name alone. If one test checks three unrelated behaviours, the first failing assertion hides the next two, and the test name can't narrate all three.

"One logical assertion" ≠ "one physical `assertThat`". This is fine:

```java
// then — all three lines verify one behaviour: the response body
assertThat(response.getStatus()).isEqualTo("ACCEPTED");
assertThat(response.getId()).isNotNull();
assertThat(response.getCreatedAt()).isAfter(before);
```

This is not, and should be split:

```java
// Bad — two separate behaviours (persistence + email send)
assertThat(userRepository.findById(id)).isPresent();  // persistence
verify(emailService).sendWelcome(email);               // side effect
```

Split into `shouldPersistUserWhenCreated` and `shouldSendWelcomeEmailWhenCreated`. Each has one reason to fail.

## 6. Test method names in camelCase

**Why:** Method names are identifiers, not sentences. The `@DisplayName` carries the narrative. Mixing `snake_case` and `camelCase` just reads as inconsistent.

```java
// Bad
void should_return_404_when_user_does_not_exist() { ... }
void shouldReturn_404_WhenUserDoesNotExist() { ... }

// Good
void shouldReturn404WhenUserDoesNotExist() { ... }
```

## 7. Constructor injection, never field `@Autowired`

**Why:** Constructor injection surfaces missing dependencies at object construction (before any test runs), matches how production code is written, and is trivial with Spring Boot's test runner. Field injection hides dependencies and makes it awkward to instantiate the test class outside Spring.

```java
// Bad
@SpringBootTest
class UserServiceIT {
    @Autowired UserService userService;
    @Autowired UserRepository userRepository;
}

// Good
@SpringBootTest
class UserServiceIT {
    private final UserService userService;
    private final UserRepository userRepository;

    UserServiceIT(@Autowired UserService userService,
                  @Autowired UserRepository userRepository) {
        this.userService = userService;
        this.userRepository = userRepository;
    }
}
```

For pure Mockito tests (no Spring context), use `@InjectMocks` on a non-`@Autowired` field, or instantiate in `@BeforeEach`:

```java
@ExtendWith(MockitoExtension.class)
class UserServiceTest {
    @Mock UserRepository userRepository;
    @Mock EmailService emailService;
    UserService userService;

    @BeforeEach
    void setUp() {
        userService = new UserService(userRepository, emailService);
    }
}
```

## 8. No `System.out.println`

**Why:** Tests that print are tests that are guessing. If you need observability in a test, you're either debugging (use the IDE) or checking a side effect (assert on it). If there is a genuinely good reason to log, use SLF4J:

```java
private static final Logger log = LoggerFactory.getLogger(MyServiceIT.class);
```

But if this is the first time the codebase has seen a logger in a test, ask yourself whether the test is assertion-shaped.

## 9. Tests are independent

**Why:** Tests that share mutable state or depend on order are tests that pass on your laptop and fail in CI (or pass in CI and fail after somebody reorders them). Every test sets up its own fixture and tears down or rolls back its own changes.

- No `static` non-final fields that tests write to.
- No `@TestMethodOrder`.
- For DB-backed tests, either rely on `@DataJpaTest` / `@Transactional` rollback, or truncate in `@BeforeEach`. Don't count on test order for "previous test left a row".
- Clear any ThreadLocal state (e.g. `SecurityContextHolder.clearContext()` after security tests) in `@AfterEach`.

## Sanity checklist before returning a test file

Before handing the file back, scan for:

- [ ] AssertJ everywhere — no `assertEquals`, `assertTrue`, `assertNotNull`
- [ ] Every `@Test` has a `@DisplayName` in `"should ... when ..."` form (or a Javadoc in JUnit 4 modules)
- [ ] `given / when / then` comments in every test body
- [ ] All test method names camelCase
- [ ] No `@Autowired` on a field
- [ ] No `System.out` or `printStackTrace`
- [ ] Test data comes from a factory; no inline `new Foo(...)` for entities
- [ ] One logical assertion per test
