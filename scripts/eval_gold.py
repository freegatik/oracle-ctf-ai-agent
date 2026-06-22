#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Проверка модели на 3 официальных вариантах (data/gold_official.jsonl).

Для каждого варианта генерируем SQL и проверяем наличие обязательных
конструкций (структурная проверка, т.к. точное посимвольное совпадение
для генерации нереалистично). Печатает PASS/FAIL по пунктам.
"""
import json
import re
import sys

from mlx_lm import generate, load

MODEL = "mlx-community/Qwen2.5-Coder-7B-Instruct-4bit"
ADAPTER = "adapters"


def required_checks(expected_sql):
    """Извлекаем ключевые факты из эталонного SQL -> список (имя, regex)."""
    checks = [
        ("unlock compromised_user",
         r"ALTER\s+USER\s+compromised_user\s+ACCOUNT\s+UNLOCK"),
        ("read credentials",
         r"FROM\s+credentials"),
        ("create tablespace",
         r"CREATE\s+TABLESPACE\s+CTF_TABLESPACE"),
        ("autoextend maxsize 1G",
         r"AUTOEXTEND\s+ON.*MAXSIZE\s+1G"),
        ("create profile",
         r"CREATE\s+PROFILE\s+CTF_PROFILE\s+LIMIT"),
        ("create role w/ password",
         r"CREATE\s+ROLE\s+CTF_ROLE\s+IDENTIFIED\s+BY\s+ctf_role"),
        ("create user",
         r"CREATE\s+USER\s+CTF_STUDENT\s+IDENTIFIED\s+BY\s+ctf_student"),
        ("default tablespace",
         r"DEFAULT\s+TABLESPACE\s+CTF_TABLESPACE"),
        ("temp tablespace",
         r"TEMPORARY\s+TABLESPACE\s+TEMP"),
        ("profile assigned",
         r"PROFILE\s+CTF_PROFILE"),
        ("grant create session",
         r"GRANT\s+CREATE\s+SESSION\s+TO\s+CTF_STUDENT"),
        ("grant select via role",
         r"GRANT\s+SELECT\s+ON\s+CTF\.CTF_FLAG\s+TO\s+CTF_ROLE"),
        ("grant role to user",
         r"GRANT\s+CTF_ROLE\s+TO\s+CTF_STUDENT"),
        ("role not default",
         r"DEFAULT\s+ROLE\s+(ALL\s+EXCEPT\s+CTF_ROLE|NONE)"),
        ("set role w/ password",
         r"SET\s+ROLE\s+CTF_ROLE\s+IDENTIFIED\s+BY\s+ctf_role"),
        ("select flag",
         r"SELECT.*FROM\s+CTF\.CTF_FLAG"),
    ]
    # размер табличного пространства и квота — из эталона
    m = re.search(r"SIZE\s+(\d+)M", expected_sql)
    if m:
        checks.append((f"tablespace size {m.group(1)}M",
                       rf"SIZE\s+{m.group(1)}M"))
    m = re.search(r"QUOTA\s+(\d+)M", expected_sql)
    if m:
        checks.append((f"quota {m.group(1)}M",
                       rf"QUOTA\s+{m.group(1)}M"))
    # параметры профиля из эталона
    for pm in re.finditer(r"^\s+([A-Z_]+)\s+(\d+)$", expected_sql, re.M):
        name, val = pm.group(1), pm.group(2)
        checks.append((f"profile {name}={val}",
                       rf"{name}\s+{val}\b"))
    return checks


def main():
    no_adapter = "--no-adapter" in sys.argv
    adapter = None if no_adapter else ADAPTER
    model, tokenizer = load(MODEL, adapter_path=adapter)

    total_pass = total = 0
    with open("data/gold_official.jsonl", encoding="utf-8") as f:
        variants = [json.loads(l) for l in f]

    for i, ex in enumerate(variants, 1):
        sysmsg = ex["messages"][0]
        task = ex["messages"][1]
        expected = ex["messages"][2]["content"]
        prompt = tokenizer.apply_chat_template(
            [sysmsg, task], add_generation_prompt=True, tokenize=False)
        gen = generate(model, tokenizer, prompt=prompt, max_tokens=900, verbose=False)
        gen_norm = re.sub(r"\s+", " ", gen)

        print(f"\n===== ВАРИАНТ {i} =====")
        checks = required_checks(expected)
        ok = 0
        for name, pat in checks:
            found = re.search(pat, gen_norm, re.I | re.S) is not None
            print(f"  [{'OK ' if found else 'XX '}] {name}")
            ok += found
        print(f"  -> {ok}/{len(checks)} пунктов")
        total_pass += ok
        total += len(checks)

    print(f"\nИТОГО: {total_pass}/{total} проверок пройдено "
          f"({100*total_pass/total:.1f}%)")


if __name__ == "__main__":
    main()
