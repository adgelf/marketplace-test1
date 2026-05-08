# Stack Detection

Before reviewing, build a stack profile. The review's usefulness depends on it: "deprecated" means nothing until you know which version the project is on.

## What you need to know (and why)

| Signal | Why it matters |
|---|---|
| Spring Boot version | `javax.*` vs `jakarta.*`, removed APIs (`WebSecurityConfigurerAdapter`), new features (observability API, `@HttpExchange`), default library versions |
| Java version | Which language features you can recommend (records 16+, sealed types 17+, pattern matching 17+/21, virtual threads 21) |
| Spring Security style | 5.x: `extends WebSecurityConfigurerAdapter`. 6.x: `SecurityFilterChain` bean. Different DSLs, different authorization config |
| ORM / data layer | JPA-specific advice (N+1, fetch joins, `@EntityGraph`) only applies when JPA is on the classpath. Mongo and plain JDBC need different advice |
| Logging framework | SLF4J API is the same; Logback vs Log4j2 config files and async appender patterns differ |
| Micrometer / Actuator | Whether metrics / tracing suggestions are actionable or require adding a dependency |
| Build tool | Only matters for "to add this library" suggestions |
| Neighbouring code style | Constructor injection with Lombok vs explicit constructor, base test class patterns, team idioms |

## Detection checklist

### 1. Spring Boot version

**Maven** — look in `pom.xml` for one of:

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.2.1</version>
</parent>
```

Or in `<dependencyManagement>`:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-dependencies</artifactId>
    <version>2.7.18</version>
    <scope>import</scope>
</dependency>
```

**Gradle** — look in `build.gradle` / `build.gradle.kts`:

```groovy
plugins {
    id 'org.springframework.boot' version '3.1.5'
}
```

or a `gradle.properties` entry, or a `libs.versions.toml` entry.

**Rule of thumb:** 2.x ↔ `javax.*`, Security 5, `WebSecurityConfigurerAdapter` still allowed. 3.x ↔ `jakarta.*`, Security 6, `SecurityFilterChain` mandatory.

### 2. Java version

**Maven:**
```xml
<properties>
    <java.version>17</java.version>
</properties>
```
or
```xml
<maven.compiler.release>17</maven.compiler.release>
```

**Gradle:**
```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
```
or `sourceCompatibility = '11'`.

If nothing is declared, look at imports: `java.util.Optional<T> orElseThrow(Supplier)` + `var` usage ⇒ ≥ 11; `record` usage ⇒ ≥ 16; `sealed`, pattern matching for `instanceof` without extra casts ⇒ ≥ 17; `Thread.ofVirtual()` or virtual-thread config ⇒ ≥ 21.

### 3. Spring Security configuration style

This is the one that catches people out. The two styles look superficially similar but are not interchangeable.

**Security 5 / Spring Boot 2 style** — class extends `WebSecurityConfigurerAdapter` and overrides `configure(HttpSecurity)`:

```java
@Configuration
@EnableWebSecurity
public class SecurityConfig extends WebSecurityConfigurerAdapter {
    @Override
    protected void configure(HttpSecurity http) throws Exception {
        http.authorizeRequests()
            .antMatchers("/admin/**").hasRole("ADMIN")
            .anyRequest().authenticated()
            .and().csrf().disable();
    }
}
```

Note: `authorizeRequests()`, `antMatchers(...)`, `.and().csrf()` — this DSL is deprecated in 5.7+ and removed in 6.

**Security 6 / Spring Boot 3 style** — no base class, returns a `SecurityFilterChain` bean:

```java
@Configuration
@EnableWebSecurity
public class SecurityConfig {
    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated())
            .csrf(AbstractHttpConfigurer::disable)
            .build();
    }
}
```

Note: `authorizeHttpRequests()`, `requestMatchers()` (not `antMatchers`), lambda-style DSL.

**When reviewing:**
- A Security 5 project using `WebSecurityConfigurerAdapter` is idiomatic, not deprecated. Don't recommend migration in the critical path — only as a tech-debt Suggestion.
- A Security 6 project *still using* `antMatchers` (deprecated in 5.8, removed in 6.x) is a Major: the code will break on the next minor upgrade.
- A Spring Boot 3 project using `WebSecurityConfigurerAdapter` literally doesn't compile, so you won't see it — but if you do (partial migration in progress), that's Critical.

### 4. ORM / data layer

Scan dependencies for:
- `spring-boot-starter-data-jpa` → JPA (Hibernate). Load `performance.md` when a repository or entity changes.
- `spring-boot-starter-data-mongodb` → Mongo. N+1 advice doesn't apply; `@DBRef` has its own fetch semantics.
- `spring-boot-starter-jdbc` → plain JDBC / `JdbcTemplate`. No JPA advice.
- `spring-boot-starter-data-r2dbc` → reactive, different rules (see reactive section in `performance.md`).
- `spring-boot-starter-data-jdbc` (note: not -jpa) → Spring Data JDBC. Similar to JPA at API level but no lazy loading, so no N+1.

A project can have more than one. Match the finding to the stack used by the file you're reviewing.

### 5. Logging framework

SLF4J is the API everyone writes against (`org.slf4j.Logger`). The implementation underneath varies:

- **Logback** — default for Spring Boot starters. `logback-spring.xml` or `logback.xml` in `src/main/resources`. `spring-boot-starter-logging` is the transitive dependency.
- **Log4j2** — `log4j2-spring.xml`. Team has explicitly excluded `spring-boot-starter-logging` and added `spring-boot-starter-log4j2`.

Both expose the same SLF4J call sites, so review advice about log levels and parameterized messages (`log.info("...{}...", id)`) is the same. The only place this matters is if you're suggesting an async appender or a structured logging config — the config syntax differs.

### 6. Micrometer / Actuator

Look for `spring-boot-starter-actuator` and/or `micrometer-core`, `micrometer-registry-*`. If absent, don't propose "add a counter / timer" — propose the concept ("consider emitting a metric for X") and note the dependency isn't present.

### 7. Build tool

`pom.xml` ⇒ Maven. `build.gradle` / `build.gradle.kts` ⇒ Gradle. Matters only when you're telling the user "add dependency X" — use the right syntax for their build.

### 8. Neighbouring code style

Pick one existing `@RestController`, one `@Service`, one security config, and one test class. Note:

- Is constructor injection explicit (`public Foo(Bar bar) { this.bar = bar; }`) or Lombok (`@RequiredArgsConstructor` + `private final Bar bar;`)?
- How are DTOs shaped — records, Lombok `@Value`, classic POJOs with getters?
- Is there a common base controller / response wrapper / error handler?
- Is there a `*TestDataFactory` / `*Fixtures` convention?
- Does the module use a specific validation pattern (`@Valid`, custom validator, Bean Validation 2.0 / 3.0)?

When you propose a fix, match the local style. Recommending `@RequiredArgsConstructor` in a codebase that bans Lombok is as bad as recommending `WebSecurityConfigurerAdapter` in Security 6.

## How to report the detected stack

In the review report's "Stack detected" line, be compact:

> **Stack detected:** Spring Boot 3.1.5, Java 21, Spring Security 6 (`SecurityFilterChain`), Spring Data JPA, Logback, Maven.

If something was ambiguous or unavailable:

> **Stack detected:** Spring Boot 2.7.x (from `import javax.*`), Java unknown, Spring Security 5 (`WebSecurityConfigurerAdapter`), Spring Data JPA, Logback, Maven. No access to build file — Java version inferred from `var` usage (≥ 11).

The point is to make it obvious to the reader on what basis you were reviewing, so they can push back if you got a signal wrong.

## When you only have a snippet

If the user pasted a single method or class with no repo context:

- Scan the snippet for `javax.*` vs `jakarta.*` imports — that gives you Boot 2 vs 3.
- Look at which Security DSL is in use, or which `@Query` / entity annotations appear.
- If you truly can't tell, pick the most common modern default (Spring Boot 3, Java 17, Security 6) and state the assumption explicitly in the Stack detected line. The user can correct you, and your review won't quietly assume one world while they live in another.
