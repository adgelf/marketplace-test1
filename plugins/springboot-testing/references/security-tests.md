# Security tests (Spring Security, JWT, method security)

## When this matters

Any test of a controller or service behind Spring Security has to satisfy the security layer — otherwise you get 401/403 where you expected a happy path, or (worse) 200 where you expected a denial. A test that disables security to "get around" the problem is a test that can't catch security regressions.

## The three authentication approaches

Pick the one that matches what the endpoint actually does. The prerequisite for all three is `org.springframework.security:spring-security-test` on the classpath.

### 1. `@WithMockUser` — simple role-based tests

Works with any auth setup. Populates the `SecurityContext` with a synthetic principal. Use when all you care about is "the caller is authenticated and has role X".

```java
@Test
@WithMockUser(roles = "ADMIN")
@DisplayName("should allow deletion when caller is admin")
void shouldAllowDeletionWhenCallerIsAdmin() throws Exception {
    // given
    doNothing().when(userService).delete(1L);

    // when / then
    mockMvc.perform(delete("/api/users/{id}", 1L))
        .andExpect(status().isNoContent());
}

@Test
@WithMockUser(roles = "USER")
@DisplayName("should forbid deletion when caller lacks admin role")
void shouldForbidDeletionWhenCallerLacksAdminRole() throws Exception {
    // when / then
    mockMvc.perform(delete("/api/users/{id}", 1L))
        .andExpect(status().isForbidden());
}
```

### 2. `jwt()` post-processor — JWT resource-server tests

When the app uses Spring Security's OAuth2 resource server (`spring-boot-starter-oauth2-resource-server`), tests should produce an authenticated JWT without signing one for real. `SecurityMockMvcRequestPostProcessors.jwt()` builds a mock `Jwt` and wires it into the security context for just that request:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;

@Test
@DisplayName("should return 200 when JWT has required scope")
void shouldReturn200WhenJwtHasRequiredScope() throws Exception {
    // when / then
    mockMvc.perform(get("/api/users/me")
            .with(jwt().jwt(j -> j
                .subject("user-123")
                .claim("email", "jane@example.com")
                .claim("scope", "users:read"))))
        .andExpect(status().isOk());
}
```

This is the right shape for Spring Security 5.2+ / Spring Boot 2.2+ apps that use `JwtAuthenticationConverter` or similar. If the app extracts custom claims into a principal object, set those claims in the `.jwt(j -> ...)` block.

### 3. Custom annotations (`@WithCustomUser`)

Teams often have a custom principal (`AppUser`, `CurrentUser`) with fields beyond username/roles. `@WithMockUser` can't populate that, so teams write a `@WithCustomUser` meta-annotation backed by a `WithSecurityContextFactory`. Look for one before writing a test — the signal is other tests using `@WithCustomUser(...)` or `@WithAppUser(...)`.

If one exists, use it:

```java
@Test
@WithAppUser(id = 42, email = "jane@example.com", roles = "USER")
@DisplayName("should return own profile when authenticated")
void shouldReturnOwnProfileWhenAuthenticated() throws Exception { ... }
```

If one doesn't exist but the controller clearly reads custom fields from the principal (e.g. `@AuthenticationPrincipal AppUser user`), either build the principal inline with `authentication(new UsernamePasswordAuthenticationToken(...))`, or — if this pattern recurs in the codebase — flag to the user that a `@WithAppUser` test helper would be worth creating.

## Method-level security

If the service uses `@PreAuthorize` / `@PostAuthorize`, unit tests with `@ExtendWith(MockitoExtension.class)` won't enforce it — there's no AOP proxy. To test method security, you either need a Spring test (`@SpringBootTest` or a minimal `@SpringJUnitConfig` that imports the security config) OR you test the security behaviour via the controller layer (usually cleaner).

## SecurityContext hygiene

Authentications set in a test can leak into subsequent tests if the context isn't reset. `@WithMockUser` / `@WithAppUser` handle this automatically via the test execution listener. Manual `SecurityContextHolder.getContext().setAuthentication(...)` does NOT — add `@AfterEach` cleanup:

```java
@AfterEach
void clearSecurity() {
    SecurityContextHolder.clearContext();
}
```

## CSRF

For state-changing requests (POST/PUT/DELETE) on Spring Security 4+, CSRF protection is enabled by default. MockMvc request needs `.with(csrf())` or the request is rejected with 403 — easy to misdiagnose as "permissions wrong":

```java
mockMvc.perform(post("/api/users")
        .with(csrf())
        .with(jwt())
        .contentType(MediaType.APPLICATION_JSON)
        .content(...))
    .andExpect(status().isCreated());
```

If the app is purely a JSON API with stateless sessions and CSRF disabled, no `csrf()` is needed — match your security config.

## What to cover

For each protected endpoint:
- Happy path with a valid principal / valid role / valid scope.
- 401 when unauthenticated (no principal).
- 403 when authenticated but lacking the required authority.
- If there's ownership logic ("users can only edit their own profile"), a test for both "correct owner" (200) and "wrong owner" (403).

Don't re-test framework behaviour (e.g. "expired JWT is rejected" — that's Spring Security's own test suite).

## Common gotchas

- **Mixing `@WithMockUser` and `jwt()`.** They both try to set up the SecurityContext. Pick one per test. `jwt()` is the right tool for resource-server apps; `@WithMockUser` is fine for form-login or basic-auth apps.
- **`@AutoConfigureMockMvc(addFilters = false)` defeats the purpose.** It bypasses the security filter chain entirely. If you see this in a test that's supposed to verify auth behaviour, it's a bug.
- **Spring Boot 2 vs 3 JWT imports.** `org.springframework.security.oauth2.server.resource.web.authentication` lives in the same package across versions, but the `Jwt` object and builder APIs have small evolutions. Match the version on the classpath.
