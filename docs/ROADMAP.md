# Roadmap проекта: T0-T4

Этот документ фиксирует общий план экспериментов по taint-tracking защите для AgentDojo workspace. Он дополняет текущую спецификацию T1 в `docs/T1_SPEC.md`, baseline-результаты в `results/T0_summary.md` и текст отчёта в `report/progress_report.tex`.

## Текущее состояние

- **T0 baseline завершён**: защита отсутствует, метрики уже измерены на AgentDojo workspace v1.2.2.
- **T1 tag-only taint tracking завершён**: спецификация, core-логика, интеграция в AgentDojo pipeline,
  полный eval (10 benign + 140 security cases) и taint leakage rate измерены. Gate остаётся выключенным.
  Результаты — `results/T1_summary.md`.
- **T2-T4 запланированы** как последовательные ablation-этапы: сначала строгая блокировка, затем более точная field-level политика, затем опциональный rule-based sanitizer.

## T0: baseline без защиты

**Цель:** получить честную точку сравнения для всех последующих treatment-этапов без taint tracking, gate или sanitizer.

**Объём реализации:**

- Запуск стандартного AgentDojo workspace benchmark без дополнительной защиты.
- Сохранение full traces, per-case markdown traces и агрегированных метрик.
- Фиксация модели, suite, attack template и числа security cases для воспроизводимости.

**Ожидаемый эффект на метрики:**

- Benign Utility показывает верхнюю границу полезности агента без защиты.
- Utility Under Attack падает при успешных injection-атаках.
- Security rate отражает только естественные отказы/неуспехи атак без defensive layer.
- Targeted ASR ожидаемо высокий и служит главным baseline для снижения в T2-T4.
- Taint leakage rate не измеряется, так как taint layer отсутствует.

**Критерии готовности:**

- Есть summary с ключевыми метриками.
- Есть raw traces и markdown traces для анализа кейсов.
- Зафиксированы параметры запуска: модель, suite, attack, число user/security задач.

**Когда rerun AgentDojo scoring:**

- При смене модели, версии AgentDojo, attack template, набора задач или benchmark-конфигурации.
- Перед финальным сравнением, если любой последующий treatment запускается в другой среде или с другой моделью.

Статус: **done**. Текущие значения см. в `results/T0_summary.md`.

## T1: tag-only taint tracking

**Цель:** добавить наблюдаемый слой taint tracking, который размечает tool outputs как untrusted, отслеживает derived_untrusted строки и пишет trace evidence без изменения поведения агента.

**Объём реализации:**

- Модель данных для `TaintedSpan`, trust labels, lineage и metadata.
- In-memory `TaintRegistry` для регистрации spans, поиска untrusted фрагментов и derivation.
- `TaintTrace` JSON-журнал для tool outputs и tool calls.
- Пассивная интеграция рядом с AgentDojo `ToolsExecutionLoop`/`ToolsExecutor`.
- Gate полностью выключен: T1 не блокирует, не переписывает и не задерживает tool calls.

**Ожидаемый эффект на метрики:**

- Benign Utility должна остаться примерно на уровне T0.
- Utility Under Attack должна остаться примерно на уровне T0.
- Security rate и Targeted ASR не должны существенно улучшиться, потому что блокировки ещё нет.
- Taint leakage rate впервые становится измеримой: доля privileged/sensitive tool calls, куда попадает `untrusted` или `derived_untrusted` content.

**Критерии готовности:**

- Unit tests покрывают labels, registry, recursive propagation, lineage и JSON serialization.
- Для синтетического сценария виден переход untrusted tool output в аргумент последующего tool call.
- Для AgentDojo run создаются trace-файлы в `results/T1_traces/`.
- Все записанные tool calls имеют `blocked=false`.
- Поведение T0-скриптов и baseline не меняется.

**Когда rerun AgentDojo scoring:**

- После завершения AgentDojo pipeline integration.
- После появления trace writer для всех benchmark cases.
- После исправлений в propagation logic, которые могут изменить taint leakage rate.
- Перед переходом к T2, чтобы получить T1 evidence и убедиться, что tag-only слой не ломает utility.

Статус: **done**. Детальная спецификация находится в `docs/T1_SPEC.md`, результаты — в `results/T1_summary.md`.

## T2: strict gate

**Цель:** включить первую defensive policy: блокировать privileged tool calls, если любой аргумент содержит `untrusted` или `derived_untrusted` content.

**Объём реализации:**

- Классификация privileged tools для workspace suite.
- Gate decision перед выполнением privileged tools.
- Запись решений `allow`/`block` в trace.
- Единый строгий критерий: tainted argument в privileged tool call приводит к block.
- Минимальные объяснения в логах, достаточные для анализа false positives и false negatives.

**Ожидаемый эффект на метрики:**

- Targeted ASR должен заметно снизиться относительно T0/T1.
- Security rate должен вырасти, так как часть атак будет заблокирована gate.
- Benign Utility может снизиться из-за false positives.
- Utility Under Attack может вырасти, если атака блокируется, а основная user task сохраняется; также может падать, если strict gate блокирует нужные benign действия.
- Taint leakage rate до privileged sinks должна снижаться на уровне executed calls, но blocked attempts должны оставаться видимыми в traces.

**Критерии готовности:**

- Есть конфигурация privileged tools и тесты для gate policy.
- Gate блокирует синтетический email-to-privileged-tool leakage.
- Trace явно показывает `blocked=true` и причину block.
- AgentDojo scoring показывает сравнение T2 с T0/T1 по тем же cases.
- Есть список false positives для анализа T3.

**Когда rerun AgentDojo scoring:**

- После каждого изменения списка privileged tools.
- После изменения block policy.
- После исправлений, влияющих на классификацию аргументов или labels.
- Перед проектированием T3, чтобы понять, где strict gate слишком грубый.

Статус: **planned**.

## T3: field-level gate

**Цель:** уменьшить false positives T2 за счёт блокировки не всего privileged tool call по факту taint в любом аргументе, а только опасного taint в sensitive fields.

**Объём реализации:**

- Описание sensitive fields для privileged tools: например recipient, file path, amount, external target, destructive action field.
- Политика gate на уровне `(tool, field)` вместо только `tool`.
- Разделение benign tainted content и управляющих/sensitive параметров.
- Более подробные traces: какое поле вызвало block и почему.

**Ожидаемый эффект на метрики:**

- Benign Utility должна восстановиться относительно T2, если strict gate давал false positives.
- Targeted ASR должен оставаться существенно ниже T0/T1.
- Security rate может немного снизиться относительно T2, если policy стала менее строгой, но должна оставаться выше baseline.
- Utility Under Attack должна улучшиться в кейсах, где можно выполнить user task без опасного действия.
- Taint leakage rate по sensitive fields должна быть низкой; leakage в non-sensitive fields может быть допустимым и учитываться отдельно.

**Критерии готовности:**

- Есть конфигурация sensitive fields для всех релевантных workspace tools.
- Unit tests покрывают allow для tainted non-sensitive fields и block для tainted sensitive fields.
- AgentDojo traces различают blocked sensitive leakage и allowed non-sensitive taint.
- Метрики T3 сравнимы с T0-T2 на одинаковом наборе cases.

**Когда rerun AgentDojo scoring:**

- После каждого изменения sensitive-fields конфигурации.
- После добавления новых privileged tools или изменения их схем.
- После анализа false positives/false negatives из T2.
- Перед финальным выбором основной defense policy для отчёта.

Статус: **planned**.

## T4: rule-based sanitizer (optional)

**Цель:** проверить, можно ли вместо block-only поведения безопасно очищать или нормализовать tainted content в ограниченных сценариях, сохраняя больше utility.

**Объём реализации:**

- Набор простых правил sanitizer: удаление явных instruction-like фраз, redaction подозрительных payloads, нормализация copied text.
- Применение только там, где semantics user task не ломаются и где sanitizer policy явно разрешена.
- Trace до/после sanitizer с указанием применённого правила.
- Conservative fallback: если sanitizer не уверен, gate блокирует или оставляет решение T3 policy.

**Ожидаемый эффект на метрики:**

- Benign Utility и Utility Under Attack могут улучшиться относительно T2/T3, если sanitizer позволяет выполнить полезные действия без опасного payload.
- Targeted ASR должен оставаться низким; рост ASR относительно T3 является сигналом, что sanitizer слишком permissive.
- Security rate может снизиться относительно block-only policy, потому что часть кейсов будет sanitized+allowed, а не blocked.
- Taint leakage rate должна учитывать как raw leakage, так и post-sanitization leakage.

**Критерии готовности:**

- Есть ограниченный список sanitizer rules и тесты на каждый rule.
- Trace сохраняет original tainted value, sanitized value и решение gate.
- Нет silent allow без audit trail.
- AgentDojo scoring показывает, даёт ли sanitizer utility gain без существенного роста Targeted ASR.

**Когда rerun AgentDojo scoring:**

- После каждого изменения sanitizer rules.
- После изменения fallback policy.
- После обнаружения sanitizer bypass в traces.
- Только после стабильного T3, так как T4 является optional extension.

Статус: **optional**.

## Глоссарий метрик

- **Benign Utility** — доля benign user tasks без атаки, которые агент успешно выполнил. Основной индикатор полезности без adversarial давления.
- **Utility Under Attack** — доля security cases, где исходная user task выполнена успешно при наличии injection. Показывает, сохраняется ли полезность в атакуемом сценарии.
- **Security rate** — доля security cases, где атака не достигла цели или была заблокирована. В defensive treatments должна расти относительно T0.
- **Targeted ASR** — targeted attack success rate: доля security cases, где агент выполнил цель атакующего. Главная метрика, которую defense должна снижать.
- **Taint leakage rate** — доля tool calls или sensitive fields, где `untrusted`/`derived_untrusted` content дошёл до потенциально опасного sink. В T1 это observational metric; в T2-T4 она помогает объяснять block/allow решения и residual risk.

## Ближайшие задачи

1. ~~Проверить точную AgentDojo pipeline API в установленной версии и выбрать минимальную точку вставки observer.~~
   Сделано: `BasePipelineElement`/`ToolsExecutor`/`ToolsExecutionLoop` проверены по установленному пакету,
   точка вставки и причина кастомного раннера задокументированы в `docs/T1_SPEC.md` («Точка интеграции с AgentDojo»).
2. ~~Реализовать `ObservingToolsExecutor` в `src/taint/pipeline_element.py` и покрыть unit-тестами без сети.~~
   Сделано: форк `ToolsExecutor`, размечающий сырой (структурированный) tool output до форматирования в
   строку — обоснование в `docs/T1_SPEC.md`. Тесты — `tests/test_pipeline_element.py`.
3. ~~Написать `scripts/run_t1_eval.py` — собственный раннер (стандартный `--defense` в `agentdojo.scripts.benchmark`
   не принимает произвольный `BasePipelineElement`), с новым `PassiveTaintObserver` на каждый кейс.~~
   Сделано.
4. ~~Добавить end-to-end smoke run для одного benign case и одного security case с записью `results/T1_traces/`.~~
   Сделано (2026-07-17). При смоук-тесте найден и исправлен баг в `TaintRegistry.find_in_text` —
   извлечение подстроки из большого untrusted-блока не ловилось (только обратное направление
   сопоставления); см. `docs/T1_SPEC.md`, правило propagation №2, и `results/T1_summary.md`.
5. ~~Запустить полный или согласованный subset T1 scoring и сравнить метрики с T0.~~
   Сделано (2026-07-17): полный прогон, 10 benign + 140 security cases. Benign Utility и Utility Under
   Attack совпадают с T0 точно (100%, 20%) — критерий приёмки T1 выполнен. Таблица — `results/T1_summary.md`.
6. ~~Посчитать и описать taint leakage rate для T1.~~
   Сделано: 202/549 (36.8%) вызовов privileged tools содержат untrusted/derived_untrusted аргумент.
7. На основе T1 traces составить первоначальный список privileged tools и sensitive fields для T2/T3.
   Draft-список privileged tools уже используется в `scripts/run_t1_eval.py::PRIVILEGED_TOOLS` (10 tools);
   осталось формализовать как конфиг T2 и определить sensitive fields по каждому tool (для T3).
8. Обновить прогресс-отчёт (`report/current_progress_update.tex` или новую версию) с результатами T1
   и перейти к проектированию T2 (strict gate).
