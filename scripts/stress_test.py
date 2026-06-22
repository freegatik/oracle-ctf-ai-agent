#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Максимальный live-стресс-тест агента против реальной Oracle.
Категории: 3 эталона, случайные, novel-фразировка (вне обучения),
рукописные, edge-cases (экстремальные значения). Считает реальное получение флага.

Запуск: .venv/bin/python scripts/stress_test.py
"""
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))

from agent.agent import Agent           # noqa: E402
from agent.llm import LLM               # noqa: E402
from agent.oracle_tool import OracleTool  # noqa: E402
from generate_dataset import make_variant, OFFICIAL, PROFILE_PARAMS  # noqa: E402
from generate_novel import make_novel   # noqa: E402


def edge_cases():
    """Экстремальные/необычные варианты."""
    out = []
    # минимальный TS + минимальная квота + 1 параметр
    out.append(("edge_min", {"ts_size": 50, "quota": 10,
                "profile": [("SESSIONS_PER_USER", 1)]}))
    # максимальный TS + большая квота + 6 параметров (макс)
    out.append(("edge_max6", {"ts_size": 900, "quota": 850,
                "profile": [("SESSIONS_PER_USER", 10), ("IDLE_TIME", 60),
                            ("CONNECT_TIME", 240), ("CPU_PER_SESSION", 100000),
                            ("FAILED_LOGIN_ATTEMPTS", 10), ("PASSWORD_LOCK_TIME", 30)]}))
    # только парольные параметры
    out.append(("edge_pwd", {"ts_size": 300, "quota": 150,
                "profile": [("PASSWORD_LIFE_TIME", 90), ("PASSWORD_GRACE_TIME", 7),
                            ("PASSWORD_REUSE_TIME", 365), ("PASSWORD_REUSE_MAX", 12),
                            ("PASSWORD_LOCK_TIME", 1)]}))
    # только ресурсные
    out.append(("edge_res", {"ts_size": 770, "quota": 400,
                "profile": [("LOGICAL_READS_PER_SESSION", 500000),
                            ("LOGICAL_READS_PER_CALL", 50000),
                            ("CPU_PER_SESSION", 90000), ("CPU_PER_CALL", 10000)]}))
    return out


def main():
    random.seed(2026)
    print("Загрузка дообученной модели (полный системный промпт)...", flush=True)
    llm = LLM(); tool = OracleTool(); agent = Agent(llm, tool)

    cats = {"эталон": 0, "случайн": 0, "novel": 0, "рукопис": 0, "edge": 0}
    tot = {k: 0 for k in cats}

    def run(cat, variant, task):
        doc = agent.solve(variant, task)
        ok = doc["success"]
        tot[cat] += 1; cats[cat] += ok
        print(f"  [{'FLAG' if ok else 'MISS'}] {cat:8s} v{variant}", flush=True)
        return ok

    print("\n-- 3 эталона --")
    for i, fx in enumerate(OFFICIAL, 1):
        run("эталон", i, make_variant(i, fixed=fx)[0])

    print("-- 20 случайных --")
    for _ in range(20):
        v = random.randint(1, 1000)
        run("случайн", v, make_variant(v)[0])

    print("-- 12 novel (фразировка вне обучения) --")
    for i in range(12):
        t, _ = make_novel(1000 + i)
        run("novel", 1000 + i, t)

    print("-- 3 рукописных --")
    for p in sorted((ROOT / "tests" / "novel_tasks").glob("novel_*.txt")):
        run("рукопис", 0, p.read_text(encoding="utf-8"))

    print("-- 4 edge-case --")
    for name, fx in edge_cases():
        run("edge", 0, make_variant(1, fixed=fx)[0])

    tool.close()
    print("\n==== ИТОГ live (реальный флаг из Oracle) ====")
    g = s = 0
    for k in cats:
        print(f"  {k:8s}: {cats[k]}/{tot[k]}")
        g += cats[k]; s += tot[k]
    print(f"  ВСЕГО:   {g}/{s} ({100*g//s}%)")


if __name__ == "__main__":
    main()
