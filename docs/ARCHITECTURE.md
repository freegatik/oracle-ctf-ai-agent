# Архитектура: интеллектуальный агент решения Oracle CTF

## Назначение

Программный модуль - **интеллектуальный агент**, который решает CTF-задания по
администрированию Oracle Database, **взаимодействуя с реальной СУБД** (Oracle Free
23ai в Docker), и **фиксирует траектории** своей работы в стандарте **OpenInference**
(семантические конвенции поверх OpenTelemetry). По итогам прогона тестов
собирается файл-набор из **≥1000 траекторий, включая неудачные попытки**.

## Соответствие ТЗ

| Требование ТЗ | Реализация |
|---------------|-----------|
| Агент (или дообученная модель) | дообученная Qwen2.5-Coder-7B (QLoRA) как policy + ReAct-обёртка |
| Модуль фиксации траектории | `agent/tracing.py` - OpenTelemetry spans + OpenInference атрибуты |
| Стандарт OpenInference | span.kind = AGENT/LLM/TOOL, атрибуты `llm.*`, `tool.*`, `input/output.value` |
| Интеграция с СУБД | `agent/oracle_tool.py` через `python-oracledb` -> Oracle Free 23ai |
| Настройка параметров | `agent/config.py` (env-driven) |
| Тестирование компонентов | `tests/` + smoke-прогоны |
| Верификация по ТЗ | `scripts/verify.py` - проверка флага и обязательных шагов |
| ≥1000 траекторий, вкл. неудачные | `scripts/run_collection.py` -> `trajectories/ep_*.json` |

## Компоненты

```
┌──────────────────────────────────────────────────────────────┐
│ scripts/run_collection.py │
│ цикл по N вариантам задания -> запуск агента -> сбор траекторий │
└───────────────┬──────────────────────────────────────────────┘
 │
 ┌───────▼────────┐ OpenInference spans
 │ agent/agent.py │──────────────────────────┐
 │ ReAct-цикл │ ▼
 │ │ ┌──────────────────┐
 │ think->act->obs │ │ agent/tracing.py │
 └───┬─────────┬───┘ │ OTel + экспортер │
 │ │ │ -> ep_*.json │
 ┌────────▼───┐ ┌──▼─────────────┐ └──────────────────┘
 │ agent/llm │ │ agent/oracle_ │
 │ (mlx Qwen) │ │ tool (oracledb)│
 │ дообученная│ │ execute_sql │
 └────────────┘ └───────┬────────┘
 │
 ┌────────▼─────────┐
 │ Oracle Free 23ai │ (docker/docker-compose.yml)
 │ seed: CTF_FLAG, │
 │ credentials, │
 │ compromised_user│
 └──────────────────┘
```

### agent/llm.py - policy (мозг)
Дообученная QLoRA-модель Qwen2.5-Coder-7B. На вход - задание (+ контекст ошибок при
коррекции), на выход - SQL. Загружается один раз, переиспользуется для всех прогонов.

### agent/oracle_tool.py - инструмент SQL
Единственный tool агента: `execute_sql(stmt)`. Выполняет оператор в Oracle, возвращает
строки/код результата/ошибку ORA-. Управляет соединениями (admin + проверка под CTF_STUDENT).
Содержит `reset_state()` - очистка объектов между траекториями (DROP USER/ROLE/PROFILE/TABLESPACE).

### agent/agent.py - ReAct-цикл
1. **LLM**: задание -> полный SQL-скрипт решения.
2. Разбор на операторы.
3. По каждому: **TOOL** `execute_sql` -> наблюдение (успех/ORA-ошибка).
4. При ошибке: **LLM** (промпт с текстом ошибки) -> исправление, повтор (лимит попыток).
5. Финал: `SELECT` из `CTF.CTF_FLAG` под CTF_STUDENT с активацией роли -> проверка флага.
6. Весь прогон = одна траектория (root span), статус success/failure.

### agent/react_agent.py - «глубокий» режим (deep)
Расширение one-shot: строит план (CHAIN-span), выполняет пооператорно с рефлексией
ошибок (`reflect_error`), при включённой инъекции конфликтов БД (`inject_conflict`)
ловит реальные ORA-ошибки -> восстанавливается. Даёт богатые многоходовые трейсы и
естественные неудачи (требование ТЗ «включая неудачные»).

### scripts/export_openinference.py - strict OTLP-экспорт
Конвертирует `ep_*.json` в каноничный OpenTelemetry/OTLP JSON (`openinference_otlp.json`),
принимаемый Arize Phoenix и любым OTel-бэкендом. Закрывает букву стандарта OpenInference.

### scripts/phrasings_aug.py - обогащение формулировок (робастность)
Широкий пул синонимов/стилей для трейна -> модель учит маппинг «смысл->параметр», а не
зубрит фразу. Использовано для дообучения v2 (novel-обобщение 19->30%, значения 70->96%).

### agent/tracing.py - фиксация траекторий (OpenInference)
- root span `kind=AGENT` на задачу;
- дочерние `kind=LLM` (атрибуты `llm.input_messages`, `llm.output_messages`, `llm.model_name`);
- дочерние `kind=TOOL` (`tool.name=execute_sql`, `input.value`=SQL, `output.value`=результат/ошибка);
- по завершении траектории все её spans сериализуются в `trajectories/ep_NNNNN.json`
 (формат: список span'ов с OpenInference-атрибутами + метаданные success/variant).
- неудачные траектории сохраняются так же (ТЗ требует включать провалы).

## Поток данных одной траектории

```
task(text)
 └─AGENT span ep_00042 (variant=2, success=?)
 ├─LLM span in: task out: SQL script
 ├─TOOL span in: ALTER USER... out: OK
 ├─TOOL span in: CREATE TABLESPACE... out: ORA-01543 (already exists)
 ├─LLM span in: error+stmt out: исправленный SQL
 ├─TOOL span in: DROP+CREATE... out: OK
 ├─ ...
 └─TOOL span in: SELECT ... CTF_FLAG out: FLAG{...} -> success=true
```

## Параметры (agent/config.py)
- `ORACLE_DSN`, `ORACLE_ADMIN_USER/PASSWORD`
- `MODEL`, `ADAPTER` - база + LoRA-адаптер
- `MAX_FIX_ATTEMPTS` - лимит коррекций на оператор
- `TRAJ_DIR` - куда писать ep_*.json
- `N_TRAJECTORIES` - сколько собрать (≥1000)

## Развёртывание
1. `docker compose -f docker/docker-compose.yml up -d` - Oracle + seed.
2. `python scripts/run_collection.py --n 1000` - сбор траекторий.
3. `python scripts/verify.py` - верификация.
