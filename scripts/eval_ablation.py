#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Абляция: значимость дообучения и системного промпта.
4 конфигурации на held-out (data/test.jsonl), структурная проверка.

  база + полный промпт (со шпаргалкой)
  база + сокращённый (lean)
  дообученная + lean
  дообученная + полный

Только инференс (read-only). Модель/адаптер не изменяются.

Запуск:  .venv/bin/python scripts/eval_ablation.py
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from mlx_lm import generate, load        # noqa: E402
from agent.config import CFG             # noqa: E402

LEAN = ("Ты эксперт по администрированию Oracle Database. "
        "Реши CTF-задание: выдай полное SQL-решение для Oracle.")

FULL = LEAN + (
    "\n\nПорядок шагов: 1) ALTER USER compromised_user ACCOUNT UNLOCK; "
    "2) SELECT из credentials; 3) CREATE TABLESPACE CTF_TABLESPACE с AUTOEXTEND и MAXSIZE 1G; "
    "4) CREATE PROFILE CTF_PROFILE LIMIT ...; 5) CREATE ROLE CTF_ROLE IDENTIFIED BY ctf_role; "
    "6) CREATE USER CTF_STUDENT ... PROFILE CTF_PROFILE; "
    "7) GRANT CREATE SESSION; GRANT SELECT ON CTF.CTF_FLAG TO CTF_ROLE; GRANT CTF_ROLE TO CTF_STUDENT; "
    "ALTER USER CTF_STUDENT DEFAULT ROLE ALL EXCEPT CTF_ROLE; "
    "8) SET ROLE CTF_ROLE IDENTIFIED BY ctf_role; SELECT FROM CTF.CTF_FLAG.\n"
    "Соответствие параметров: одновременные сессии=SESSIONS_PER_USER, простой=IDLE_TIME, "
    "соединение=CONNECT_TIME, CPU на сессию/вызов=CPU_PER_SESSION/CPU_PER_CALL, "
    "логические чтения=LOGICAL_READS_PER_SESSION/_PER_CALL, неуспешные входы=FAILED_LOGIN_ATTEMPTS, "
    "блокировка=PASSWORD_LOCK_TIME, срок пароля=PASSWORD_LIFE_TIME, льготный=PASSWORD_GRACE_TIME, "
    "повтор пароля=PASSWORD_REUSE_TIME/_REUSE_MAX.")

STEPS = [
    r"ALTER\s+USER\s+compromised_user\s+ACCOUNT\s+UNLOCK", r"FROM\s+credentials",
    r"CREATE\s+TABLESPACE\s+CTF_TABLESPACE", r"MAXSIZE\s+1G",
    r"CREATE\s+PROFILE\s+CTF_PROFILE\s+LIMIT",
    r"CREATE\s+ROLE\s+CTF_ROLE\s+IDENTIFIED\s+BY\s+ctf_role",
    r"CREATE\s+USER\s+CTF_STUDENT\s+IDENTIFIED\s+BY\s+ctf_student",
    r"GRANT\s+CREATE\s+SESSION\s+TO\s+CTF_STUDENT",
    r"GRANT\s+SELECT\s+ON\s+CTF\.CTF_FLAG\s+TO\s+CTF_ROLE",
    r"GRANT\s+CTF_ROLE\s+TO\s+CTF_STUDENT",
    r"SET\s+ROLE\s+CTF_ROLE\s+IDENTIFIED\s+BY\s+ctf_role",
]


def eval_config(model, tok, rows, sysprompt):
    full_ok = 0
    for ex in rows:
        prompt = tok.apply_chat_template(
            [{"role": "system", "content": sysprompt}, ex["messages"][1]],
            add_generation_prompt=True, tokenize=False)
        g = re.sub(r"\s+", " ", generate(model, tok, prompt=prompt, max_tokens=700, verbose=False))
        if all(re.search(p, g, re.I) for p in STEPS):
            full_ok += 1
    return full_ok, len(rows)


def main():
    rows = [json.loads(l) for l in open("data/test.jsonl", encoding="utf-8")]
    results = []

    print("Загрузка БАЗОВОЙ модели (без адаптера)...", flush=True)
    bm, bt = load(CFG.model, adapter_path=None)
    for name, sp in [("полный (со шпаргалкой)", FULL), ("сокращённый (lean)", LEAN)]:
        ok, n = eval_config(bm, bt, rows, sp)
        results.append(("Qwen2.5-Coder-7B (база)", name, ok, n))
        print(f"  база | {name}: {ok}/{n}", flush=True)
    del bm, bt

    print("Загрузка ДООБУЧЕННОЙ модели (+адаптер)...", flush=True)
    tm, tt = load(CFG.model, adapter_path=CFG.adapter)
    for name, sp in [("сокращённый (lean)", LEAN), ("полный", FULL)]:
        ok, n = eval_config(tm, tt, rows, sp)
        results.append(("Qwen2.5-Coder-7B-CTF (QLoRA)", name, ok, n))
        print(f"  дообуч | {name}: {ok}/{n}", flush=True)

    print("\n=== АБЛЯЦИЯ (held-out, 50 вариантов вне обучения) ===")
    for m, sp, ok, n in results:
        print(f"{m:32s} | {sp:24s} | {ok}/{n} ({100*ok//n}%)")
    Path("logs").mkdir(exist_ok=True)
    Path("logs/ablation.json").write_text(json.dumps(results, ensure_ascii=False))


if __name__ == "__main__":
    main()
