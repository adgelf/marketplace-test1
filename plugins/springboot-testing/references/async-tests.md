# Async and scheduled tests (Awaitility, @Async, @Scheduled)

## The core problem

The thing you're asserting hasn't happened yet. `verify(emailService).send(...)` called immediately after a method that triggers an async email returns false positives until the other thread gets around to running — or worse, passes on a fast laptop and fails on a loaded CI runner. The fix is to wait *for a condition*, not a duration.

`Thread.sleep(500)` is not a fix. It's slow on the common case and still flaky on the rare case.

## The tool: Awaitility

If the project has `org.awaitility:awaitility` on the classpath (or depends on `spring-boot-starter-test` on Boot 2.6+, which brings it transitively), use it.

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;
import static java.time.Duration.ofSeconds;

@Test
@DisplayName("should send welcome email when user is created")
void shouldSendWelcomeEmailWhenUserIsCreated() {
    // given
    CreateUserRequest request = CreateUserRequestTestDataFactory.createDefault();

    // when
    userService.create(request);

    // then
    await().atMost(ofSeconds(5)).untilAsserted(() ->
        verify(emailService).sendWelcome(request.getEmail())
    );
}
```

Key patterns:

- `.atMost(ofSeconds(5))` — how long before giving up.
- `.pollInterval(ofMillis(100))` — how often to check. Default is 100ms; usually fine.
- `.untilAsserted(() -> ...)` — runs the lambda; if it throws (AssertionError from AssertJ, or Mockito's `WantedButNotInvoked`), Awaitility waits and retries. On the first successful run, the test passes.
- `.until(() -> someSupplier.get())` — for simple boolean conditions (`.until(() -> queue.size() == 1)`).

## @Async tests

If the production method is `@Async`, decide whether you're testing:

**(a) That the method does what it says, regardless of async.** Just test the body directly with Mockito and ignore the async-ness. `@Async` on an interface method is just an annotation; the underlying code still runs synchronously from a test that calls the implementation directly.

**(b) That the async behaviour works end-to-end** (e.g. "the controller returns immediately, and the work completes in the background"). This is a `@SpringBootTest` scenario because `@Async` only activates in a Spring context with `@EnableAsync`. Use Awaitility to wait for the side effect.

```java
@SpringBootTest
class NotificationIT {
    @SpyBean private EmailService emailService;
    private final NotificationController controller;

    NotificationIT(@Autowired NotificationController controller) {
        this.controller = controller;
    }

    @Test
    @DisplayName("should send email asynchronously when notify is called")
    void shouldSendEmailAsynchronouslyWhenNotifyIsCalled() {
        // given
        NotifyRequest request = NotifyRequestTestDataFactory.createDefault();

        // when
        controller.notify(request);

        // then
        await().atMost(ofSeconds(5)).untilAsserted(() ->
            verify(emailService).send(request.getRecipient(), anyString())
        );
    }
}
```

`@SpyBean` (real bean wrapped in a Mockito spy) is the right choice here — `@MockBean` would replace the `EmailService` entirely, breaking any downstream logic. You want the real thing, with the ability to verify interactions.

## @Scheduled tests

Testing `@Scheduled` directly is almost always the wrong idea — you're testing Spring's scheduler, not your code. Two options:

**(a) Test the scheduled method directly.** Call it from a unit test as a plain method. Verify the logic.

```java
@ExtendWith(MockitoExtension.class)
class ReportJobTest {
    @Mock private ReportService reportService;
    private ReportJob reportJob;

    @BeforeEach
    void setUp() { reportJob = new ReportJob(reportService); }

    @Test
    @DisplayName("should generate daily report when runDaily is invoked")
    void shouldGenerateDailyReportWhenRunDailyIsInvoked() {
        // given: nothing special

        // when
        reportJob.runDaily();

        // then
        verify(reportService).generateDailyReport();
    }
}
```

**(b) If you genuinely need to verify the scheduling triggers** (the cron expression, the rate), use a `@SpringBootTest` with a very short test-only schedule (override via `@TestPropertySource`) and Awaitility to wait for the expected number of invocations. Use sparingly — this is usually overkill.

## Kafka listeners

Kafka listeners are async by construction. The test pattern:

```java
@Test
@DisplayName("should persist event when message is received")
void shouldPersistEventWhenMessageIsReceived() {
    // given
    UserEvent event = UserEventTestDataFactory.createDefault();
    kafkaTemplate.send("user-events", event);

    // when / then
    await().atMost(ofSeconds(10)).untilAsserted(() ->
        assertThat(userEventRepository.findByCorrelationId(event.getCorrelationId())).isPresent()
    );
}
```

With `@EmbeddedKafka`, you can also use `ContainerTestUtils.waitForAssignment(...)` in `@BeforeEach` to make sure the listener is actually consuming before you publish — otherwise the first test occasionally races the partition assignment.

## Verifying "it didn't happen" asynchronously

The tricky one. `verify(mock, never()).method(...)` right after an async trigger tells you nothing — of course it hasn't happened *yet*. You need a bounded wait, *and then* the absence assertion. Awaitility has `.during()` for this:

```java
// then — verify emailService is NOT called within a 2-second window
await().during(ofSeconds(2)).atMost(ofSeconds(3)).untilAsserted(() ->
    verify(emailService, never()).send(any(), any())
);
```

This is inherently slow — the test waits for 2 full seconds. Use only when "it shouldn't happen" is the actual behaviour under test.

## Common gotchas

- **`@Async` inside the same class as the caller doesn't work.** Spring AOP proxies only intercept external calls. If `methodA()` calls `this.asyncMethodB()`, `asyncMethodB` runs synchronously. Tests that seem to "work synchronously" for an async method are often revealing this bug — mention it to the user.
- **Thread pool exhaustion.** The default `@Async` executor (SimpleAsyncTaskExecutor) spawns a new thread per call. Under test load, tests can run, the pool can be saturated, and calls silently block. Configure a bounded `ThreadPoolTaskExecutor` in prod; test with it too.
- **`@SpyBean` on a `@Service` with `@Async`.** Mockito's spy wraps the bean *inside* the proxy — `verify(spy).asyncMethod(...)` works, but argument-matcher semantics can behave oddly with deep stubs. Prefer asserting on the side effect (DB row, outgoing message) rather than on the async method invocation itself.
- **Don't `Thread.sleep()` "just to be safe" before an Awaitility call.** It's a smell that says "I don't trust the wait-for-condition"; either trust it or increase `.atMost`.
