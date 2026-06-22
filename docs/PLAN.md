# PLAN - План работ

## Фаза 0. Подготовка окружения 
- [x] Анализ задания (`Примеры.pdf`, методички по аутентификации/профилям/авторизации).
- [x] Выбор модели: Qwen2.5-Coder-7B-Instruct-4bit (SQL-генерация, влезает в 24 GB QLoRA).
- [x] Python 3.13 venv (3.14 без MLX-wheels), установка mlx-lm.

## Фаза 1. Датасет обучения 
- [x] Генератор вариантов `scripts/generate_dataset.py`:
 13 параметров профиля, диапазоны значений, перефразировки русских формулировок.
- [x] 3 официальных варианта зашиты явно и продублированы (гарантия выучивания).
- [x] 1000 примеров: train 850 / valid 100 / test 50 + gold 3.

## Фаза 2. Дообучение policy (QLoRA) 
- [x] Конфиг `lora_config.yaml` (rank 16, 8 слоёв, mask_prompt, grad_checkpoint).
- [x] Обучение: train loss сошёлся к ~0.002 за ~40 итераций (формат регулярный).
- [x] Адаптер `adapters/adapters.safetensors`.

## Фаза 3. Развёртывание СУБД 
- [x] `docker/docker-compose.yml` - Oracle Free 23ai (ARM64).
- [x] Seed `docker/init/01_seed.sql`: схема CTF, `CTF_FLAG`, `credentials`,
 заблокированный `compromised_user`, привилегированный `dba_ctf`.
- [x] Проверка соединения и seed-данных.

## Фаза 4. Агент + фиксация траекторий 
- [x] `agent/config.py` - параметры (env-driven).
- [x] `agent/oracle_tool.py` - `execute_sql`, `read_flag`, `reset_state`.
- [x] `agent/llm.py` - policy на дообученной модели (+sampling для вариативности).
- [x] `agent/tracing.py` - OpenInference spans (AGENT/LLM/TOOL) -> `ep_*.json`.
- [x] `agent/agent.py` - ReAct-цикл с коррекцией по ошибкам СУБД.
- [x] Smoke-тест: 3 официальных варианта решены, флаг получен.

## Фаза 5. Сбор траекторий 
- [x] one-shot: `run_collection.py --n 1010` -> 1010 траекторий (1009 ok / 1 fail).
- [x] deep ReAct: `--mode react --n 500 --inject-fail-rate 0.4` -> 500 (425 ok / 75 fail).
- [x] Итого **1510 траекторий** в `trajectories/` (вкл. 76 неудачных).

## Фаза 6. Верификация, тесты, отчёт 
- [x] `scripts/verify.py` - ВСЕ проверки ТЗ пройдены (кол-во, валидность, провалы, эталоны).
- [x] `scripts/export_openinference.py` - strict OTLP (22502 span'а); Phoenix ingestion ОК.
- [x] `tests/` - 16 тестов (компонентные + интеграционные), pytest-cov.
- [x] Held-out eval (50) + устойчивость (100 novel) + 3 рукописные live.
- [x] Демо-ассеты: `demo.py`, `pick_showcase.py`, `verify_phoenix.py`, `finalize.sh`.
- [x] `REPORT.md` финализирован.

## Фаза 7. Усиление робастности (v2) 
- [x] Тесты вскрыли переобучение v1 на формулировки (novel 19%, live 0/3).
- [x] `phrasings_aug.py` - обогащение трейна стилями/синонимами.
- [x] Переобучен v2; v1 в `adapters_v1_backup`.
- [x] v2: novel 19->30%, значения 70->96%, live 0/3->2/3; PDF-стиль 100% (без регресса).

## Риски / решения
| Риск | Решение |
|------|---------|
| Python 3.14 без MLX | venv на 3.13 |
| Зависание загрузки модели с HF | `hf_transfer` + resume |
| Oracle на ARM | образ `gvenzl/oracle-free` (поддержка arm64) |
| Нет провалов в траекториях | deep-режим + инъекция конфликтов БД + temp 0.6 |
| Переобучение v1 на формулировки (novel 19%) | обогащение трейна -> v2 (novel 30%, значения 96%) |
| Остаточный пропуск шагов на диких фразах | приемлемо: экзамен в стиле PDF (v2 = 100%) |
