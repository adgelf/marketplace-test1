# Service tests (plain JUnit + Mockito, no Spring context)

## When to use this test type

A service test exercises the business logic of a single class with its collaborators mocked. No Spring context, no classpath scanning — just `new MyService(mock, mock, mock)`. This is where the bulk of a codebase's test count lives and where they run fastest (milliseconds).

If your service only meaningfully works because Spring wires a transaction manager around it, and the thing you want to verify is "the transaction rolls back on error", that's not a unit test — write an integration test instead.

## The shape — JUnit 5 / Mockito

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class UserServiceTest {

    @Mock private UserRepository userRepository;
    @Mock private EmailService emailService;
    @Mock private Clock clock;

    private UserService userService;

    @BeforeEach
    void setUp() {
        userService = new UserService(userRepository, emailService, clock);
    }

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

    @Test
    @DisplayName("should throw UserNotFoundException when id does not exist")
    void shouldThrowUserNotFoundExceptionWhenIdDoesNotExist() {
        // given
        when(userRepository.findById(99L)).thenReturn(Optional.empty());

        // when / then
        assertThatThrownBy(() -> userService.findById(99L))
            .isInstanceOf(UserNotFoundException.class)
            .hasMessageContaining("99");
    }

    @Test
    @DisplayName("should send welcome email when user is created")
    void shouldSendWelcomeEmailWhenUserIsCreated() {
        // given
        CreateUserRequest request = CreateUserRequestTestDataFactory.createDefault();
        User saved = UserTestDataFactory.createDefault();
        when(userRepository.save(any(User.class))).thenReturn(saved);

        // when
        userService.create(request);

        // then
        verify(emailService).sendWelcome(saved.getEmail());
    }

    @Test
    @DisplayName("should not send welcome email when save fails")
    void shouldNotSendWelcomeEmailWhenSaveFails() {
        // given
        CreateUserRequest request = CreateUserRequestTestDataFactory.createDefault();
        when(userRepository.save(any(User.class))).thenThrow(new DataIntegrityViolationException("duplicate"));

        // when / then
        assertThatThrownBy(() -> userService.create(request))
            .isInstanceOf(DataIntegrityViolationException.class);
        verify(emailService, never()).sendWelcome(any());
    }
}
```

## JUnit 4 variant

```java
@RunWith(MockitoJUnitRunner.class)
public class UserServiceTest {

    @Mock private UserRepository userRepository;
    @Mock private EmailService emailService;
    @InjectMocks private UserService userService;

    @Test
    public void shouldReturnUserWhenIdExists() {
        // given
        User expected = UserTestDataFactory.createDefault();
        when(userRepository.findById(1L)).thenReturn(Optional.of(expected));

        // when
        User actual = userService.findById(1L);

        // then
        assertThat(actual).isEqualTo(expected);
    }
}
```

`@InjectMocks` is acceptable here because there's no Spring context and the service isn't annotated with `@Autowired`. The intent — "inject the mocks into this constructor" — is the same.

## ArgumentCaptor for "did we call it with the right shape?"

Use `ArgumentCaptor` when the thing passed to a collaborator is constructed inside the method under test (you don't have a handle on the object to pass directly to `verify`).

```java
@Test
@DisplayName("should persist user with normalized email when created")
void shouldPersistUserWithNormalizedEmailWhenCreated() {
    // given
    CreateUserRequest request = CreateUserRequestTestDataFactory.createWithEmail("  Jane@Example.com  ");
    ArgumentCaptor<User> captor = ArgumentCaptor.forClass(User.class);

    // when
    userService.create(request);

    // then
    verify(userRepository).save(captor.capture());
    assertThat(captor.getValue().getEmail()).isEqualTo("jane@example.com");
}
```

For JUnit 5 + Mockito 3.4+, `@Captor` on a field is equivalent and sometimes cleaner.

## Stubbing patterns worth knowing

- **`any()` vs specific values.** Prefer specific values in `when(...)` so the stub only matches the input you expect. Reserve `any()` for arguments that are genuinely not interesting (e.g. a timestamp you constructed inline).
- **`thenAnswer` for returning a computed value based on the input.** Useful when `save()` should "echo back" whatever was passed in:
  ```java
  when(userRepository.save(any(User.class))).thenAnswer(inv -> inv.getArgument(0));
  ```
- **`doThrow(...)` / `doNothing()` for void methods.** `when(mock.voidMethod()).thenThrow(...)` doesn't compile — use `doThrow(...).when(mock).voidMethod()`.
- **Strict vs lenient stubbing.** Mockito 3+ is strict by default and will fail the test on unused stubs. Don't blanket with `lenient()` — if a stub is unused, the test is probably stubbing the wrong thing or asserting the wrong behaviour.

## What to cover

For a typical service method, a good coverage set is:
- Happy path.
- Each distinct branch (`if`, `switch`, ternary, early return).
- Each exception this method can throw, including exceptions propagated from collaborators.
- Side effects: every `verify(collaborator).method(...)` is a behaviour that should be asserted somewhere.
- Interactions that should NOT happen: `verify(collaborator, never()).method(any())` — the "we didn't send an email because validation failed" case.

## Common gotchas

- **Don't mock value classes** (`String`, `Instant`, your own records). Mock behaviour, not data. Build data with factories.
- **`@Mock` fields don't get initialised without `@ExtendWith(MockitoExtension.class)`** (JUnit 5) or `@RunWith(MockitoJUnitRunner.class)` / `MockitoAnnotations.openMocks(this)` (JUnit 4). Forgetting gives confusing NPEs in `when(...)`.
- **`when(mock.method())` returns null by default** for object types. If the production code chains on that return value (`service.findUser(id).getEmail()`), it'll NPE before your assertion runs. Either stub the call or use `@Mock(answer = Answers.RETURNS_DEEP_STUBS)` only as a last resort.
- **Final classes need Mockito inline** (the default since 5.0) or explicit opt-in via `mockito-inline`. If you see "cannot mock/spy because final class", check the Mockito version.
