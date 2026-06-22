#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Инференс: подаём текст CTF-задания -> получаем SQL-решение.
Использует дообученный LoRA-адаптер поверх базовой модели.

Примеры:
  # задание из файла
  .venv/bin/python scripts/solve.py --task-file task.txt
  # задание из stdin
  echo "Вариант 5 ..." | .venv/bin/python scripts/solve.py
"""
import argparse
import sys

from mlx_lm import generate, load

MODEL = "mlx-community/Qwen2.5-Coder-7B-Instruct-4bit"
ADAPTER = "adapters"
SYSTEM_PROMPT = (
    "Ты — эксперт по администрированию Oracle Database. "
    "На вход даётся CTF-задание на русском языке. "
    "Выдай корректное и полное SQL-решение для Oracle, "
    "выполняющее все пункты задания по порядку."
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task-file", help="файл с текстом задания")
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--adapter", default=ADAPTER, help="путь к LoRA-адаптеру (пусто = без)")
    ap.add_argument("--max-tokens", type=int, default=900)
    ap.add_argument("--no-adapter", action="store_true", help="базовая модель без дообучения")
    args = ap.parse_args()

    if args.task_file:
        with open(args.task_file, encoding="utf-8") as f:
            task = f.read()
    else:
        task = sys.stdin.read()
    if not task.strip():
        sys.exit("Пустое задание.")

    adapter = None if args.no_adapter else args.adapter
    model, tokenizer = load(args.model, adapter_path=adapter)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": task},
    ]
    prompt = tokenizer.apply_chat_template(
        messages, add_generation_prompt=True, tokenize=False
    )
    out = generate(model, tokenizer, prompt=prompt, max_tokens=args.max_tokens, verbose=True)
    return out


if __name__ == "__main__":
    main()
