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

`derive_from_text` ищет уже зарегистрированные untrusted spans, скопированные в `text`. Если такие spans найдены, метод создаёт span `derived_untrusted` с найденными spans в качестве `parents`; иначе создаёт span `trusted`.

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
2. Если последующая строка содержит точный зарегистрированный untrusted span, эта строка получает метку `derived_untrusted`.
3. Если dictionary/list/tuple/set передан как tool output, T1 рекурсивно извлекает строковые листья и помечает каждый лист как `untrusted`.
4. Аргументы tool-вызовов проверяются рекурсивно. Строковые листья размечаются через `derive_from_text`.
5. Нестрочные scalar values в T1 не получают taint, если только их строковое представление не содержит известный untrusted span. Это консервативно для текущего workspace suite, где injection payloads являются текстовыми.

## Точка интеграции с AgentDojo

Pipelines AgentDojo строятся из элементов `BasePipelineElement`. Выполнение tools происходит внутри `ToolsExecutionLoop`, обычно через `ToolsExecutor`.

T1 должен быть добавлен рядом с выполнением tools как пассивный observer:

1. после получения tool outputs вызвать `record_tool_output`;
2. перед выполнением следующего tool call вызвать `record_tool_call`;
3. вернуть исходные pipeline data без изменений.

Лёгкий skeleton находится в `src/taint/agentdojo_hook.py`. Он намеренно не меняет benchmark configuration, пока точная сигнатура метода AgentDojo `BasePipelineElement` не будет проверена по установленному пакету. TODO для интеграции: создать subclass `agentdojo.agent_pipeline.BasePipelineElement` и разместить observer вокруг `ToolsExecutor` внутри workspace benchmark pipeline.

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
