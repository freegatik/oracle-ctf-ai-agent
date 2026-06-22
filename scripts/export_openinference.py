#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Strict-экспорт траекторий в каноничный формат OpenTelemetry/OpenInference (OTLP JSON).

Читает все trajectories/ep_*.json (наша человекочитаемая сериализация) и собирает
единый файл `trajectories/openinference_otlp.json` в структуре OTLP `resourceSpans`,
который напрямую принимается Arize Phoenix и любым OTel-бэкендом. Так буква стандарта
"OpenInference" закрывается каноничным экспортом, а не только использованием атрибутов.

Запуск:
  .venv/bin/python scripts/export_openinference.py
"""
import glob
import json
from pathlib import Path

TRAJ = Path("trajectories")
OUT = TRAJ / "openinference_otlp.json"


def _attr_value(v):
    """Кодирование значения атрибута по OTLP AnyValue."""
    if isinstance(v, bool):
        return {"boolValue": v}
    if isinstance(v, int):
        return {"intValue": str(v)}
    if isinstance(v, float):
        return {"doubleValue": v}
    return {"stringValue": str(v)}


def _attrs(d: dict) -> list:
    return [{"key": k, "value": _attr_value(v)} for k, v in d.items()]


def _otlp_span(s: dict, traj_meta: dict) -> dict:
    attrs = dict(s.get("attributes", {}))
    # дублируем метаданные траектории в атрибуты span'а (variant, success, mode)
    attrs.setdefault("ctf.trajectory_id", traj_meta["trajectory_id"])
    span = {
        "traceId": s["trace_id"],
        "spanId": s["span_id"],
        "name": s["name"],
        "kind": 1,  # SPAN_KIND_INTERNAL - OpenInference kind лежит в атрибутах
        "startTimeUnixNano": str(s["start_time"]),
        "endTimeUnixNano": str(s["end_time"]),
        "attributes": _attrs(attrs),
        "status": {"code": 1 if s.get("status") == "OK" else 0},
    }
    if s.get("parent_id"):
        span["parentSpanId"] = s["parent_id"]
    return span


def main():
    files = sorted(glob.glob(str(TRAJ / "ep_*.json")))
    all_spans = []
    n_traj = 0
    for f in files:
        doc = json.loads(Path(f).read_text(encoding="utf-8"))
        meta = {"trajectory_id": doc.get("trajectory_id", "")}
        for s in doc.get("spans", []):
            all_spans.append(_otlp_span(s, meta))
        n_traj += 1

    otlp = {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": _attrs({
                        "service.name": "oracle-ctf-agent",
                        "openinference.project.name": "oracle-ctf",
                    })
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "oracle-ctf-agent", "version": "1.0"},
                        "spans": all_spans,
                    }
                ],
            }
        ]
    }
    OUT.write_text(json.dumps(otlp, ensure_ascii=False), encoding="utf-8")
    print(f"OTLP-экспорт: {n_traj} траекторий, {len(all_spans)} span'ов -> {OUT}")
    print("Импорт в Phoenix: px.Client().log_traces(...) либо OTLP-приёмник.")


if __name__ == "__main__":
    main()
