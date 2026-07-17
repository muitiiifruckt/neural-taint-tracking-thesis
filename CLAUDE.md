# CLAUDE.md

Этот файл даёт указания Claude Code (claude.ai/code) при работе с кодом в этом репозитории.

## Обзор проекта

Это учебный исследовательский проект («Neural Taint Tracking»), в рамках которого строится поэтапная
(T0–T4) защита LLM-агентов от prompt-injection атак, измеряемая на бенчмарк-сьюте AgentDojo `workspace`. Каждый
этап — это ablation-шаг: T0 — baseline без защиты, T1 добавляет наблюдательный (не блокирующий) слой
taint-tracking, T2–T4 (запланированы) постепенно добавляют блокирующие/gating политики. Полный
экспериментальный план, ожидаемый эффект на метрики и критерии готовности каждого этапа находятся в
`docs/ROADMAP.md` — читай его перед началом работы над любым этапом Tx. `docs/T1_SPEC.md` — детальная,
на данный момент актуальная спецификация T1. `docs/REPORT_PLAN.md` — конкретный чек-лист задач до
следующего и до финального прогресс-отчёта; сверяйся с ним, когда просят «продолжить по плану».

## Установка

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
copy .env.example .env
# отредактируй .env: укажи OPENAI_API_KEY=sk-...
```

## Частые команды

Запустить все unit-тесты (не требуют API-ключа или live-запуска AgentDojo):

```powershell
.\.venv\Scripts\python -m pytest
```

Запустить один тестовый файл или один тест:

```powershell
.\.venv\Scripts\python -m pytest tests\test_taint_registry.py
.\.venv\Scripts\python -m pytest tests\test_taint_registry.py::test_name -v
```

Запустить T0 baseline-бенчмарк (10 user tasks × 14 injection tasks = 140 security cases; требует `.env` с
`OPENAI_API_KEY` или ключом OpenRouter, обращается к внешнему API):

```powershell
.\scripts\run_t0_baseline.ps1
```

Smoke-тест всего на 2 задачах вместо полного T0-прогона:

```powershell
.\.venv\Scripts\python -m agentdojo.scripts.benchmark -s workspace --benchmark-version v1.2.2 --model GPT_4O_MINI_2024_07_18 --logdir ./runs -ut user_task_0 -ut user_task_1
.\.venv\Scripts\python -m agentdojo.scripts.benchmark -s workspace --benchmark-version v1.2.2 --model GPT_4O_MINI_2024_07_18 --attack important_instructions --logdir ./runs -ut user_task_0 -ut user_task_1
.\.venv\Scripts\python scripts\collect_t0_results.py
```

`collect_t0_results.py` читает сырые JSON-логи AgentDojo из `runs/{pipeline}/workspace/...` и пишет
`results/T0_summary.md`, `results/T0_summary.json`, `results/T0_full_traces.json`, а также per-case
markdown-трейсы в `results/traces/`. Скрипт всегда берёт самую недавно изменённую директорию pipeline
внутри `runs/` и жёстко зашивает имя атаки `important_instructions` как «security»-прогон — учитывай это,
если появится новый attack template.

## Архитектура

### `src/taint/` — ядро T1 taint-tracking

Это лёгкий по зависимостям Python-код без AgentDojo или сетевых зависимостей, поэтому он полностью
тестируется в изоляции:

- `models.py` — enum `TrustLabel` (`trusted` / `untrusted` / `derived_untrusted`) и frozen-датакласс
  `TaintedSpan` (размеченный текстовый фрагмент с lineage `parents` и JSON-сериализуемыми `metadata`).
- `registry.py` — `TaintRegistry`, in-memory хранилище spans. `mark_tool_output` рекурсивно обходит
  tool output (dict/list/tuple/set/str) через `iter_string_leaves` и помечает каждый строковый лист как
  `untrusted`. `derive_from_text` заново сканирует новую строку на предмет уже зарегистрированных
  untrusted-подстрок и, если находит совпадения, создаёт span `derived_untrusted`, чьи `parents`
  указывают на найденные spans — так фиксируется lineage (например, «тело письма скопировано в
  аргумент `send_email`»).
- `propagation.py` — тонкие обёртки (`record_tool_output`, `derive_argument_spans`), которые вызывают
  registry для двух событий propagation, важных для T1: получение tool output и построение аргументов
  tool call.
- `trace.py` — `TaintTrace`/`TaintEvent`, append-only, JSON-сериализуемый журнал событий
  (`record_tool_output`, `record_tool_call`), записываемый в
  `results/T1_traces/{case_id}.taint.json`. Поле `blocked` в T1 всегда `false` — ни один этап до T2 не
  имеет права менять поведение агента.
- `agentdojo_hook.py` — `PassiveTaintObserver`, состояние одного кейса (registry + trace).
- `pipeline_element.py` — `ObservingToolsExecutor` (форк `ToolsExecutor` AgentDojo, наблюдение без
  блокировки — T1) и `GatingToolsExecutor` (наследник с gate: `mode="strict"` — T2, `mode="field"` —
  T3). Интегрированы в живой AgentDojo pipeline через `scripts/run_eval.py --stage t1|t2|t3`.
- `policy.py` — `PRIVILEGED_TOOLS` (10 workspace tools), `SENSITIVE_FIELDS` (по-инструментные
  чувствительные поля), `gate_decision()`.

### Правила propagation (T1, полная спецификация — `docs/T1_SPEC.md`)

1. Каждый строковый лист tool output → `untrusted`.
2. Строка-аргумент tool call, точно содержащая текст зарегистрированного untrusted span → `derived_untrusted`,
   с этим span в качестве parent.
3. Вложенные контейнеры (dict/list/tuple/set) обходятся рекурсивно; нестроковые scalar-значения не
   получают taint, если их строковое представление не содержит известный untrusted span.
4. T1 никогда не блокирует, не переписывает и не задерживает вызовы — gating появляется только с T2.

### Поток данных при прогоне бенчмарка

`scripts/run_t0_baseline.ps1` вызывает `agentdojo.scripts.benchmark` (установленный pip-пакет, не часть
этого репозитория) дважды — один раз без `--attack` (benign utility) и один раз с
`--attack important_instructions` (security/ASR) — против сьюта `workspace` на
`--benchmark-version v1.2.2`. Сырые per-case JSON попадают в
`runs/{pipeline}/workspace/{user_task}/{attack}/{injection_task}.json`.
`scripts/collect_t0_results.py` агрегирует их в директорию `results/`. `configs/baseline.yaml` фиксирует
параметры T0-прогона (модель, suite, attack, список задач) для документации, но ни один скрипт его не
читает — это запись, а не живой конфиг.

### Метрики (полные определения — глоссарий в `docs/ROADMAP.md`)

- **Benign Utility** — % user tasks, успешно выполненных без атаки.
- **Utility Under Attack** — % security cases, где user task всё равно выполнена успешно несмотря на injection.
- **Targeted ASR** — % security cases, где цель атаки достигнута; главная метрика, которую последующие
  этапы должны снижать. Основная интерпретация — на direct-achievable subset (7 задач, 70 cases).
- **Security rate** — `100% − Targeted ASR`.
- **Taint leakage rate** — (с T1) % привилегированных/sensitive tool calls, куда попадает
  `untrusted`/`derived_untrusted` контент; наблюдательная метрика до появления gating в T2.

**Семантика сырого поля `security` в логах AgentDojo:** `True` = цель инъекции достигнута (атака
удалась). Это подтверждено докстрингом `BaseInjectionTask.security`, кодом `TaskSuite.check`
(выполняет ground truth атаки и требует `True`) и эмпирически на логах T0. ASR = доля кейсов с
`security=True`; НЕ инвертировать. До 2026-07-17 скрипты агрегации трактовали поле наоборот, поэтому
числа в старых отчётах (`report/*.tex`, ASR 75.7%) инвертированы относительно истинных.

### Threat model (из отчёта)

- **Доверенное**: system prompt, задача пользователя, схемы tools.
- **Недоверенное**: ответы tools, RAG-chunks, любые данные, производные от untrusted источников.
- **Privileged sinks**: tools, меняющие внешнее состояние — `send_email`, `delete_file`,
  `transfer_money` и т.п. Именно перед их вызовом должен будет срабатывать gate в T2+.
- Итоговая gate-политика (T2, план): если хотя бы один аргумент privileged tool имеет
  `trust(arg) != trusted` → блокировать вызов (с опциональным sanitizer в T4).

### Текущий статус и результаты (по состоянию на отчёты в `report/`)

Проект задуман как курсовая/проектная работа (~1.5 месяца), с возможным расширением до магистерской
(learned sanitizer, полная noninterference-оценка) — это не зафиксировано, а лишь обозначено как
направление на будущее.

Результаты T0 baseline (модель `gpt-4o-mini-2024-07-18` через OpenRouter, suite `workspace` v1.2.2,
атака `important_instructions`, 10 user tasks, 140 security cases):

| Метрика | Значение (исправленная семантика, 2026-07-17) |
|---|---|
| Benign Utility | 100% (10/10) |
| Utility Under Attack | 20.0% (28/140) |
| **Targeted ASR, direct-achievable subset (primary)** | **48.6% (34/70)** |
| Targeted ASR, full set | 24.3% (34/140) |
| Security rate, full set | 75.7% |
| Injection goals, достижимые напрямую | 7/14 |

Вывод: без защиты агент полностью справляется с benign-задачами, а на целях, которые ему по силам,
успешна почти каждая вторая инъекция (subset ASR ≈ 49%) — это референсная точка для T1–T4. Full-set
ASR (24.3%) разбавлен 7 недостижимыми целями: на них атака не удалась ни разу (0/70), поэтому основная
метрика — subset. Старые отчёты (`report/*.tex`) содержат инвертированные значения (75.7%) из-за
неправильной трактовки поля `security` — см. раздел «Метрики».

Статус на 2026-07-17: T1 завершён полностью (интеграция + полный eval на 150 кейсах, utility
идентична T0, leakage 36.8%, трейсы в `results/T1_traces/`); T2 (strict gate) и T3 (field-sensitive
gate) реализованы и покрыты тестами, идут полные eval-прогоны. По фидбеку рецензента проект
переименован в «symbolic provenance-gated defense» (не «neural taint tracking»), фокус — T1–T3,
research question: снижает ли field-sensitive gating ASR, сохраняя utility лучше strict gate.
Актуальный отчёт — `report/progress_update_2026-07-17.md`.

### `report/`

Содержит текст прогресс-отчётов и историю рассуждений о проекте — полезный источник контекста о
целях, threat model и текущем статусе (см. выше), но не источник истины о состоянии кода. Актуальный,
самый свежий отчёт — `current_progress_update.tex`/`.pdf` (англ., датирован 7 июля 2026, содержит ссылку
на GitHub-репозиторий и оценку прогресса); `progress_report.tex` — более ранняя версия того же отчёта;
`progress_ru.md` — черновик на русском для самопроверки, по которому позже готовился английский
`progress_report.tex`. Собирается через `report/Makefile`. Обновляй актуальный `.tex`-отчёт, когда
завершается интеграция/eval очередного этапа Tx — см. «ближайшие задачи» в `docs/ROADMAP.md`.
