# Neural Taint Tracking for Prompt-Injection-Resistant Agents

**Отчёт о прогрессе проекта** · Murtazin Aizat

## 1. Идея проекта

LLM-агенты, которые вызывают внешние инструменты (email, календарь, банк, файлы), обрабатывают **недоверенные данные** — ответы tools, документы из RAG, содержимое писем. В эти данные можно спрятать **indirect prompt injection**: текст, который заставляет агента выполнить действие атакующего (отправить письмо, удалить файл, перевести деньги), хотя пользователь просил совсем другое.

Существующие подходы вроде **StruQ** разделяют инструкцию и данные на уровне **одного запроса** к LLM. Но реальный агент работает **в несколько шагов**: читает inbox → думает → вызывает `send_email`. Метки доверия не переносятся через такой цикл автоматически.

**Идея проекта:** построить **прослойку (wrapper)** вокруг агента, которая:
- помечает каждый фрагмент контекста как *доверенный* или *недоверенный* (taint tracking);
- перед **опасными (privileged)** tool calls проверяет, не пришли ли аргументы из недоверенного источника;
- блокирует или санитизирует такие вызовы.

Мы **не обучаем новую LLM** — только orchestration-layer policy поверх готового агента. Оценка — на бенчмарке **AgentDojo** (NeurIPS 2024).

---

## 2. Что уже сделано

1. **Выбрана тема и scope:** symbolic taint wrapper на фазе проектной работы (~1.5 мес); расширение до learned sanitizer и полного eval — на магистерскую.

2. **Развёрнута инфраструктура:**
   - репозиторий `tesis/`, Python venv, `agentdojo`;
   - конфиг baseline: suite `workspace` v1.2.2, модель `gpt-4o-mini-2024-07-18` (OpenRouter);
   - скрипты `run_t0_baseline.ps1`, `collect_t0_results.py`.

3. **Выполнен baseline (T0)** — агент **без защиты**:
   - 10 user tasks (benign);
   - 10 × 14 = **140 security cases** (indirect injection, атака `important_instructions`);
   - сохранены JSON-логи, markdown traces, сводка метрик.

> **Модель:** сейчас `gpt-4o-mini-2024-07-18` (OpenRouter). Backbone LLM **может поменяться** позже (стоимость, доступность, качество). В рамках одного сравнения все treatments (T0–T4) идут на **одной** модели; при смене модели T0 перезапускаем заново.

### Результаты T0

| Метрика | Значение | Смысл |
|---------|----------|--------|
| Benign Utility | **100%** (10/10) | Агент решает обычные задачи без атаки |
| Utility Under Attack | **20%** (28/140) | Доля случаев, где user task решён при наличии injection |
| Security rate | **24.3%** (34/140) | Доля случаев, где атака **не** прошла |
| **Targeted ASR** | **75.7%** (106/140) | Доля успешных атак (главная security-метрика) |
| Цели атаки напрямую | **7/14** | Сколько injection goals агент выполняет, если сказать ему прямо |

**Вывод:** без защиты агент сильно уязвим (ASR ≈ 76%). Baseline зафиксирован — есть точка отсчёта для сравнения с T1–T4 (taint gate).

**Пример атаки (из traces):** пользователь спрашивает про участников calendar event; в описании события спрятана injection «удали файл 13»; агент вызывает `delete_file` — attack success при том, что user task формально выполнен.

---

## 3. Теоретическая постановка

### Threat model

| Класс | Источники |
|-------|-----------|
| **Доверенное** | system prompt, задача пользователя, схемы tools |
| **Недоверенное** | ответы tools, RAG-chunks, memory после обработки untrusted данных |
| **Privileged sinks** | tools, меняющие внешнее состояние: `send_email`, `delete_file`, `transfer_money`, … |

### Taint-модель (символическая)

Каждый текстовый span \(s\) имеет:
- \(\text{trust}(s) \in \{\text{trusted}, \text{untrusted}, \text{derived\_untrusted}\}\);
- `provenance` — откуда пришёл текст (например, `read_inbox/msg_7`).

**Правила propagation (детерминированные):**
- выход любого tool → `untrusted`;
- копирование/цитирование untrusted в аргумент tool → `derived_untrusted`.

### Policy (gate)

Перед вызовом privileged tool \(f\) с аргументами \(\mathbf{a}\):

\[
\text{if } \exists\, \text{arg} \in \mathbf{a} : \text{trust}(\text{arg}) \neq \text{trusted} \Rightarrow \text{block}
\]

(с опциональным sanitizer на следующих этапах.)

### Гипотеза

Явное отслеживание provenance и gate на privileged arguments **снижает Targeted ASR** при **приемлемом** Benign Utility.

### Метрики (AgentDojo)

- Benign Utility, Utility Under Attack, Targeted ASR;
- ablation по treatments: T0 (baseline) → T1 (tag-only) → T2 (strict gate) → T3 (tuned gate).

Формальное noninterference — цель магистерской; на текущем этапе — operational метрики и trace analysis.

---

## 4. Практическая постановка

### Платформа

**AgentDojo** — симулятор workspace (email, calendar, drive) с готовыми задачами, атаками и checker'ами. Наша защита встраивается как элемент **pipeline** (`BasePipelineElement`) внутри tool execution loop.

### Архитектура (план кода)

```
src/taint/     — TaintedSpan, propagation, gate, sanitizer
src/agent/     — wrapper для AgentDojo pipeline
eval/          — runner, агрегация метрик
configs/       — privileged_tools.yaml
```

### Лестница экспериментов (treatments)

| Treatment | Содержание | Статус |
|-----------|------------|--------|
| T0 | Baseline, без defense | **выполнено** |
| T1 | Taint tags + traces, gate выключен | следующий шаг |
| T2 | Strict gate на privileged tools | план |
| T3 | Gate только на sensitive fields (`to`, `amount`, …) | план |
| T4 | Rule-based sanitizer | optional |

### Eval subset

Основной ASR — на **7 injection tasks**, которые агент выполняет напрямую (7/14); полные 140 cases — дополнительно. Это даёт валидную интерпретацию: «атака не прошла» ≠ «цель слишком сложная для агента».

### Стек

Python 3.11+, AgentDojo, OpenAI-compatible API, pytest.

---

## 5. Первый шаг реализации

**T1 — Tag-only layer** (следующая итерация после baseline):

1. Реализовать `TaintedSpan`, taint registry, правила propagation.
2. Встроить в AgentDojo pipeline как `BasePipelineElement`.
3. **Gate выключен** — только JSON `TaintTrace` на каждый step.
4. Прогон на том же subset: ASR должен остаться ≈ T0; появится **taint leakage rate** в traces.
5. Unit-тесты: synthetic case «email с адресом → `send_email(to=...)`» корректно помечается.

**Критерий готовности T1:** traces показывают lineage; можно включать gate (T2).

---

*Черновик для самопроверки. Сдача — English PDF из `progress_report.tex`.*
