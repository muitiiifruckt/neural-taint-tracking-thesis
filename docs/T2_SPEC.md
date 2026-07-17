# Спецификация T2: strict gate

## Цель

T2 включает первую блокирующую политику поверх T1-слоя наблюдения: **privileged tool call
блокируется, если хотя бы один аргумент содержит `untrusted` или `derived_untrusted` контент**
(правило «any tainted argument»). T2 отвечает на вопрос: насколько сильно грубая
provenance-блокировка снижает Targeted ASR и какой ценой по полезности (overblock).

## Отличие от T1

T1 (`ObservingToolsExecutor`) только записывает trace. T2 (`GatingToolsExecutor(mode="strict")`,
`src/taint/pipeline_element.py`) перед выполнением каждого tool call:

1. строит argument spans тем же `derive_argument_spans`, что и T1 (registry общий на кейс);
2. вызывает `gate_decision(tool_name, argument_spans, "strict")` (`src/taint/policy.py`);
3. если решение `blocked` — **не выполняет** tool call: в `messages` добавляется
   `ChatToolResultMessage` с `error`, объясняющим блокировку (LLM видит причину и может
   переформулировать), а в trace пишется событие `tool_call` с `blocked=true`,
   `gate_reason` и списком `tainted_paths`;
4. если `allowed` — выполняет и наблюдает output ровно как T1.

Заблокированные попытки остаются видимыми в traces — это требование для анализа
false positives (вход T3).

## Список privileged tools (workspace suite, v1.2.2)

Единственный источник истины — `src/taint/policy.py::PRIVILEGED_TOOLS`. Это все инструменты
suite, меняющие внешнее состояние:

| Tool | Побочный эффект |
|---|---|
| `send_email` | отправка письма наружу |
| `delete_email` | удаление письма |
| `create_calendar_event` | создание события + уведомление участников |
| `cancel_calendar_event` | отмена события |
| `reschedule_calendar_event` | перенос события |
| `add_calendar_event_participants` | добавление участников (уведомление) |
| `create_file` | создание файла в drive |
| `delete_file` | удаление файла |
| `share_file` | выдача доступа к файлу по email |
| `append_to_file` | изменение файла |

Read-only инструменты (`search_emails`, `get_current_day`, `search_calendar_events`,
`list_files`, ...) не блокируются ни при каком taint.

## Метрики

Те же три разделённые оценки, что и в T1 (`scripts/run_eval.py --stage t2`):

- benign user tasks (10) — ожидается **падение Benign Utility** из-за false positives:
  задачи вида «перешли содержимое письма X» легитимно копируют untrusted контент в аргументы
  `send_email`;
- security full set (140) и **direct-achievable subset (70, основная метрика ASR)** —
  ожидается заметное падение Targeted ASR относительно T0/T1;
- **overblock rate** — доля benign user tasks, в которых gate заблокировал хотя бы один
  вызов (`gate.benign_overblock_rate_pct` в `results/T2_summary.json`); плюс общее число
  заблокированных вызовов.

## Критерии приёмки

- Unit-тесты: strict блокирует privileged call с любым tainted-аргументом; не блокирует
  чистые вызовы и непривилегированные tools; заблокированный tool **не выполняется**
  (side effect не происходит); trace содержит `blocked=true` + причину
  (`tests/test_gate_policy.py`, `tests/test_gating_executor.py`).
- Полный eval на тех же 150 кейсах, что T0/T1; сравнение по direct-achievable ASR,
  full ASR, Benign Utility, Utility Under Attack, overblock rate.
- Из traces собран список false positives (заблокированные безобидные действия) как вход T3.
