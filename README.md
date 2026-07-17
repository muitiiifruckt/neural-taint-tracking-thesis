# Symbolic Provenance-Gated Defense against Indirect Prompt Injection

Курсовой исследовательский проект: поэтапная (T0–T3) защита tool-using LLM-агента от
indirect prompt injection на бенчмарке **AgentDojo** (`workspace` suite). Защита строится на
символьном (substring-based) отслеживании происхождения данных (taint/provenance tracking) и
gate-политике перед privileged tool calls — без обучения моделей и без formal
noninterference-претензий.

**Исследовательский вопрос:** снижает ли field-sensitive provenance gating (T3) targeted
ASR, сохраняя benign utility лучше, чем строгий gate (T2)?

## Этапы

| Этап | Защита | Спецификация |
|---|---|---|
| T0 | нет (baseline) | `results/T0_summary.md` |
| T1 | tag-only taint tracking, gate выключен | `docs/T1_SPEC.md` |
| T2 | strict gate: блок privileged call при любом tainted-аргументе | `docs/T2_SPEC.md` |
| T3 | field-sensitive gate: блок только tainted sensitive полей | `docs/T3_SPEC.md` |

План и критерии готовности всех этапов — `docs/ROADMAP.md`.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt   # зависимости запинены
copy .env.example .env
# .env: OPENAI_API_KEY=... (и OPENAI_BASE_URL при доступе через OpenRouter)
```

## Запуск

Unit-тесты (без API-ключа и сети):

```powershell
.\.venv\Scripts\python -m pytest
```

T0 baseline (стандартный AgentDojo benchmark + агрегация):

```powershell
.\scripts\run_t0_baseline.ps1
.\.venv\Scripts\python scripts\collect_t0_results.py
```

T1/T2/T3 (собственный раннер — AgentDojo CLI не принимает кастомный pipeline element):

```powershell
.\.venv\Scripts\python scripts\run_eval.py --stage t1
.\.venv\Scripts\python scripts\run_eval.py --stage t2
.\.venv\Scripts\python scripts\run_eval.py --stage t3
# смоук: добавить -ut user_task_0 -it injection_task_0
```

## Воспроизводимость

- Модель: `gpt-4o-mini-2024-07-18` (через OpenRouter, `OPENAI_BASE_URL` в `.env`).
- Benchmark: AgentDojo `0.1.35`, suite `workspace`, `--benchmark-version v1.2.2`,
  атака `important_instructions`.
- Набор задач: `user_task_0..user_task_9` (10) × `injection_task_0..injection_task_13` (14)
  = 140 security cases + 10 benign; раннер **assert'ит** эти количества на полном прогоне.
- Основная security-метрика — targeted ASR на **direct-achievable subset**: 7 injection
  tasks (`0,1,2,4,5,10,13`), чьи цели агент выполняет по прямой просьбе (измерено в T0);
  full-set ASR приводится как вторичная метрика.
- Зависимости запинены в `requirements.txt`.

## Outputs

| Path | Content |
|------|---------|
| `runs/{pipeline}/workspace/...` | Сырые AgentDojo JSON-логи (messages, utility, security) |
| `results/T{n}_summary.{md,json}` | Метрики этапа (JSON содержит per-case детали) |
| `results/T{n}_traces/*.taint.json` | Taint/gate traces: spans, lineage, blocked + причина |
| `results/traces/*.md` | Human-readable трейсы T0 |

## Метрики

- **Benign Utility** — % выполненных user tasks без атаки (10 задач).
- **Utility Under Attack** — % security cases с выполненной user task.
- **Targeted ASR (direct-achievable)** — основная: % успешных атак на 70 кейсах subset.
- **Targeted ASR (full)** — вторичная: % успешных атак на всех 140 кейсах.
- **Taint leakage rate** — % выполненных privileged calls с tainted-аргументом (T1+).
- **Overblock rate** — % benign user tasks, где gate заблокировал ≥1 вызов (T2+).

## Структура кода

- `src/taint/` — ядро: модели spans, registry, propagation, trace, политика gate
  (`policy.py`), интеграция с AgentDojo pipeline (`pipeline_element.py`).
- `scripts/run_eval.py` — раннер T1/T2/T3; `scripts/collect_t0_results.py` — агрегация T0.
- `tests/` — unit-тесты taint propagation, gate policy, gated executor, интеграции.
- `docs/` — спецификации этапов, roadmap, план отчётов.
- `report/` — тексты прогресс-отчётов.
