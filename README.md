<div align="center">

<img src="assets/banner.png?v=2" alt="Oracle-CTF AI Agent" width="100%"/>

# Oracle-CTF AI Agent

**Автономный ИИ-агент, который решает CTF-задачи администрирования Oracle Database и фиксирует траектории в стандарте OpenInference.**

[![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Model](https://img.shields.io/badge/Qwen2.5--Coder--7B-QLoRA-6f42c1)](https://huggingface.co/mlx-community/Qwen2.5-Coder-7B-Instruct-4bit)
[![MLX](https://img.shields.io/badge/MLX-Apple%20Silicon-black?logo=apple&logoColor=white)](https://github.com/ml-explore/mlx)
[![Oracle](https://img.shields.io/badge/Oracle%20Free-23ai-F80000?logo=oracle&logoColor=white)](https://www.oracle.com/database/free/)
[![OpenInference](https://img.shields.io/badge/OpenInference-Phoenix-00b0ff)](https://arize-ai.github.io/openinference/)
[![Tests](https://img.shields.io/badge/tests-16%20passed-success)](tests/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

[Русский](#-русский) · [English](#-english)

</div>

---

## 🇷🇺 Русский

Дообученная локальная LLM (**Qwen2.5-Coder-7B**, QLoRA) в обёртке-агенте: получает задание на русском, генерирует SQL для Oracle, выполняет его в **реальной СУБД**, при ошибке исправляется и доводит задачу до получения флага. Каждый прогон пишется траекторией в стандарте **OpenInference** (видно в Arize Phoenix).

> ⚠️ `FLAG{0r4cl3_pr1v_3sc_m4st3r}` в коде — **синтетический демо-флаг** локального стенда, не из реального CTF.

### ✨ Возможности
- 🧠 **Дообученная модель** — QLoRA-адаптер поверх 4-битной Qwen2.5-Coder, запуск на Apple Silicon через MLX.
- 🔧 **Агентный цикл (ReAct)** — генерация SQL → выполнение в Oracle → наблюдение → коррекция по ORA-ошибкам.
- 🗄️ **Реальная СУБД** — Oracle Database Free 23ai в Docker, не мок.
- 📊 **Фиксация траекторий** — OpenInference/OpenTelemetry, экспорт в Phoenix.
- 🔐 **Эскалация привилегий** — старт под низкопривилегированным аккаунтом → чтение `credentials` → переподключение.
- 🛟 **Надёжность** — детерминированный прогон + резервный повтор со сэмплингом (стресс-тест **42/42**).

### 🏗️ Архитектура
```
задание → [ Agent ] → SQL → [ OracleTool ] → Oracle 23ai
              │  ▲                                  │
              │  └──── наблюдение / ORA-ошибка ◄────┘
              ▼
        [ tracing ] → OpenInference spans → ep_*.json + Arize Phoenix
              │
         [ LLM: Qwen2.5-Coder-7B + QLoRA (MLX) ]
```

### 🚀 Быстрый старт
```bash
python3.13 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 1) поднять СУБД
docker compose -f docker/docker-compose.yml up -d

# 2) решить задачу и достать флаг (живой прогон + траектория)
python scripts/demo.py --variant 1
```
Универсальный запуск из образа любого формата:
```bash
bash flag_extractor/solve_image.sh <образ.tar | docker:REF | running> --task task.txt
```

### 📈 Результаты
| Метрика | Значение |
|---------|----------|
| Стресс-тест (эталон/случайн/novel/edge) | **42/42 (100%)** |
| Эталонные варианты | 3/3 — флаг получен |
| Собрано траекторий | 1510 (вкл. неудачные) |
| Абляция: база lean → дообуч полный | 2% → **100%** |
| Юнит/интеграционные тесты | 16 — все проходят |

### 🗂️ Структура
```
agent/          код агента (config, llm, oracle_tool, tracing, agent, react_agent)
scripts/        генерация данных, сбор траекторий, eval, demo
flag_extractor/ универсальный извлекатель флага из образа + инструкция
docker/         Oracle 23ai compose + seed CTF-сцены
data/           обучающий датасет (jsonl)
adapters/       дообученный QLoRA-адаптер
trajectories/   примеры траекторий OpenInference
tests/          16 тестов
docs/           ARCHITECTURE / PLAN / REPORT и др.
```

---

## 🇬🇧 English

A fine-tuned local LLM (**Qwen2.5-Coder-7B**, QLoRA) wrapped as an agent: it reads a task in Russian, generates Oracle SQL, runs it against a **real database**, self-corrects on errors, and drives the task to capturing the flag. Every run is recorded as an **OpenInference** trajectory (viewable in Arize Phoenix).

> ⚠️ `FLAG{0r4cl3_pr1v_3sc_m4st3r}` in the code is a **synthetic demo flag** for the local stand, not from a real CTF.

### ✨ Features
- 🧠 **Fine-tuned model** — QLoRA adapter over 4-bit Qwen2.5-Coder, runs on Apple Silicon via MLX.
- 🔧 **Agentic loop (ReAct)** — generate SQL → execute in Oracle → observe → correct on ORA errors.
- 🗄️ **Real DBMS** — Oracle Database Free 23ai in Docker, not a mock.
- 📊 **Trajectory tracing** — OpenInference/OpenTelemetry, exported to Phoenix.
- 🔐 **Privilege escalation** — start as a low-priv account → read `credentials` → reconnect.
- 🛟 **Robustness** — deterministic run + sampling fallback (stress test **42/42**).

### 🏗️ Architecture
```
task → [ Agent ] → SQL → [ OracleTool ] → Oracle 23ai
          │  ▲                                  │
          │  └──── observation / ORA error ◄────┘
          ▼
    [ tracing ] → OpenInference spans → ep_*.json + Arize Phoenix
          │
     [ LLM: Qwen2.5-Coder-7B + QLoRA (MLX) ]
```

### 🚀 Quick start
```bash
python3.13 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 1) start the DBMS
docker compose -f docker/docker-compose.yml up -d

# 2) solve a task and capture the flag (live run + trajectory)
python scripts/demo.py --variant 1
```
Universal launch from any image format:
```bash
bash flag_extractor/solve_image.sh <image.tar | docker:REF | running> --task task.txt
```

### 📈 Results
| Metric | Value |
|--------|-------|
| Stress test (official/random/novel/edge) | **42/42 (100%)** |
| Official variants | 3/3 — flag captured |
| Trajectories collected | 1510 (incl. failures) |
| Ablation: base lean → tuned full | 2% → **100%** |
| Unit/integration tests | 16 — all pass |

### 🗂️ Layout
```
agent/          agent code (config, llm, oracle_tool, tracing, agent, react_agent)
scripts/        data generation, trajectory collection, eval, demo
flag_extractor/ universal image→flag launcher + instructions
docker/         Oracle 23ai compose + CTF seed
data/           training dataset (jsonl)
adapters/       fine-tuned QLoRA adapter
trajectories/   OpenInference trajectory samples
tests/          16 tests
docs/           ARCHITECTURE / PLAN / REPORT etc.
```

---

<div align="center">
<sub>Built with Qwen2.5-Coder · MLX · Oracle 23ai · OpenInference · Arize Phoenix · MIT License</sub>
</div>
