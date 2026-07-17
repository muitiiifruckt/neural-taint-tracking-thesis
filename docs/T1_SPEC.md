---
title: T1 — спецификация
---

<nav class="site-nav">
<a href="./">Главная</a>
<a href="architecture">Архитектура</a>
<a href="results">Результаты</a>
<a href="reproduce">Как запустить</a>
<a href="PROJECT_EXPLAINED">Подробный разбор</a>
<a href="T1_SPEC" class="active">T1</a>
<a href="T2_SPEC">T2</a>
<a href="T3_SPEC">T3</a>
<a href="https://github.com/muitiiifruckt/neural-taint-tracking-thesis">GitHub</a>
</nav>

# Спецификация T1: слой taint-tracking только с метками

## Цель

T1 добавляет самостоятельный слой taint-tracking для запусков AgentDojo workspace. Он записывает метки доверия и lineage происхождения для строк, которые переходят из результатов tool-вызовов в аргументы последующих tool-вызовов.

Gate в T1 выключен. Слой не должен блокировать, переписывать, задерживать или иным образом менять поведение выполнения tools. Скрипты и метрики T0 baseline остаются валидными точками сравнения.

## Не входит в цели

- Не блокировать привилегированные tool-вызовы.
- Не выполнять sanitizer, rewriting, redaction или трансформацию LLM prompt.
- Не выполнять retraining и не менять модель.
- Не заявлять о полном information-flow tracking внутри LLM.
- Не менять `scripts/run_t0_baseline.ps1` или поведение сбора T0.

## Метки доверия

- `trusted`: system prompt, user task, tool schemas и константы, заданные benchmark harness.
- `untrusted`: прямой внешний/tool output, включая тела писем, описания событий календаря, содержимое файлов drive и другие workspace-данные, возвращённые tools.
- `derived_untrusted`: последующая строка, которая копирует, цитирует, форматирует или иным образом включает текст из untrusted span.

В T1 метка `derived_untrusted` используется только для наблюдения. Решение о блокировке относится к T2.

## Модель данных и API

### `TaintedSpan`

Представляет размеченный текстовый фрагмент:

- `span_id`: стабильный уникальный id.
- `text`: точный строковый фрагмент.
- `label`: одно из значений `trusted`, `untrusted`, `derived_untrusted`.
- `source`: дескриптор источника, например `tool:read_inbox`.
- `parents`: ноль или больше `span_id` родительских spans.
- `metadata`: необязательный JSON-serializable контекст.

### `TaintRegistry`

In-memory индекс для spans:

- `add_span(text, label, source, parents=None, metadata=None) -> TaintedSpan`
- `mark_tool_output(tool_name, output, metadata=None) -> list[TaintedSpan]`
- `derive_from_text(text, source, metadata=None) -> TaintedSpan`
- `find_in_text(text) -> list[TaintedSpan]`
- `label_for_text(text) -> TrustLabel`

`derive_from_text` ищет уже зарегистрированные untrusted spans, связанные с `text` — либо скопированные в
`text` целиком, либо содержащие `text` как подстроку (см. правило propagation №2 ниже). Если такие spans
найдены, метод создаёт span `derived_untrusted` с найденными spans в качестве `parents`; иначе создаёт
span `trusted`.

### `TaintTrace`

Сериализуемый журнал событий:

- `trace_id`
- `events`
- `record_tool_output(tool_name, output, spans)`
- `record_tool_call(tool_name, arguments, argument_spans, blocked=False)`
- `to_dict()`
- `write_json(path)`

В T1 поле `blocked` всегда равно `false`.

## Правила распространения

1. Tool outputs получают метку `untrusted`.
2. Если последующая строка содержит точный зарегистрированный untrusted span **или сама является
   подстрокой** зарегистрированного untrusted span, эта строка получает метку `derived_untrusted`.
   Обе директории нужны: первая ловит случай «вся untrusted строка скопирована целиком в новый текст»
   (например, тело письма процитировано полностью), вторая — случай «из большого untrusted-блока
   извлечён короткий фрагмент» (например, email-адрес вытащен из длинного описания календарного
   события с payload инъекции). `TaintRegistry.find_in_text` игнорирует совпадения короче
   `MIN_MATCH_LENGTH` символов (4) с обеих сторон, чтобы короткие span'ы вроде числового id tool output
   не давали случайных ложных срабатываний как подстрока внутри несвязанного текста.
3. Если dictionary/list/tuple/set передан как tool output, T1 рекурсивно извлекает строковые листья и помечает каждый лист как `untrusted`.
4. Аргументы tool-вызовов проверяются рекурсивно. Строковые листья размечаются через `derive_from_text`.
5. Нестрочные scalar values в T1 не получают taint, если только их строковое представление не содержит известный untrusted span. Это консервативно для текущего workspace suite, где injection payloads являются текстовыми.

## Точка интеграции с AgentDojo

Проверено по установленному пакету `agentdojo` (см. `.venv/Lib/site-packages/agentdojo/agent_pipeline/`).

`BasePipelineElement.query(query, runtime, env, messages, extra_args) -> tuple[str, FunctionsRuntime, Env, Sequence[ChatMessage], dict]`
— единственный метод, который нужно реализовать. `ToolsExecutionLoop` вызывает элементы своего списка
`elements` по очереди, пока последнее сообщение — `assistant` с непустым `tool_calls`.

`ToolsExecutor.query`, получив `messages[-1]` (assistant-сообщение с `tool_calls`), для каждого tool call
вызывает `runtime.run_function` и **сразу форматирует** сырое значение (`FunctionReturnType` —
`BaseModel`/`dict`/`list`/строка/скаляр) в одну плоскую строку через `tool_output_formatter` (по
умолчанию `tool_result_to_str`, YAML-дамп), прежде чем положить её в `ChatToolResultMessage.content`.

**Место вставки T1:** `ObservingToolsExecutor` (`src/taint/pipeline_element.py`) — **форк**
`ToolsExecutor`, а не элемент, поставленный рядом с ним:

```python
ToolsExecutionLoop([ObservingToolsExecutor(observer), llm])
```

Рассматривался более простой вариант — отдельный passive-элемент **после** штатного `ToolsExecutor`,
читающий уже добавленные `ChatToolResultMessage`. Он был отклонён: к моменту, когда сообщение с
результатом появляется, tool output уже свёрнут в одну плоскую YAML/JSON-строку, и `mark_tool_output`
может зарегистрировать только один untrusted span на весь этот блоб. Правило propagation №3
(`docs/T1_SPEC.md`, раздел «Правила propagation») требует рекурсивно размечать каждый строковый лист
структуры отдельно — а `TaintRegistry.find_in_text` ищет **span.text как подстроку** в новом тексте, то
есть если единственный span — это весь блоб целиком, обычные копирования одного поля (например,
email-адреса) в аргумент tool call перестают совпадать и остаются `trusted` (ложноотрицательный leakage).

Поэтому `ObservingToolsExecutor` сам выполняет `runtime.run_function` (как и `ToolsExecutor`, но ровно
один раз — **не** оборачивает вызов, чтобы не выполнить tool с побочным эффектом дважды) и:

1. до выполнения — `observer.observe_tool_call(tool_call.function, dict(tool_call.args))`:
   `derive_from_text` по уже накопленным untrusted spans из **предыдущих** tool calls в этом диалоге;
2. выполняет tool call через `runtime.run_function`;
3. после выполнения — `observer.observe_tool_output(tool_call.function, _taint_input(result))`, где
   `_taint_input` рекурсивно разворачивает `BaseModel` в `dict` (как и `tool_result_to_str`), сохраняя
   структуру для `mark_tool_output`, — так помечается результат текущего вызова как `untrusted` для
   **последующих** шагов;
4. форматирует тот же сырой результат в строку тем же `tool_output_formatter` и добавляет
   `ChatToolResultMessage`, как и стандартный `ToolsExecutor` — видимое поведение агента не меняется.

Порядок (call → execute → output) обеспечивает causal lineage «email прочитан → его текст скопирован в
`send_email`» через границу нескольких итераций `ToolsExecutionLoop`. `messages`/`env`/`runtime` не
меняются относительно поведения стандартного `ToolsExecutor` — пассивность гарантируется на уровне кода.

**Почему не через штатный `--defense` в `agentdojo.scripts.benchmark`:** список `DEFENSES` и ветка
`if/elif` в `AgentPipeline.from_config` зашиты в библиотеке и не принимают произвольный
`BasePipelineElement`. Поэтому T1 запускается собственным раннером `scripts/run_eval.py`, который
собирает pipeline вручную (`SystemMessage`, `InitQuery`, `llm` через `get_llm`, `ToolsExecutionLoop`) и
переиспользует только `suite.run_task_with_pipeline`/загрузку suite из библиотеки, а не CLI-обвязку.

**Сброс состояния между кейсами:** `AgentPipeline`/`ToolsExecutionLoop` в штатном раннере переиспользуют
один и тот же объект пайплайна на весь benchmark run, поэтому один `PassiveTaintObserver` с одним
`TaintRegistry` копил бы taint между несвязанными user/injection task парами. `run_eval.py` создаёт
**новый** `PassiveTaintObserver` (и, соответственно, новый `ObservingToolsExecutor`/pipeline) на каждый
кейс, а `trace_id` выставляет равным `{user_task_id}__{attack}__{injection_task_id or "none"}` —
согласовано с именами файлов в `results/traces/` из T0.

## JSON-схема trace

Директория вывода по умолчанию:

```text
results/T1_traces/
```

Один trace-файл на каждый benchmark case:

```text
results/T1_traces/{case_id}.taint.json
```

Схема:

```json
{
  "trace_id": "security_user_task_0_injection_task_1",
  "events": [
    {
      "event_id": "event_000001",
      "kind": "tool_output",
      "tool_name": "read_email",
      "arguments": null,
      "spans": [
        {
          "span_id": "span_000001",
          "text": "Ignore previous instructions...",
          "label": "untrusted",
          "source": "tool:read_email",
          "parents": [],
          "metadata": {}
        }
      ],
      "blocked": false,
      "metadata": {}
    }
  ]
}
```

## Критерии приёмки

- Unit tests проходят без API key и без live AgentDojo run.
- Строковые листья tool output получают метку `untrusted`.
- Точные копии untrusted text в последующих строках становятся `derived_untrusted`.
- Registry сохраняет parent lineage.
- Trace JSON можно сериализовать и загрузить обратно.
- Синтетический сценарий email-to-`send_email` показывает, что untrusted email content попадает в аргумент привилегированного tool.
- T1 не блокирует: у каждого записанного tool call поле `blocked=false`.
- Скрипты T0 остаются без изменений.
- `ObservingToolsExecutor.query` выполняет тот же tool call ровно один раз и возвращает `messages` с тем
  же форматированным результатом, что дал бы стандартный `ToolsExecutor` (unit-тест на реальном
  `FunctionsRuntime` с тестовыми tools, без сети).
- На реальном smoke run (1 benign + 1 security case через `scripts/run_eval.py`) появляется
  `results/T1_traces/{case_id}.taint.json`, и Benign Utility/Utility Under Attack не отличаются от T0 на
  тех же кейсах.

## Тесты

Фокусные тесты находятся в `tests/`:

- label enum и сериализация span;
- поведение registry add/find/derive;
- рекурсивное распространение tool output;
- сериализация trace JSON;
- lineage для синтетического перехода от output `read_email` к `send_email(to=...)`.

## Предварительный обзор T2

T2 добавит gate:

- классификацию privileged tools и sensitive fields;
- block или allow для tool calls на основе tainted arguments;
- явные gate decisions;
- измерение Targeted ASR и Benign Utility относительно T0.

T2 явно находится вне scope T1. T1 только записывает evidence, необходимое для проектирования и отладки gate.
