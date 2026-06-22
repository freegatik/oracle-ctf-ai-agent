# CHANGELOG

Все значимые изменения проекта. Формат - по датам.

## [0.7.0] - 2026-06-12 - Гибкое подключение и реальная эскалация
- `agent/oracle_tool.py`: `_open_admin()` - прямой вход админом, при неудаче
 эскалация через bootstrap-аккаунт (вход -> чтение credentials -> переподключение).
- `read_flag`: настраиваемые объекты (flag_object, student/role) + устойчивый поиск
 ячейки FLAG{...} через SELECT * (имя колонки не важно).
- `agent/config.py`: env-параметры bootstrap_user/password, credentials_table,
 flag_object, student_user/password, role_name/password.
- Системный промпт расширен до полной шпаргалки (8 шагов + маппинг) - дообуч+полный = 100%.
- Стресс-тест live: 41/42 (97%) реальных флагов (эталон/случайн/novel/рукопис/edge).
- Эскалация проверена: неверный админ + bootstrap=ctfapp -> флаг получен.
- Резервный ретрай со сэмплингом при провале (`fallback_temps`): стресс-тест 42/42 (100%).
- Совместимость сохранена: прямой путь и 16 тестов без изменений.

## [0.6.0] - 2026-06-12 - Робастность к формулировкам (v2)
- Тестами вскрыта слабость v1: переобучение на формулировки (novel 19%, live 0/3).
- `scripts/phrasings_aug.py`: обогащение трейна (синонимы, стили списков -/нумер./тире,
 шаблоны блоков). Подключено в `generate_dataset.py` (SQL-цели не тронуты).
- Переобучен адаптер **v2**; v1 сохранён в `adapters_v1_backup`.
- Результат v2: novel значения 70->96%, шаги 67->85%, полностью 19->30%, live 0/3->2/3.
 PDF-стиль held-out остался 100% (без регресса). 3/3 эталона.
- `scripts/eval_novel.py` + `scripts/generate_novel.py`: held-out устойчивость-оценка.

## [0.5.0] - 2026-06-12 - Сбор траекторий, тесты, демо
- Собрано **1510 траекторий** (1010 one-shot + 500 deep ReAct), 1434 ok / 76 fail.
- `agent/react_agent.py`: deep-режим (план + рефлексия + инъекция конфликтов БД).
- `scripts/export_openinference.py`: strict OTLP-экспорт (22502 span'а), Phoenix ingestion ОК.
- `scripts/verify.py`: все проверки ТЗ пройдены; `scripts/pick_showcase.py`: SHOWCASE-трейс.
- `tests/`: 16 тестов (11 компонентных + 5 интеграционных Oracle), pytest-cov.
- `scripts/{demo.py,eval_testset.py,verify_phoenix.py,finalize.sh}`: демо-ассеты + held-out eval.

## [0.4.0] - 2026-06-11 - Документация
- Добавлены PROJECT.md, PLAN.md, DIARY.md, CHANGELOG.md, REPORT.md.

## [0.3.0] - 2026-06-11 - Агент и фиксация траекторий
- `agent/tracing.py`: модуль фиксации траекторий в стандарте OpenInference
 (OpenTelemetry spans AGENT/LLM/TOOL -> `trajectories/ep_*.json`).
- `agent/oracle_tool.py`: интеграция с СУБД (`execute_sql`, `read_flag`, `reset_state`).
- `agent/llm.py`: policy на дообученной модели + sampling (temp) для вариативности.
- `agent/agent.py`: ReAct-цикл с коррекцией по ошибкам Oracle.
- `scripts/run_collection.py`: сбор ≥1000 траекторий.
- `scripts/verify.py`: верификация по ТЗ.
- Fix: фильтр пропускал `GRANT SELECT ON CTF.CTF_FLAG` -> ORA-00942; исправлено.
- Оптимизация: `max_tokens` 1000->600 (убран мусор за решением).

## [0.2.0] - 2026-06-11 - СУБД
- `docker/docker-compose.yml`: Oracle Free 23ai (ARM64).
- `docker/init/01_seed.sql`: seed окружения CTF (флаг, credentials, compromised_user, dba_ctf).

## [0.1.0] - 2026-06-11 - Датасет и дообучение
- `scripts/generate_dataset.py`: генератор 1000 вариантов (13 параметров профиля, перефразировки).
- `lora_config.yaml`: конфиг QLoRA (rank 16, mask_prompt, grad_checkpoint).
- `scripts/{train.sh,solve.py,eval_gold.py}`.
- Дообучен адаптер: train loss -> ~0.002.
- Окружение: venv Python 3.13, mlx-lm 0.31.3.
