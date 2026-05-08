# Controller tests (@WebMvcTest + MockMvc)

## When to use this test type

Use `@WebMvcTest` when you want to verify the web layer in isolation — request mapping, path/query/body binding, validation (`@Valid`), JSON serialization of the response, status codes, and error handling — without booting the full application context. The service layer is mocked; the database is not involved.

If you need the real service layer (say, because the thing you're testing is "end-to-end flow produces the right record in the DB"), reach for `@SpringBootTest` instead — see `integration-tests.md`.

## The shape — Spring Boot 3 / JUnit 5

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.hamcrest.Matchers.is;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@WebMvcTest(UserController.class)
class UserControllerTest {

    private final MockMvc mockMvc;
    private final ObjectMapper objectMapper;

    @MockBean
    private UserService userService;

    UserControllerTest(@Autowired MockMvc mockMvc,
                       @Autowired ObjectMapper objectMapper) {
        this.mockMvc = mockMvc;
        this.objectMapper = objectMapper;
    }

    @Test
    @DisplayName("should return user when id exists")
    void shouldReturnUserWhenIdExists() throws Exception {
        // given
        User user = UserTestDataFactory.createDefault();
        when(userService.findById(1L)).thenReturn(user);

        // when / then
        mockMvc.perform(get("/api/users/{id}", 1L))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id", is(1)))
            .andExpect(jsonPath("$.email", is("jane@example.com")));
    }

    @Test
    @DisplayName("should return 404 when user does not exist")
    void shouldReturn404WhenUserDoesNotExist() throws Exception {
        // given
        when(userService.findById(99L)).thenThrow(new UserNotFoundException(99L));

        // when / then
        mockMvc.perform(get("/api/users/{id}", 99L))
            .andExpect(status().isNotFound());
    }

    @Test
    @DisplayName("should reject request when email format is invalid")
    void shouldRejectRequestWhenEmailFormatIsInvalid() throws Exception {
        // given
        CreateUserRequest request = CreateUserRequestTestDataFactory.createWithEmail("not-an-email");

        // when / then
        mockMvc.perform(post("/api/users")
                .contentType(MediaType.APPLICATION_JSON)
                .content(objectMapper.writeValueAsString(request)))
            .andExpect(status().isBadRequest());
    }
}
```

## JUnit 4 variant

```java
@RunWith(SpringRunner.class)
@WebMvcTest(UserController.class)
public class UserControllerTest {

    @Autowired private MockMvc mockMvc;  // OK for @RunWith style; constructor injection on JUnit 4 is awkward
    @MockBean private UserService userService;

    @Test
    public void shouldReturnUserWhenIdExists() throws Exception {
        // given
        User user = UserTestDataFactory.createDefault();
        when(userService.findById(1L)).thenReturn(user);

        // when / then
        mockMvc.perform(get("/api/users/1"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id", is(1)));
    }
}
```

Note: JUnit 4 has no `@DisplayName`. Put the human-readable description in a Javadoc comment above the method, keep the method name in the same `should...When...` form, and preserve the given/when/then comments. JUnit 4's idiom also tends to lean on field `@Autowired` because constructor injection on JUnit 4 is clunky; this is the one place convention #7 bends.

## Asserting on response body

Prefer JsonPath matchers (`jsonPath("$.field", is(value))`) for quick field-level checks. For structural assertions on a deserialized DTO, use AssertJ on the parsed body:

```java
// then
MvcResult result = mockMvc.perform(get("/api/users/1"))
    .andExpect(status().isOk())
    .andReturn();

UserResponse body = objectMapper.readValue(result.getResponse().getContentAsString(), UserResponse.class);
assertThat(body)
    .extracting(UserResponse::getId, UserResponse::getEmail)
    .containsExactly(1L, "jane@example.com");
```

## What to cover

For a controller with endpoints for GET/POST/PUT/DELETE, a good coverage set is typically:

- One happy-path test per endpoint.
- 4xx tests for each distinct error surface: 400 (validation), 404 (not found), 409 (conflict), 403 (forbidden).
- Validation: one test per bound field's constraint (`@NotBlank`, `@Email`, `@Size`). Don't try to cover all combinations — cover each constraint once.
- Serialization quirks worth testing: dates/times, enums, nullable fields that should be omitted, fields renamed via `@JsonProperty`.

## Common gotchas

- **`@WebMvcTest` doesn't load `@Service`/`@Repository` beans.** Mock collaborators with `@MockBean`. If the controller depends on something unusual (a `Clock`, a `MessageSource`), mock that too.
- **Spring Security is active in `@WebMvcTest`.** If your controller is behind auth, tests will 401/403 unless you either disable security (`@AutoConfigureMockMvc(addFilters = false)` — avoid) or authenticate (`@WithMockUser`, `jwt()` post-processor). See `security-tests.md`.
- **Validation annotations must be on the controller method parameter** (`@Valid @RequestBody CreateUserRequest req`) for `MethodArgumentNotValidException` to fire. A missing `@Valid` silently ignores constraints.
- **Do not use `webAppContextSetup` manually** — `@WebMvcTest` wires MockMvc for you. Injecting both confuses the bean graph.
