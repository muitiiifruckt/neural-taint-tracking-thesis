---
title: T3 — спецификация
---

<nav class="site-nav">
<a href="./">Главная</a>
<a href="architecture">Архитектура</a>
<a href="results">Результаты</a>
<a href="reproduce">Как запустить</a>
<a href="PROJECT_EXPLAINED">Подробный разбор</a>
<a href="T1_SPEC">T1</a>
<a href="T2_SPEC">T2</a>
<a href="T3_SPEC" class="active">T3</a>
<a href="https://github.com/muitiiifruckt/neural-taint-tracking-thesis">GitHub</a>
</nav>

# Спецификация T3: field-sensitive gate

## Цель

T3 уточняет строгий gate T2 до уровня полей: privileged tool call блокируется **только если
tainted-значение попало в sensitive поле** этого инструмента. Ключевой исследовательский
вопрос проекта: снижает ли field-sensitive gating Targeted ASR, сохраняя Benign Utility
лучше, чем strict gate T2.

## Мотивация (из ожидаемых false positives T2)

Легитимные workspace-задачи постоянно копируют untrusted контент в *контентные* поля:
«перешли текст письма», «создай файл со списком встреч», «ответь на приглашение» — тело
письма/файла обязано содержать данные из tool outputs. Опасность не в контенте, а в том,
**куда** уходит действие (адресат, участник) и **какой объект** уничтожается/меняется
(id письма/события/файла). T2 блокирует и то и другое; T3 блокирует только второе.

## Таблица sensitive fields (workspace suite, v1.2.2)

Единственный источник истины — `src/taint/policy.py::SENSITIVE_FIELDS`.

| Tool | Sensitive fields | Non-sensitive (allow tainted) | Обоснование sensitive |
|---|---|---|---|
| `send_email` | `recipients`, `cc`, `bcc`, `attachments` | `subject`, `body` | адресаты = exfiltration target |
| `delete_email` | `email_id` | — | выбор уничтожаемого объекта |
| `create_calendar_event` | `participants` | `title`, `description`, `location`, `start_time`, `end_time` | участники получают приглашение (утечка) |
| `cancel_calendar_event` | `event_id` | — | выбор отменяемого события |
| `reschedule_calendar_event` | `event_id` | `new_start_time`, `new_end_time` | выбор переносимого события |
| `add_calendar_event_participants` | `event_id`, `participants` | — | и цель, и новые получатели |
| `create_file` | — (нет) | `filename`, `content` | создание нового файла ничего не уничтожает и никуда не отправляет |
| `delete_file` | `file_id` | — | выбор уничтожаемого файла |
| `share_file` | `file_id`, `email` | `permission` | какой файл и кому расшаривается |
| `append_to_file` | `file_id` | `content` | выбор изменяемого файла |

Правило принятия решения: span path аргумента (например `$.recipients[0]`) сводится к
имени поля верхнего уровня (`top_level_field`), и вызов блокируется, если это поле в
`SENSITIVE_FIELDS[tool]` и метка span — `untrusted`/`derived_untrusted`.

## Реализация

Тот же `GatingToolsExecutor`, что и T2, но `mode="field"` — вся разница инкапсулирована в
`gate_decision` (`src/taint/policy.py`). Формат trace идентичен T2 (`blocked`, `gate_reason`,
`tainted_paths`), поэтому blocked-события T2 и T3 сравнимы напрямую.

## Ожидаемый эффект относительно T2

- Benign Utility должна восстановиться к уровню T0/T1 там, где T2 блокировал копирование
  контента (`body`, `content`).
- Targeted ASR (direct-achievable subset — основная метрика) должен остаться существенно
  ниже T0/T1: цели атак в suite — отправка писем на адрес атакующего, удаление/шаринг
  объектов — проходят именно через sensitive поля.
- Известный residual-риск: атака, чья цель — записать payload в *контентное* поле
  (например, текст письма), полем-sensitive gate не блокируется. Это осознанный trade-off,
  фиксируется в финальном отчёте.

## Критерии приёмки

- Unit-тесты: allow tainted non-sensitive поля (`body`), block tainted sensitive
  (`recipients`); `create_file` не блокируется никогда; таблица полей покрывает каждый
  privileged tool (`tests/test_gate_policy.py`, `tests/test_gating_executor.py`).
- Полный eval на тех же 150 кейсах; сравнение T3 vs T2 по overblock rate и Benign Utility,
  T3 vs T0/T1 по ASR.
- Traces различают blocked sensitive leakage и allowed non-sensitive taint.
