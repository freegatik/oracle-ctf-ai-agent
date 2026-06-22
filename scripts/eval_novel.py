#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Robustness-оценка: модель на N НОВЫХ задачах (формулировки вне обучающего набора,
generate_novel.py). Структурная проверка: 11 обязательных шагов + точные значения
(размер TS, квота, все параметры профиля). Детерминированно (greedy).

Запуск:
  .venv/bin/python scripts/eval_novel.py --n 100
  .venv/bin/python scripts/eval_novel.py --n 100 --no-adapter   # база для сравнения
"""
import argparse
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from mlx_lm import generate, load     # noqa: E402
from agent.config import CFG          # noqa: E402
from generate_novel import make_novel  # noqa: E402

STEPS = [
    r"ALTER\s+USER\s+compromised_user\s+ACCOUNT\s+UNLOCK",
    r"FROM\s+credentials",
    r"CREATE\s+TABLESPACE\s+CTF_TABLESPACE",
    r"MAXSIZE\s+1G",
    r"CREATE\s+PROFILE\s+CTF_PROFILE\s+LIMIT",
    r"CREATE\s+ROLE\s+CTF_ROLE\s+IDENTIFIED\s+BY\s+ctf_role",
    r"CREATE\s+USER\s+CTF_STUDENT\s+IDENTIFIED\s+BY\s+ctf_student",
    r"GRANT\s+CREATE\s+SESSION\s+TO\s+CTF_STUDENT",
    r"GRANT\s+SELECT\s+ON\s+CTF\.CTF_FLAG\s+TO\s+CTF_ROLE",
    r"GRANT\s+CTF_ROLE\s+TO\s+CTF_STUDENT",
    r"SET\s+ROLE\s+CTF_ROLE\s+IDENTIFIED\s+BY\s+ctf_role",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--no-adapter", action="store_true")
    args = ap.parse_args()
    random.seed(args.seed)

    adapter = None if args.no_adapter else CFG.adapter
    model, tok = load(CFG.model, adapter_path=adapter)

    full_ok = steps_ok = steps_tot = 0
    val_ok = val_tot = 0
    sysmsg = {"role": "system", "content": CFG.system_prompt}

    for i in range(1, args.n + 1):
        task, exp = make_novel(i)
        prompt = tok.apply_chat_template(
            [sysmsg, {"role": "user", "content": task}],
            add_generation_prompt=True, tokenize=False)
        gen = generate(model, tok, prompt=prompt, max_tokens=700, verbose=False)
        g = re.sub(r"\s+", " ", gen)

        s = sum(bool(re.search(p, g, re.I)) for p in STEPS)
        steps_ok += s; steps_tot += len(STEPS)
        # точные значения
        v = vt = 0
        vt += 1; v += bool(re.search(rf"SIZE\s+{exp['ts_size']}M", g, re.I))
        vt += 1; v += bool(re.search(rf"QUOTA\s+{exp['quota']}M", g, re.I))
        for nm, val in exp["profile"]:
            vt += 1; v += bool(re.search(rf"{nm}\s+{val}\b", g, re.I))
        val_ok += v; val_tot += vt
        if s == len(STEPS) and v == vt:
            full_ok += 1
        if i % 20 == 0:
            print(f"  {i}/{args.n} ...", flush=True)

    tag = "базовая" if args.no_adapter else "дообученная"
    print(f"\n=== ROBUSTNESS ({tag}), {args.n} НОВЫХ задач (формулировки вне обучения) ===")
    print(f"Полностью верных (11 шагов + все значения): {full_ok}/{args.n} "
          f"({100*full_ok/args.n:.1f}%)")
    print(f"Обязательные шаги: {steps_ok}/{steps_tot} ({100*steps_ok/steps_tot:.1f}%)")
    print(f"Точные значения:   {val_ok}/{val_tot} ({100*val_ok/val_tot:.1f}%)")


if __name__ == "__main__":
    main()
