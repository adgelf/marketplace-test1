# Spec examples

Reference JSON specs for different carousel use cases. Read this when you need inspiration for structuring content or want to see how specific patterns map to the archetypes.

## Course announcement (Russian)

```json
{
  "title": "Kubernetes с нуля",
  "kicker": "новый поток",
  "subtitle": "от первого пода до продакшена за восемь недель",
  "author": "школа «Мирантис»",
  "slides": [
    {"type": "cover"},
    {"type": "content",
     "heading": "Для кого курс",
     "body": "Для backend-разработчиков, которые уже пишут сервисы, но знают кластер только как строчку в CI. Для тех, кто устал копировать чужие манифесты и хочет понимать, что на самом деле происходит за kubectl apply."},
    {"type": "content",
     "heading": "Восемь недель",
     "body": "От базовых объектов — Pod, Service, Deployment — к продвинутым темам: сетевым политикам, observability и кастомным контроллерам. Каждая неделя заканчивается практикой в настоящем кластере, а не в песочнице."},
    {"type": "content",
     "heading": "Что вы унесёте",
     "body": "Не заученные команды, а рабочую модель Kubernetes в голове. Понимание, где оркестратор помогает, а где лезть туда не стоит. Свой pet-проект, задеплоенный к выпуску."},
    {"type": "closing",
     "body": "Старт 10 марта",
     "cta": "запись · @mirantis.school"}
  ]
}
```

Notes: kicker is short and lowercase in the source (gets uppercased in render). Subtitle is a single clarifying line — don't stuff a full description here.

## Engineer spotlight

```json
{
  "title": "Leslie Lamport",
  "kicker": "engineer notes",
  "subtitle": "New York, b. 1941",
  "author": "mirantis.notes",
  "slides": [
    {"type": "cover"},
    {"type": "content",
     "heading": "Proving before building",
     "body": "Lamport's core move is to write what a system should do before writing how it does it. TLA+ makes that writable in a language a machine can check. The discipline exposes race conditions and ambiguities that no amount of testing would have caught — because tests only run the paths you thought to run."},
    {"type": "content",
     "heading": "Time, clocks, Paxos",
     "body": "His 1978 paper on logical clocks gave distributed systems a usable notion of ordering without a shared wall-clock. Twenty years later Paxos gave them consensus without shared trust. Both read like field reports from somewhere that had already solved the problem."},
    {"type": "closing",
     "body": "Further reading in our notes",
     "cta": "mirantis.notes/lamport"}
  ]
}
```

Notes: cover author is a handle rather than a person here. Closing CTA is a URL — equally valid as a handle. Keep content bodies to 2–3 sentences.

## Single-concept explainer (English)

```json
{
  "title": "The art of choosing",
  "subtitle": "why good taste is a practiced skill",
  "author": "sacha",
  "slides": [
    {"type": "cover"},
    {"type": "content",
     "heading": "Taste is not innate",
     "body": "It looks innate because people who have it don't narrate the process. But the discrimination — this yes, that no — is built on thousands of small noticings. The question is never whether to develop taste, only whether to develop it deliberately."},
    {"type": "content",
     "heading": "What looking trains",
     "body": "The eye is a muscle in the sense that matters: repeated attention reshapes what feels obvious. A year of looking at paintings changes what your kitchen counter looks like."},
    {"type": "closing",
     "body": "Looking is a practice",
     "cta": "continue →"}
  ]
}
```

Notes: no kicker on this cover (kicker is optional). Closing body is a takeaway, not a thank-you — that's fine; the archetype is flexible on tone.

## Quote-driven (single quote per slide)

Don't use quotes as a distinct archetype — fold them into content. Put the quote in `body` and attribution in `heading`, or vice versa depending on emphasis:

```json
{"type": "content",
 "heading": "— John Berger",
 "body": "Seeing comes before words. The child looks and recognizes before it can speak. But there is also another sense in which seeing comes before words. It is seeing which establishes our place in the surrounding world."}
```

## Anti-patterns

Don't invent archetypes. If you're tempted to write `{"type": "quote"}` or `{"type": "section_divider"}` — resist. The three archetypes are load-bearing. A quote is just a content slide; a section break is usually an indication you have too many slides.

Don't cram bullet points into body text. Rewrite lists as flowing sentences:
  - Bad body: `"• Composition\n• Light\n• Gesture\n• Color"`
  - Good body: `"Composition first — how the eye is led. Then light, then gesture, then color. In that order, because each depends on the one before."`

Don't put more than ~80 words in a content body. If you need more, split across two content slides.
