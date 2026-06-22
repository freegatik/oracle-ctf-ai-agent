#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Проверка: траектории реально принимаются Arize Phoenix через OTLP-пайплайн
(тот же OpenInference, что и в агенте). Поднимает локальный Phoenix, эмитит
тестовую траекторию через agent/tracing.py, подтверждает приём по числу span'ов.

Запуск:
  .venv/bin/python scripts/verify_phoenix.py

Для живого показа на защите Phoenix остаётся поднятым (UI на http://localhost:6006).
"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import phoenix as px

# 1. Phoenix-сервер должен быть уже поднят отдельно:  .venv/bin/phoenix serve
#    (на нагруженной машине in-process launch_app не успевает стартовать).
ENDPOINT = os.environ.setdefault("PHOENIX_COLLECTOR_ENDPOINT", "http://localhost:6006")
print(f"Phoenix endpoint: {ENDPOINT}  (UI там же в браузере)")

# 2. импорт tracing уже с включённым OTLP-экспортом в Phoenix
from agent import tracing  # noqa: E402
from opentelemetry import trace  # noqa: E402

# 3. эмитим тестовую траекторию (без модели — синтетика)
traj = tracing.Trajectory("trajectories", variant=1, task="DEMO задание")
m = [{"role": "user", "content": "DEMO задание"}]
tracing.llm_span(m, "CREATE USER ...", "demo-model").end()
tracing.tool_span("ALTER USER compromised_user ACCOUNT UNLOCK", "OK", True).end()
tracing.tool_span("CREATE TABLESPACE CTF_TABLESPACE ...", "OK", True).end()
tracing.tool_span("SELECT flag FROM CTF.CTF_FLAG", "FLAG{demo}", True).end()
traj.finish(True, "FLAG{demo}")

# 4. форс-флаш экспортёра и пауза на приём
trace.get_tracer_provider().force_flush()
time.sleep(3)

# 5. подтвердить приём
try:
    from phoenix.client import Client
    df = Client(base_url=ENDPOINT).spans.get_spans_dataframe(project_name="default")
    n = 0 if df is None else len(df)
    print(f"Phoenix принял span'ов: {n}")
    print("РЕЗУЛЬТАТ: OpenInference-траектории ингестятся в Phoenix — OK"
          if n >= 5 else "ВНИМАНИЕ: span'ы не подтверждены, проверь endpoint")
except Exception as e:  # noqa: BLE001
    print(f"Запрос к Phoenix не удался: {e}")

print("\nPhoenix-сервер работает отдельно (phoenix serve). UI: http://localhost:6006")
