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
- [x] **Спроектировать и реализовать T2 (и заодно T3).** Готово (2026-07-17):
      `src/taint/policy.py` (`PRIVILEGED_TOOLS` + `SENSITIVE_FIELDS`), `GatingToolsExecutor`
      (strict/field), тесты, спеки `docs/T2_SPEC.md`/`docs/T3_SPEC.md`, раннер
      `scripts/run_eval.py --stage t2|t3`. Полный eval заблокирован: API снова 403 (2026-07-17).
- [x] **Обновить документацию.** Готово: `docs/ROADMAP.md` (T1 done, T2/T3 implemented),
      T2/T3-спеки, README переписан (рефрейминг + воспроизводимость), отчёт
      `report/progress_update_2026-07-17.md` обновлён под фидбек рецензента.

**Дополнение по фидбеку рецензента (получен 2026-07-17):** проект переименован в «symbolic
provenance-gated defense», фокус T1–T3, основная метрика — targeted ASR на direct-achievable
subset (7 задач), добавлен overblock rate; T0-репортинг разделён на 3 оценки (10 benign user
tasks / 14 direct-goal runs / 140 security cases); главная причина недозачёта прошлой сдачи —
незапушенный код — устранена (всё в origin/master).

**Критерий готовности отчёта:** таблица T0 vs T1 + leakage rate — **выполнено**. Для сильного
результата осталось: прогнать T2/T3 eval (нужен рабочий API-ключ) и собрать таблицу T0–T3.

## Пре-финальный отчёт (написан 2026-07-17)

`report/prefinal_report.tex` → `prefinal_report.pdf` (4 стр., LaTeX). Содержит полное сравнение
T0–T3, ответ на research question, разбор false positives и остаточных атак, статус по плану и
план на финальный отчёт. Собирается `pdflatex prefinal_report.tex` (TinyTeX).

## Финальный отчёт (ориентир: до конца июля / не позднее начала августа 2026)

T4 в `docs/ROADMAP.md` помечен как *optional* — ядро финального отчёта это T0→T3.
**Вся техническая работа T0–T3 закрыта** (см. ниже); осталась только письменная часть и,
опционально, T4.

- [x] **T2 доведён до конца.** Полный eval strict gate выполнен: subset ASR 11.4% (T0: 48.6%),
      full 5.7%, Benign Utility 80% (overblock 20%, 2 кейса), UUA 34.3%, 579 blocked calls.
      False positives собраны (оба — поле `participants`). `results/T2_summary.md`.
- [x] **T3 доведён до конца.** Полный eval field-gate выполнен: subset ASR 8.6%, full 4.3%,
      Benign Utility 80% (те же 2 false positive). Ответ на research question: field-gate НЕ
      восстанавливает utility относительно strict. `results/T3_summary.md`.
- [ ] **(Опционально, если останется время) T4 — rule-based sanitizer** поверх block-only policy.
- [x] **Итоговое сравнение T0–T3.** Таблица собрана в `report/prefinal_report.tex`, README,
      `report/progress_update_2026-07-17.md` и на сайте (`docs/results.md`). Основная метрика —
      subset ASR (7 из 14 задач), full ASR как вторичная.
- [ ] **Финальный текст отчёта.** Idea → threat model → результаты по всем этапам → выводы →
      ограничения (символический taint, а не formal noninterference; порог MIN_MATCH_LENGTH;
      false positives на routing-полях) → future work. Каркас и всё содержание уже есть в
      пре-финальном отчёте и на сайте — осталась консолидация в финальный документ.

**Критерий готовности:** воспроизводимый прогон T0–T3 на одной модели, таблица сравнения метрик,
зафиксированные false positives/negatives, текст, честно объясняющий выполненное и оставшееся на
будущее — **всё, кроме финального сводного текста, готово**.
