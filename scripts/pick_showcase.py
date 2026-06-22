#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Выбирает показательную deep-траекторию для демонстрации «агент рассуждает»:
приоритет — была инъекция конфликта + рефлексия ошибки + успешное восстановление.
Копирует в trajectories/SHOWCASE.json и печатает человекочитаемую раскадровку.

Запуск:
  .venv/bin/python scripts/pick_showcase.py
"""
import glob
import json
import shutil
from pathlib import Path

TRAJ = Path("trajectories")


def score(d: dict) -> int:
    """Чем выше — тем нагляднее для демо."""
    if d.get("mode") != "react":
        return -1
    kinds = [s["attributes"].get("openinference.span.kind") for s in d["spans"]]
    n_reflect = sum(1 for s in d["spans"] if s["name"] == "reflect_error")
    n_err = sum(1 for s in d["spans"]
                if s["attributes"].get("tool.status") == "error")
    s = 0
    if d.get("injected_conflict"):
        s += 5                      # был реальный конфликт
    s += n_err * 2                  # ловил ошибки
    s += n_reflect * 3              # рассуждал над ошибкой
    if d.get("success"):
        s += 10                     # и всё-таки восстановился -> идеальный показ
    return s


def main():
    best = None
    best_doc = None
    best_score = -1
    for f in glob.glob(str(TRAJ / "ep_*.json")):
        d = json.loads(Path(f).read_text(encoding="utf-8"))
        sc = score(d)
        if sc > best_score:
            best_score, best, best_doc = sc, f, d

    if best is None or best_score < 0:
        print("Нет react-траекторий — запусти deep-сбор сначала.")
        return

    dst = TRAJ / "SHOWCASE.json"
    shutil.copy(best, dst)
    d = best_doc
    print(f"Показательная траектория: {Path(best).name} -> {dst} (score={best_score})")
    print(f"  variant={d['variant']} success={d['success']} "
          f"injected={d.get('injected_conflict')} spans={d['n_spans']}")
    print("\n=== РАСКАДРОВКА (что делал агент) ===")
    for s in sorted(d["spans"], key=lambda x: x["start_time"]):
        a = s["attributes"]
        k = a.get("openinference.span.kind")
        if k == "AGENT":
            print(f"[AGENT] решает задачу variant={a.get('ctf.variant')}")
        elif k == "CHAIN":
            print(f"[{s['name'].upper()}] {a.get('output.value','')[:60]}")
        elif k == "LLM":
            print(f"[LLM] генерация ({len(a.get('output.value',''))} символов)")
        elif k == "TOOL":
            st = a.get("tool.status")
            tag = "OK " if st == "ok" else "ERR"
            print(f"  [{tag}] {a.get('input.value','').splitlines()[0][:55]} "
                  f"-> {a.get('output.value','')[:55]}")
    print(f"\nИтог: success={d['success']}, флаг={d.get('flag')}")


if __name__ == "__main__":
    main()
