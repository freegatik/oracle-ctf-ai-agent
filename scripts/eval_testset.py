#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Held-out оценка обобщения: прогон модели по data/test.jsonl (50 невиданных при
обучении примеров) со структурной проверкой обязательных SQL-шагов.

Даёт реальное число обобщения (не только 3 эталона). Детерминированно (greedy).

Запуск:
  .venv/bin/python scripts/eval_testset.py
  .venv/bin/python scripts/eval_testset.py --no-adapter   # базовая для сравнения
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mlx_lm import generate, load  # noqa: E402
from agent.config import CFG       # noqa: E402

REQUIRED = [
    ("unlock", r"ALTER\s+USER\s+compromised_user\s+ACCOUNT\s+UNLOCK"),
    ("credentials", r"FROM\s+credentials"),
    ("tablespace", r"CREATE\s+TABLESPACE\s+CTF_TABLESPACE"),
    ("maxsize1g", r"MAXSIZE\s+1G"),
    ("profile", r"CREATE\s+PROFILE\s+CTF_PROFILE\s+LIMIT"),
    ("role_pw", r"CREATE\s+ROLE\s+CTF_ROLE\s+IDENTIFIED\s+BY\s+ctf_role"),
    ("user", r"CREATE\s+USER\s+CTF_STUDENT\s+IDENTIFIED\s+BY\s+ctf_student"),
    ("grant_session", r"GRANT\s+CREATE\s+SESSION\s+TO\s+CTF_STUDENT"),
    ("grant_flag", r"GRANT\s+SELECT\s+ON\s+CTF\.CTF_FLAG\s+TO\s+CTF_ROLE"),
    ("grant_role", r"GRANT\s+CTF_ROLE\s+TO\s+CTF_STUDENT"),
    ("set_role", r"SET\s+ROLE\s+CTF_ROLE\s+IDENTIFIED\s+BY\s+ctf_role"),
]


def main():
    no_adapter = "--no-adapter" in sys.argv
    adapter = None if no_adapter else CFG.adapter
    model, tok = load(CFG.model, adapter_path=adapter)

    rows = [json.loads(l) for l in open("data/test.jsonl", encoding="utf-8")]
    full_ok = 0
    step_hits = {n: 0 for n, _ in REQUIRED}
    # извлечём ещё и числовые параметры из эталона каждого примера
    param_ok = param_total = 0

    for i, ex in enumerate(rows, 1):
        sysmsg, usr, asst = ex["messages"]
        prompt = tok.apply_chat_template([sysmsg, usr], add_generation_prompt=True,
                                         tokenize=False)
        gen = generate(model, tok, prompt=prompt, max_tokens=700, verbose=False)
        g = re.sub(r"\s+", " ", gen)

        ok_steps = sum(bool(re.search(p, g, re.I)) for _, p in REQUIRED)
        for n, p in REQUIRED:
            step_hits[n] += bool(re.search(p, g, re.I))
        # числовые параметры профиля из эталона должны присутствовать
        exp = asst["content"]
        for pm in re.finditer(r"^\s+([A-Z_]+)\s+(\d+)$", exp, re.M):
            param_total += 1
            param_ok += bool(re.search(rf"{pm.group(1)}\s+{pm.group(2)}\b", g, re.I))
        # размер TS и квота
        for rx in (r"SIZE\s+(\d+)M", r"QUOTA\s+(\d+)M"):
            m = re.search(rx, exp)
            if m:
                param_total += 1
                param_ok += bool(re.search(rx.replace(r"(\d+)", m.group(1)), g, re.I))

        if ok_steps == len(REQUIRED):
            full_ok += 1
        if i % 10 == 0:
            print(f"  {i}/{len(rows)} ...", flush=True)

    n = len(rows)
    print(f"\n=== HELD-OUT EVAL ({'базовая' if no_adapter else 'дообученная'}), "
          f"{n} примеров ===")
    print(f"Полностью верных (все 11 шагов): {full_ok}/{n} "
          f"({100*full_ok/n:.1f}%)")
    print(f"Параметры (значения профиля+размер+квота): {param_ok}/{param_total} "
          f"({100*param_ok/max(1,param_total):.1f}%)")
    print("Попадание по шагам:")
    for nstep, _ in REQUIRED:
        print(f"  {nstep:14s} {step_hits[nstep]}/{n}")


if __name__ == "__main__":
    main()
