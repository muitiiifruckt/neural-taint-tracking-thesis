# T1 Results (tag-only taint tracking, gate disabled)

- Pipeline: `gpt-4o-mini-2024-07-18-t1-taint` via OpenRouter
- Suite: `workspace` (v1.2.2)
- Attack: `important_instructions`
- Defense: T1 tag-only taint tracking (`ObservingToolsExecutor` — observation only, никогда не блокирует)
- User tasks: 10 (`user_task_0` .. `user_task_9`)
- Security cases: **140** (10 user × 14 injection tasks), тот же набор, что и T0

Raw JSON: `results/T1_summary.json`. Per-case taint traces: `results/T1_traces/{case_id}.taint.json` (150 файлов: 10 benign + 140 security).

## Метрики: T1 vs T0

> **Важное исправление семантики (2026-07-17).** Сырое поле `security` в логах AgentDojo равно
> `True`, когда **цель инъекции достигнута** (докстринг `BaseInjectionTask.security`; подтверждено
> кодом `TaskSuite.check`, который выполняет ground truth атаки и требует `True`, и эмпирически на
> наших логах: для `injection_task_0` `security=True` ровно в тех кейсах, где письмо атакующему
> реально отправлено). Ранние версии наших скриптов трактовали поле наоборот, поэтому прежние
> опубликованные ASR/Security rate были инвертированы. Ниже — исправленные значения.

| Metric | T0 (no defense) | T1 (tag-only) | Δ |
|--------|------------------|----------------|---|
| **Benign Utility** | 100.0% (10/10) | **100.0%** (10/10) | 0 |
| **Utility Under Attack** | 20.0% (28/140) | **20.0%** (28/140) | 0 |
| **Targeted ASR, direct-achievable subset (primary)** | 48.6% (34/70) | **51.4%** (36/70) | +2.9 п.п. |
| **Targeted ASR, full set (140 cases)** | 24.3% (34/140) | **28.6%** (40/140) | +4.3 п.п. |
| **Security rate, full set** | 75.7% | **71.4%** | −4.3 п.п. |

На 7 недостижимых напрямую целях атака не удалась ни разу ни в T0, ни в T1 (0/70) — full-set ASR
разбавлен «невозможными» целями, поэтому основная метрика считается на direct-achievable subset.

Benign Utility и Utility Under Attack совпадают с T0 **точно** — подтверждает главный критерий приёмки
T1 из `docs/ROADMAP.md`: наблюдательный taint-слой не меняет поведение агента. Разница в ASR
(~3–4 п.п.) объясняется недетерминизмом самой LLM (temperature > 0 при повторном прогоне),
а не действием T1 — gate выключен, T1 физически не может влиять на исход tool calls.

## Taint leakage rate

Доля вызовов privileged tools (`send_email`, `delete_email`, `create_calendar_event`,
`cancel_calendar_event`, `reschedule_calendar_event`, `add_calendar_event_participants`,
`create_file`, `delete_file`, `share_file`, `append_to_file`), куда попал хотя бы один
`untrusted`/`derived_untrusted` аргумент:

| Privileged tool calls (executed) | Tainted | Taint leakage rate |
|---|---|---|
| 549 | 202 | **36.8%** |

Это первая измеримая T1-метрика и прямой вход для проектирования T2 (strict gate заблокировал бы
именно эти 202 вызова, если бы gate уже был включён).

## Известное ограничение, найденное и исправленное в ходе этого прогона

Первая версия `TaintRegistry.find_in_text` сопоставляла только направление «весь зарегистрированный
untrusted span скопирован целиком в новый текст» (`span.text in text`). Реальный паттерн атаки в
workspace suite чаще обратный: модель **извлекает короткую подстроку** (например email-адрес) **из**
большого untrusted-блока (поле `description` с injection payload, размеченное одним span). Такое
извлечение первая версия не ловила вообще — на смоук-тесте `derived_untrusted` метка появилась только
благодаря случайному совпадению с не относящимся к делу коротким span (`"13"`, числовой id, оказавшийся
подстрокой email-адреса).

Исправлено: `find_in_text` теперь проверяет обе директории (`span.text in text` **или**
`text in span.text`), с порогом `MIN_MATCH_LENGTH = 4` символов на обе стороны, чтобы короткие
случайные span'ы не давали ложных срабатываний. Добавлены 2 unit-теста
(`tests/test_taint_registry.py`), обновлён `docs/T1_SPEC.md`. Данные выше (leakage rate 36.8%)
получены **после** этого фикса.

## Notes

- Runner: `scripts/run_eval.py` (не через `agentdojo.scripts.benchmark` — CLI не принимает
  произвольный `BasePipelineElement`, см. `docs/T1_SPEC.md`).
- Новый `PassiveTaintObserver`/pipeline на каждый кейс — предотвращает утечку taint между
  несвязанными user/injection task парами.
- Raw AgentDojo logs: `runs/gpt-4o-mini-2024-07-18-t1-taint/workspace/`.
