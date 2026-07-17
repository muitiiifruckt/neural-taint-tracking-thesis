# План: пре-финальный, следующий и финальный отчёт

Этот документ фиксирует конкретные шаги между прогресс-отчётами. Он дополняет `docs/ROADMAP.md`
(критерии готовности T0–T4) и `report/current_progress_update.tex` (последний написанный отчёт,
датирован 2026-07-07). Составлен 2026-07-15.

**Важно:** весь проект (T0–T3, T4 опционально) должен быть закрыт до августа 2026 — это сильно
сжимает график относительно первоначальной прикидки «~1.5 месяца». Планировать по неделям, не по
двухнедельным блокам.

Статус пунктов обновляй по мере выполнения (`[ ]` → `[x]`), не переписывай историю — если пункт
оказался неактуален, зачеркни/опиши почему, а не удаляй молча.

## Пре-финальный short report (сдан 2026-07-15)

Короткий отчёт «what's done / progress since last stage / plan for next week» с ссылкой на репозиторий
GitHub (`https://github.com/muitiiifruckt/neural-taint-tracking-thesis`). Текст отчёта — см. диалог от
2026-07-15 или `report/` при появлении там письменной версии. Содержание: T0 завершён (метрики ниже),
T1 core реализован (~60–70%), интеграция T1 в live AgentDojo pipeline — главный открытый пункт, план на
следующую неделю — закрыть T1 полностью и спроектировать T2.

## Следующая неделя (ориентир: до ~2026-07-22)

Цель — закрыть T1 полностью и получить первые данные T2, чтобы отчёт показывал не просто «код готов»,
а реальный eval-результат.

- [x] **Интеграция T1 в AgentDojo pipeline.** Готово: `ObservingToolsExecutor`
      (`src/taint/pipeline_element.py`) — форк `ToolsExecutor`, размечающий структурированный tool
      output и call-аргументы через `PassiveTaintObserver` до форматирования в строку (обоснование —
      `docs/T1_SPEC.md`). Покрыто unit-тестами (`tests/test_pipeline_element.py`, реальный
      `FunctionsRuntime`, без сети). Раннер `scripts/run_t1_eval.py` собирает pipeline вручную (новый
      observer на каждый кейс) и подтверждён dry-run'ом (сборка pipeline, `--help`) без реального
      вызова API.
- [x] **Smoke run.** Готово (2026-07-17): 1 benign case + 1 security case, `results/T1_traces/{case_id}.taint.json`
      с корректным lineage. Ключ OpenRouter восстановлен пользователем. В процессе найден и исправлен
      баг в `TaintRegistry.find_in_text` (извлечение подстроки из большого untrusted-блока не ловилось
      алгоритмом сопоставления) — см. `docs/T1_SPEC.md` и `results/T1_summary.md`.
- [x] **Полный (или согласованный subset) T1 eval.** Готово (2026-07-17): полный набор, 10 user tasks ×
      14 injection tasks = 140 security cases + 10 benign. Benign Utility 100.0% и Utility Under Attack
      20.0% — идентичны T0 (критерий приёмки T1 выполнен). Таблица — `results/T1_summary.md`.
- [x] **Taint leakage rate.** Готово: 202/549 (36.8%) вызовов privileged tools содержат
      `untrusted`/`derived_untrusted` аргумент.
- [ ] **Спроектировать T2.** Список privileged tools для workspace suite (черновой список уже есть в
      `scripts/run_t1_eval.py::PRIVILEGED_TOOLS`), strict gate (block, если хоть один аргумент
      untrusted/derived_untrusted), запись `blocked=true/false` + причина в trace.
- [x] **Обновить документацию.** `docs/ROADMAP.md`: статус T1 → done. Таблица T0 vs T1 и leakage rate —
      `results/T1_summary.md`. Осталось: завести T2-спеку по аналогии с `docs/T1_SPEC.md`, обновить
      `report/current_progress_update.tex` числами T1.

**Критерий готовности отчёта:** таблица T0 vs T1 (utility не изменилась) + leakage rate — **выполнено**,
см. `results/T1_summary.md`. Осталось для полноты недели: T2-спека и, если успеет, первые числа T2.

## Финальный отчёт (ориентир: до конца июля / не позднее начала августа 2026)

T4 в `docs/ROADMAP.md` помечен как *optional* — ядро финального отчёта это T0→T3.

- [ ] **T2 доведён до конца.** Полный eval strict gate на всём наборе задач, сравнение T2 vs T0/T1 по
      Targeted ASR, Security rate, Benign Utility, Utility Under Attack. Собрать список false positives
      (заблокированные безобидные действия) как вход для T3.
- [ ] **T3 реализован (field-level gate).** Sensitive fields для privileged tools (recipient, file path,
      amount и т.п.), gate на уровне `(tool, field)` вместо целого tool call. Unit-тесты: allow для
      tainted non-sensitive полей, block для tainted sensitive полей. Eval T3 vs T2.
- [ ] **(Опционально, если останется время) T4 — rule-based sanitizer** поверх block-only policy.
- [ ] **Итоговое сравнение T0–T3(–T4).** Одна таблица/график по всем метрикам, на одинаковой модели и
      наборе cases. Обсудить trade-off Benign Utility vs Targeted ASR по этапам. Основная интерпретация
      ASR — subset «7 из 14 injection tasks, достижимых напрямую» (полные 140 cases как дополнение).
- [ ] **Финальный текст отчёта.** Idea → threat model → результаты по всем этапам → выводы →
      ограничения (символический taint, а не formal noninterference) → что остаётся на возможную
      магистерскую (learned sanitizer, полноценная noninterference-оценка). Обновить README, если
      появятся `src/agent/`, `eval/` из изначального плана кода (см. `report/progress_report.tex`,
      «Planned Code Structure»).

**Критерий готовности:** воспроизводимый прогон T0–T3 на одной модели, таблица сравнения метрик,
зафиксированные false positives/negatives, текст, честно объясняющий выполненное и оставшееся на
будущее.
