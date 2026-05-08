# Logging Review

SLF4J is the API everywhere in Spring; the underlying framework (Logback / Log4j2) doesn't change the review criteria. Focus on three things: what context is in the message, what level is it at, and is it parameterized correctly.

## Parameterized vs concatenated messages

**Flag when you see:**
- `log.info("Processing order " + orderId + " for user " + userId)` — string concat.
- `log.debug("request: " + new Gson().toJson(request))` — even worse; builds the JSON every call, even when DEBUG is disabled.
- `log.error(String.format("failed to save %s", entity))` — same story, eager evaluation.

**Why it matters:** SLF4J's `{}` placeholders are lazily evaluated — if the log level is disabled, the `toString()` never runs. Concatenation happens before `log.info` is even called; you pay the CPU and allocation cost whether the log is emitted or not. On a hot path, this shows up in profiles.

**Fix:**
```java
log.info("processing order {} for user {}", orderId, userId);
log.error("failed to save entity id={} reason={}", entity.getId(), e.getMessage(), e);
```

Note the last example: an `e` at the end (not as a placeholder argument) is recognised by SLF4J as the throwable to attach — that's how you log stack traces cleanly.

**Severity:** Minor, except on clearly hot paths (request filters, per-message handlers) where it becomes Major.

## Missing context

A log line without identifiers is a log line you'll stare at during an incident wishing you'd included more.

**Flag when you see:**
- `log.error("failed to process")` with no IDs.
- `log.warn("invalid input", e)` with no indication of *what* input or *which* caller.
- `log.info("starting nightly job")` then no further context through the job.
- Request-level logging with no correlation ID / MDC key.

**What good context looks like:**
- For an entity operation: the entity type, the ID(s), and the user/tenant if relevant.
- For an external call: the endpoint, the operation, maybe the request ID.
- For an error: the cause (pass the exception), plus what you were trying to do, plus any input that's safe to log.

```java
log.error("failed to fulfil order orderId={} userId={} status={} reason={}",
    order.getId(), order.getUserId(), order.getStatus(), e.getMessage(), e);
```

**Severity:** Minor for individual instances. Major when an error path has no useful context at all — that's an incident-response liability.

## Sensitive data in logs

Covered in `security.md` (Sensitive data in logs). If you're on the logging review pass and see `log.info("user: {}", user)` where the user object has a password field, that's a security finding, not a logging finding — file it under Critical or Major per the security checklist.

## Level misuse

Each level has a specific meaning. Using the wrong one either spams production logs or hides real problems.

| Level | For |
|---|---|
| ERROR | Something failed and the system couldn't recover / complete. Requires a human (or alert) to look at. |
| WARN | Something unusual but the system continued. Often recoverable errors, retries, degraded states. |
| INFO | Business-significant events worth knowing in aggregate: startup, shutdown, job-started, major state transitions. NOT per-request. |
| DEBUG | Development-time detail; disabled in production by default. |
| TRACE | Very fine-grained, usually only turned on for specific classes when debugging. |

**Flag when you see:**
- `log.info` on every request or per-record in a loop — floods the log, drowns out real signal.
- `log.error` on a validation failure that's a normal 400-response case (e.g. bad input from a client). That's a `WARN` at most, often DEBUG — the client caused it, not the server.
- `log.warn` on fully-handled business states (e.g. "user has no orders yet") — that's INFO or nothing.
- `log.debug` left with production-meaningful data but at a level that's off in prod — gives false confidence that it's being logged.
- Catching an exception and logging as `warn` when the flow actually failed and the caller is getting a stack trace — should be `error`.

**Severity:** Minor for individual mistakes. Major when the mistake affects alerting / on-call (a real error suppressed as info, or a flood of "errors" that drown the real ones).

## Double logging

A specific anti-pattern: logging an exception in a low-level method, then throwing it, then the caller also logs it, then it hits the global exception handler which logs again.

**Flag when you see:**
- `catch (Exception e) { log.error("...", e); throw e; }` — if the upstream code logs too, you get the stack trace three times.
- A service method that logs the error, then re-throws; the `@ControllerAdvice` also logs.
- A filter and a handler both logging the same exception.

**Fix:** Log once. Usually at the boundary where the decision about what to do with the error is made — typically the controller advice / filter that turns the exception into a response. Lower-level code can re-throw or wrap, but shouldn't log unless adding genuinely new context.

**Severity:** Minor, unless the duplicate logs are degrading log volume meaningfully.

## MDC / correlation IDs

If the project uses MDC for tracing, flag anywhere a new execution context (new thread, `@Async`, scheduled task) is started without propagating MDC. Missing MDC on async means logs from that task won't correlate with the triggering request.

**Flag when you see:**
- `@Async` method or `ExecutorService.submit(...)` without an MDC-propagating wrapper in a codebase that uses MDC elsewhere.
- New `Thread`s created manually (already a smell) and launched without MDC copy.

**Fix:** Use `MdcTaskDecorator` on the `ThreadPoolTaskExecutor`. For manual executors, wrap runnables: capture `MDC.getCopyOfContextMap()` at submission, restore inside the task.

**Severity:** Minor. Major if the codebase's on-call runbooks depend on correlation IDs.
