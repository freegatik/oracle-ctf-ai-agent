#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ДЕМО: живой прогон агента на одном CTF-задании.

Показывает по шагам: задание -> SQL от модели -> выполнение в реальной Oracle ->
ответ СУБД на каждый оператор -> получение флага. ОДНОВРЕМЕННО записывает
траекторию в стандарте OpenInference: сохраняет ep_*.json и шлёт в Arize Phoenix
(http://localhost:6006) - там виден весь процесс и рассуждения деревом span'ов.
Детерминированно (greedy, temp 0); при неудаче - резервный повтор со сэмплингом.

Запуск:
  .venv/bin/python scripts/demo.py                 # официальный Вариант 1
  .venv/bin/python scripts/demo.py --variant 2     # Вариант 2 / 3
  .venv/bin/python scripts/demo.py --task-file t.txt
  echo "Вариант ..." | .venv/bin/python scripts/demo.py
"""
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

# включить live-экспорт траектории в Phoenix ДО импорта tracing (если сервер поднят)
os.environ.setdefault("PHOENIX_COLLECTOR_ENDPOINT", "http://localhost:6006")

from agent.config import CFG                         # noqa: E402
from agent.llm import LLM                            # noqa: E402
from agent.oracle_tool import OracleTool, split_statements  # noqa: E402
from agent import tracing                            # noqa: E402
from opentelemetry import trace as _otel             # noqa: E402
from generate_dataset import make_variant, OFFICIAL  # noqa: E402

C_HEAD = "\033[1;36m"; C_OK = "\033[1;32m"; C_ERR = "\033[1;31m"
C_SQL = "\033[0;33m"; C_DIM = "\033[2m"; C_RST = "\033[0m"; C_FLAG = "\033[1;35m"


def banner(t):
    print(f"\n{C_HEAD}{'='*70}\n{t}\n{'='*70}{C_RST}")


def run_script(tool, sql):
    """Выполнить операторы скрипта (кроме SET ROLE и финального SELECT флага),
    печатая и фиксируя каждый в TOOL-span."""
    for stmt in split_statements(sql):
        low = stmt.lower()
        if low.startswith("set role"):
            continue
        if low.startswith("select") and "ctf_flag" in low:
            continue
        ok, res = tool.execute_sql(stmt)
        tracing.tool_span(stmt, res, ok).end()
        mark = f"{C_OK}OK{C_RST}" if ok else f"{C_ERR}FAIL{C_RST}"
        print(f"  [{mark}] {stmt.splitlines()[0][:58]} {C_DIM}-> {res[:64]}{C_RST}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", type=int, default=1, choices=[1, 2, 3])
    ap.add_argument("--task-file")
    args = ap.parse_args()

    if args.task_file:
        task = Path(args.task_file).read_text(encoding="utf-8")
    elif not sys.stdin.isatty():
        task = sys.stdin.read()
    else:
        task, _ = make_variant(args.variant, fixed=OFFICIAL[args.variant - 1])

    banner("CTF-ЗАДАНИЕ")
    print(task.strip())

    print(f"\n{C_DIM}Загрузка дообученной модели (greedy, temp=0)...{C_RST}")
    llm = LLM(); tool = OracleTool(); tool.reset_state()

    traj = tracing.Trajectory(CFG.traj_dir, args.variant, task)

    banner("ШАГ 1. Модель генерирует SQL-решение")
    msgs, sql = llm.solve(task)
    tracing.llm_span(msgs, sql, CFG.model).end()
    print(f"{C_SQL}{sql}{C_RST}")

    banner("ШАГ 2. Выполнение в реальной Oracle (по операторам)")
    run_script(tool, sql)

    banner("ШАГ 3. Вход под CTF_STUDENT, активация роли паролем, чтение флага")
    ok, flag = tool.read_flag()
    tracing.tool_span("CONNECT CTF_STUDENT; SET ROLE ...; SELECT flag", flag, ok).end()
    success = ok and str(flag).startswith("FLAG{")

    # резервный повтор со сэмплингом, если детерминированный прогон не дал флаг
    for temp in (CFG.fallback_temps if not success else ()):
        print(f"{C_DIM}  повтор со сэмплингом (temp={temp})...{C_RST}")
        tool.reset_state()
        m2, sql = llm.solve(task, temperature=temp)
        tracing.llm_span(m2, sql, CFG.model).end()
        run_script(tool, sql)
        ok, flag = tool.read_flag()
        tracing.tool_span(f"[retry t={temp}] SELECT flag", flag, ok).end()
        if ok and str(flag).startswith("FLAG{"):
            success = True
            break

    # завершить и сохранить траекторию
    doc = traj.finish(success, flag if success else None)
    path = tracing.next_episode_path(CFG.traj_dir)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        _otel.get_tracer_provider().force_flush()
    except Exception:  # noqa: BLE001
        pass

    if success:
        print(f"\n{C_FLAG}  ФЛАГ ПОЛУЧЕН: {flag}{C_RST}")
    else:
        print(f"\n{C_ERR}  Флаг не получен: {flag}{C_RST}")
    print(f"{C_DIM}  Траектория: {path}  (участков: {doc['n_spans']}){C_RST}")
    print(f"{C_DIM}  Процесс и рассуждения деревом span'ов: http://localhost:6006{C_RST}\n")
    tool.close()


if __name__ == "__main__":
    main()
