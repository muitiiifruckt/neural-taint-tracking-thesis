---
title: Архитектура
---

[Главная](./) · [Архитектура](architecture) · [Результаты](results) · [Как запустить](reproduce) · [GitHub-репозиторий](https://github.com/muitiiifruckt/neural-taint-tracking-thesis)

# Архитектура

## Threat model

- **Доверено**: system prompt, задача пользователя, схемы tools.
- **Не доверено**: всё, что возвращают tools — тела писем, описания календарных событий,
  содержимое файлов — и всё, что из этого производно (скопировано, процитировано,
  переписано).
- **Привилегированные sinks** — tools, меняющие внешнее состояние: отправка письма, удаление
  файла, создание события календаря и т.п. Именно перед их вызовом защита принимает решение.

Защита не пытается быть formal noninterference proof — заявляется только эмпирическая метрика
(частота успешных атак), не формальное доказательство отсутствия утечки.

## Ядро: символический taint-tracking

Лёгкий по зависимостям слой, не завязанный на конкретный агентный фреймворк.

### Метки доверия

- `trusted` — system prompt, задача пользователя, схемы tools.
- `untrusted` — прямой tool output.
- `derived_untrusted` — текст, скопировавший/включивший в себя untrusted-контент.

Каждый размеченный фрагмент (`span`) хранит текст, метку, источник и `parents` — ссылки на
spans, из которых он произошёл. Это даёт полный **lineage**: можно проследить цепочку «письмо
прочитано → его текст скопирован в аргумент `send_email`».

### Схема распространения меток

<pre class="mermaid">
flowchart LR
    A["Tool output"] -->|"mark_tool_output"| B["TaintRegistry: untrusted spans"]
    B -->|"derive_from_text перед следующим call"| C["Аргументы tool call"]
    C -->|"найдено совпадение (>= 4 символов, в любом направлении)"| D["derived_untrusted span, parent = исходный span"]
    C -->|"совпадения нет"| E["trusted"]
</pre>

### Правила распространения (propagation)

1. Каждый строковый лист tool output (рекурсивно — dict/list/tuple/set обходятся полностью)
   получает метку `untrusted`.
2. Строка-аргумент будущего tool call, содержащая текст уже размеченного untrusted span **в
   любом направлении** — то есть либо span целиком скопирован в новый текст, либо, наоборот,
   новый текст является короткой подстрокой большого untrusted-блока (например, email-адрес,
   извлечённый из описания календарного события с внедрённым payload'ом) — получает метку
   `derived_untrusted` с этим span как parent.
3. Совпадения короче 4 символов игнорируются с обеих сторон, чтобы случайные короткие строки
   (например, числовой id) не создавали ложных срабатываний. Это осознанный trade-off: он же
   создаёт единственный практически наблюдаемый способ обойти защиту (см. [«Результаты»](results)).

### Интеграция с агентным pipeline

Стандартный исполнитель tool calls форматирует результат в одну плоскую строку **до** того, как
её можно разметить по отдельным полям — то есть штатный путь убивает гранулярность, нужную для
правила №2. Поэтому исполнитель tool calls форкнут: перед выполнением вызова он размечает
аргументы по уже накопленным untrusted spans, выполняет вызов ровно один раз (без дублирования
побочных эффектов), затем размечает сырой структурированный результат **до** его форматирования
в строку. Видимое поведение агента при этом не меняется — слой только наблюдает (T1) либо,
дополнительно, принимает решение блокировать вызов (T2/T3).

Каждый сценарий получает собственный, изолированный набор spans — taint одного сценария не
протекает в другой.

### Сквозной пример: как атака доходит до gate

<pre class="mermaid">
sequenceDiagram
    participant U as Пользователь
    participant A as Агент
    participant C as read_calendar_event (tool)
    participant M as send_email (tool)

    U->>A: Запланируй встречу по описанию события
    A->>C: read_calendar_event(...)
    C-->>A: description содержит скрытую инструкцию + email атакующего
    Note over A: description размечен как untrusted
    A->>M: send_email(recipients=[email атакующего], ...)
    Note over M: recipients получен из untrusted description → derived_untrusted
    M--xA: gate (T2/T3): вызов заблокирован
</pre>

## Gate-политика (T2/T3)

### Решение gate

<pre class="mermaid">
flowchart TD
    Call["Tool call"] --> Priv{"Привилегированный tool?"}
    Priv -- нет --> Allow["Выполнить без проверки"]
    Priv -- да --> Mode{"Режим gate"}
    Mode -- "off (T1)" --> Allow
    Mode -- "strict (T2)" --> AnyTaint{"Есть непроверенный аргумент?"}
    Mode -- "field (T3)" --> SensTaint{"Непроверенный контент в sensitive-поле?"}
    AnyTaint -- нет --> Allow
    AnyTaint -- да --> Block["Заблокировать, вернуть ошибку агенту"]
    SensTaint -- нет --> Allow
    SensTaint -- да --> Block
</pre>

### Привилегированные tools

`send_email`, `delete_email`, `create_calendar_event`, `cancel_calendar_event`,
`reschedule_calendar_event`, `add_calendar_event_participants`, `create_file`, `delete_file`,
`share_file`, `append_to_file`. Только эти tools проверяются gate — tools только для чтения
никогда не блокируются.

### Две политики

- **Strict (T2)** — блокирует вызов, если **хоть один** аргумент (на любой глубине) помечен
  как непроверенный.
- **Field-sensitive (T3)** — блокирует только если непроверенный контент попал в поле, реально
  управляющее тем, **куда уходят данные** или **какой объект уничтожается/меняется**;
  контентные поля (тело письма, описание, заголовок) пропускаются без блокировки.

### Таблица sensitive fields (T3)

| Tool | Sensitive-поля | Почему |
|---|---|---|
| `send_email` | `recipients`, `cc`, `bcc`, `attachments` | куда уходят данные |
| `delete_email` | `email_id` | какой объект уничтожается |
| `create_calendar_event` | `participants` | кто получает доступ/приглашение |
| `cancel_calendar_event` | `event_id` | какой объект уничтожается |
| `reschedule_calendar_event` | `event_id` | какой объект меняется |
| `add_calendar_event_participants` | `event_id`, `participants` | и объект, и получатели |
| `create_file` | — | новый локальный объект — некуда «утечь» |
| `delete_file` | `file_id` | какой объект уничтожается |
| `share_file` | `file_id`, `email` | какой объект и кому раскрывается |
| `append_to_file` | `file_id` | какой объект модифицируется |

Логика: routing/exfiltration-цели и id уничтожаемого объекта — sensitive; контентные поля —
нет, потому что копирование текста в контент (переслать письмо, процитировать описание
встречи) — нормальное поведение при выполнении легитимной задачи, и блокировка именно этого —
источник ложных срабатываний строгой политики.

Полные технические спецификации каждого этапа — в репозитории:
[T1](https://github.com/muitiiifruckt/neural-taint-tracking-thesis/blob/master/docs/T1_SPEC.md) ·
[T2](https://github.com/muitiiifruckt/neural-taint-tracking-thesis/blob/master/docs/T2_SPEC.md) ·
[T3](https://github.com/muitiiifruckt/neural-taint-tracking-thesis/blob/master/docs/T3_SPEC.md).
