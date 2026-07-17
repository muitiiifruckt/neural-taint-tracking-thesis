---
title: Как запустить
---

<nav class="site-nav">
<a href="./">Главная</a>
<a href="architecture">Архитектура</a>
<a href="results">Результаты</a>
<a href="reproduce" class="active">Как запустить</a>
<a href="PROJECT_EXPLAINED">Подробный разбор</a>
<a href="T1_SPEC">T1</a>
<a href="T2_SPEC">T2</a>
<a href="T3_SPEC">T3</a>
<a href="https://github.com/muitiiifruckt/neural-taint-tracking-thesis">GitHub</a>
</nav>

# Как запустить

## Установка

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt   # зависимости запинены
copy .env.example .env
# .env: OPENAI_API_KEY=... (и OPENAI_BASE_URL, если доступ через OpenRouter)
```

## Unit-тесты (без API-ключа и сети)

```powershell
.\.venv\Scripts\python -m pytest
```

## T0 baseline

```powershell
.\scripts\run_t0_baseline.ps1
.\.venv\Scripts\python scripts\collect_t0_results.py
```

## T1 / T2 / T3

Собственный раннер — стандартный CLI AgentDojo не принимает произвольный элемент pipeline:

```powershell
.\.venv\Scripts\python scripts\run_eval.py --stage t1
.\.venv\Scripts\python scripts\run_eval.py --stage t2
.\.venv\Scripts\python scripts\run_eval.py --stage t3

# смоук-тест на одном сценарии:
.\.venv\Scripts\python scripts\run_eval.py --stage t2 -ut user_task_0 -it injection_task_0
```

Раннер кэширует per-case результаты через штатный механизм AgentDojo — повторный запуск той же
команды не тратит API-вызовы на уже пройденные сценарии.

## Воспроизводимость

- Модель: `gpt-4o-mini-2024-07-18`.
- Бенчмарк: AgentDojo `0.1.35`, suite `workspace`, `--benchmark-version v1.2.2`, атака
  `important_instructions`.
- Набор задач: `user_task_0..9` (10) × `injection_task_0..13` (14) = 140 security cases + 10
  benign; раннер **проверяет** эти количества на полном прогоне и падает, если что-то не
  сошлось.
- Зависимости запинены в `requirements.txt`.

## Что где лежит

| Путь | Содержимое |
|---|---|
| `src/taint/` | Ядро: модели spans, registry, propagation, trace, gate-политика |
| `src/agent/` | Обёртка над AgentDojo pipeline и общая арифметика метрик |
| `scripts/run_eval.py` | Раннер T1/T2/T3 |
| `scripts/collect_t0_results.py` | Агрегация T0 baseline |
| `tests/` | 29 unit-тестов, без сети |
| `results/` | Сводки по этапам + per-case трейсы (`.taint.json`) |
| `docs/` | Технические спецификации каждого этапа |
