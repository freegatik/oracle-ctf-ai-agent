#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Верификация по ТЗ:
  1. Собрано >= 1000 траекторий.
  2. Траектории валидны: формат OpenInference (span.kind, llm/tool атрибуты).
  3. Присутствуют как успешные, так и неудачные (ТЗ требует включать провалы).
  4. 3 официальных варианта решаются успешно.
  5. Статистика по success rate, числу span'ов, коррекциям.
"""
import json
import sys
from collections import Counter
from pathlib import Path

TRAJ = Path("trajectories")
REQUIRED = 1000


def load_all():
    docs = []
    for p in sorted(TRAJ.glob("ep_*.json")):
        try:
            docs.append((p.name, json.loads(p.read_text(encoding="utf-8"))))
        except Exception as e:  # noqa: BLE001
            print(f"  BAD JSON: {p.name}: {e}")
    return docs


def check_openinference(doc) -> bool:
    """Минимальная проверка соответствия OpenInference."""
    if doc.get("schema") != "openinference-spans-v1":
        return False
    kinds = {s["attributes"].get("openinference.span.kind") for s in doc["spans"]}
    if "AGENT" not in kinds or "LLM" not in kinds or "TOOL" not in kinds:
        return False
    # хотя бы один TOOL span с tool.name
    has_tool = any(
        s["attributes"].get("tool.name") == "execute_sql" for s in doc["spans"])
    return has_tool


def main():
    docs = load_all()
    n = len(docs)
    print(f"Траекторий найдено: {n}")

    valid = sum(1 for _, d in docs if check_openinference(d))
    succ = sum(1 for _, d in docs if d.get("success"))
    fail = n - succ
    span_counts = [d["n_spans"] for _, d in docs]
    variants = Counter(d.get("variant") for _, d in docs)

    modes = Counter(d.get("mode", "oneshot") for _, d in docs)
    injected = Counter(d.get("injected_conflict") for _, d in docs
                       if d.get("injected_conflict"))
    print(f"OpenInference-валидных: {valid}/{n}")
    print(f"Режимы: {dict(modes)}")
    if injected:
        print(f"Инъекции конфликтов: {dict(injected)}")
    print(f"Успешных: {succ} | Неудачных: {fail}")
    if span_counts:
        print(f"Span'ов: min={min(span_counts)} avg={sum(span_counts)/n:.1f} "
              f"max={max(span_counts)}")
    print(f"Уникальных вариантов: {len(variants)}")

    checks = {
        f">= {REQUIRED} траекторий": n >= REQUIRED,
        "все OpenInference-валидны": valid == n,
        "есть успешные": succ > 0,
        "есть неудачные (ТЗ)": fail > 0,
    }
    print("\n=== ПРОВЕРКИ ТЗ ===")
    all_ok = True
    for name, ok in checks.items():
        print(f"  [{'OK ' if ok else 'XX '}] {name}")
        all_ok &= ok

    # официальные варианты (1,2,3) должны иметь хотя бы один success
    for v in (1, 2, 3):
        ok = any(d.get("success") for _, d in docs if d.get("variant") == v)
        print(f"  [{'OK ' if ok else 'XX '}] вариант {v} решается успешно")
        all_ok &= ok

    print(f"\nИТОГ: {'ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ' if all_ok else 'ЕСТЬ ПРОБЛЕМЫ'}")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
