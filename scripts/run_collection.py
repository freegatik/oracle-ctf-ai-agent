#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Сбор траекторий: прогон агента по N вариантам задания.
Каждый прогон -> trajectories/ep_NNNNN.json (OpenInference). Включает неудачные.

Запуск:
  .venv/bin/python scripts/run_collection.py --n 1000
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.agent import Agent, save_trajectory          # noqa: E402
from agent.react_agent import ReactAgent                  # noqa: E402
from agent.config import CFG                              # noqa: E402
from agent.llm import LLM                                 # noqa: E402
from agent.oracle_tool import OracleTool                  # noqa: E402

# генератор вариантов
sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_dataset import make_variant, OFFICIAL       # noqa: E402


def task_iter(n: int):
    """Сначала 3 официальных, затем случайные до n штук."""
    i = 0
    for vi, fx in enumerate(OFFICIAL, start=1):
        task, _ = make_variant(vi, fixed=fx)
        yield vi, task
        i += 1
        if i >= n:
            return
    import random
    while i < n:
        vi = random.randint(1, 1000)
        task, _ = make_variant(vi)
        yield vi, task
        i += 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--mode", choices=["oneshot", "react"], default="oneshot",
                    help="oneshot = генерация+выполнение; react = план+пошагово+рассуждение")
    ap.add_argument("--inject-fail-rate", type=float, default=0.0,
                    help="доля прогонов с инъекцией конфликта БД (только react)")
    args = ap.parse_args()

    import random
    random.seed(args.seed)

    print(f"Загрузка модели {CFG.model} (+adapter={CFG.adapter}) mode={args.mode} ...",
          flush=True)
    llm = LLM()
    tool = OracleTool()
    if args.mode == "react":
        agent = ReactAgent(llm, tool, inject_fail_rate=args.inject_fail_rate)
    else:
        agent = Agent(llm, tool)

    n_ok = n_fail = 0
    t0 = time.time()
    for k, (variant, task) in enumerate(task_iter(args.n), start=1):
        doc = agent.solve(variant, task)
        doc.setdefault("mode", args.mode)
        path = save_trajectory(doc)
        if doc["success"]:
            n_ok += 1
        else:
            n_fail += 1
        if k % 10 == 0 or k <= 3:
            dt = time.time() - t0
            rate = k / dt if dt else 0
            print(f"[{k}/{args.n}] {path.name} variant={variant} "
                  f"success={doc['success']} spans={doc['n_spans']} "
                  f"| ok={n_ok} fail={n_fail} | {rate:.2f} traj/s", flush=True)

    tool.close()
    print(f"\nГОТОВО: {n_ok+n_fail} траекторий (ok={n_ok}, fail={n_fail}) "
          f"за {time.time()-t0:.0f}s -> {CFG.traj_dir}/")


if __name__ == "__main__":
    main()
