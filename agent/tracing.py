# -*- coding: utf-8 -*-
"""
Модуль фиксации траекторий в стандарте OpenInference (поверх OpenTelemetry).

Каждая траектория = один root-span (kind=AGENT) с дочерними LLM/TOOL span'ами.
По завершении траектории все её span'ы выгружаются в trajectories/ep_NNNNN.json
с OpenInference-атрибутами. Неудачные траектории сохраняются так же (требование ТЗ).
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from opentelemetry import trace, context as context_api
from opentelemetry.sdk.trace import TracerProvider, ReadableSpan
from opentelemetry.sdk.trace.export import SpanProcessor
from openinference.semconv.trace import (
    SpanAttributes as SA,
    MessageAttributes as MA,
    OpenInferenceSpanKindValues as KIND,
)

# глобальный список накопленных span'ов текущего процесса, группируется по trace_id
_COLLECTED: dict[int, list[ReadableSpan]] = {}


class _CollectingProcessor(SpanProcessor):
    """Накапливает завершённые span'ы в памяти, сгруппированными по trace_id."""

    def on_start(self, span, parent_context=None):  # noqa: D401
        pass

    def on_end(self, span: ReadableSpan) -> None:
        tid = span.context.trace_id
        _COLLECTED.setdefault(tid, []).append(span)

    def shutdown(self) -> None:
        pass

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True


_provider = TracerProvider()
_provider.add_span_processor(_CollectingProcessor())

# Опциональный live-экспорт в Phoenix (тот же OpenInference-пайплайн, не пост-хак).
# Включается заданием PHOENIX_COLLECTOR_ENDPOINT (напр. http://localhost:6006).
import os as _os  # noqa: E402
_px_ep = _os.getenv("PHOENIX_COLLECTOR_ENDPOINT")
if _px_ep:
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    _provider.add_span_processor(BatchSpanProcessor(
        OTLPSpanExporter(endpoint=f"{_px_ep.rstrip('/')}/v1/traces")))

trace.set_tracer_provider(_provider)
_tracer = trace.get_tracer("oracle-ctf-agent")


def _msg_attrs(prefix: str, messages: list[dict]) -> dict[str, Any]:
    """Разворачивает список сообщений в плоские OpenInference-атрибуты."""
    out: dict[str, Any] = {}
    for i, m in enumerate(messages):
        out[f"{prefix}.{i}.{MA.MESSAGE_ROLE}"] = m.get("role", "")
        out[f"{prefix}.{i}.{MA.MESSAGE_CONTENT}"] = m.get("content", "")
    return out


def llm_span(messages_in: list[dict], output_text: str, model_name: str):
    """Контекст-менеджер для LLM-вызова."""
    span = _tracer.start_span("llm.generate")
    span.set_attribute(SA.OPENINFERENCE_SPAN_KIND, KIND.LLM.value)
    span.set_attribute(SA.LLM_MODEL_NAME, model_name)
    for k, v in _msg_attrs(SA.LLM_INPUT_MESSAGES, messages_in).items():
        span.set_attribute(k, v)
    out_msgs = [{"role": "assistant", "content": output_text}]
    for k, v in _msg_attrs(SA.LLM_OUTPUT_MESSAGES, out_msgs).items():
        span.set_attribute(k, v)
    span.set_attribute(SA.INPUT_VALUE, messages_in[-1]["content"] if messages_in else "")
    span.set_attribute(SA.OUTPUT_VALUE, output_text)
    return span


def tool_span(sql: str, result: str, ok: bool):
    """Span для вызова инструмента execute_sql."""
    span = _tracer.start_span("tool.execute_sql")
    span.set_attribute(SA.OPENINFERENCE_SPAN_KIND, KIND.TOOL.value)
    span.set_attribute(SA.TOOL_NAME, "execute_sql")
    span.set_attribute(SA.INPUT_VALUE, sql)
    span.set_attribute(SA.OUTPUT_VALUE, result)
    span.set_attribute("tool.status", "ok" if ok else "error")
    return span


def _span_to_dict(s: ReadableSpan) -> dict[str, Any]:
    return {
        "name": s.name,
        "span_id": format(s.context.span_id, "016x"),
        "trace_id": format(s.context.trace_id, "032x"),
        "parent_id": format(s.parent.span_id, "016x") if s.parent else None,
        "start_time": s.start_time,
        "end_time": s.end_time,
        "status": s.status.status_code.name,
        "attributes": dict(s.attributes or {}),
    }


class Trajectory:
    """Управляет жизненным циклом одной траектории (root AGENT span)."""

    def __init__(self, traj_dir: str, variant: int, task: str):
        self.dir = Path(traj_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.variant = variant
        self.task = task
        self.success = False
        self.flag: str | None = None
        self._root = _tracer.start_span("agent.solve")
        self._root.set_attribute(SA.OPENINFERENCE_SPAN_KIND, KIND.AGENT.value)
        self._root.set_attribute(SA.INPUT_VALUE, task)
        self._root.set_attribute("ctf.variant", variant)
        # делаем root активным span'ом - дочерние LLM/TOOL span'ы автоматически
        # привяжутся к нему как к родителю
        self._token = context_api.attach(trace.set_span_in_context(self._root))
        self._trace_id = self._root.context.trace_id

    def finish(self, success: bool, flag: str | None) -> Path:
        self.success = success
        self.flag = flag
        self._root.set_attribute("ctf.success", success)
        self._root.set_attribute(SA.OUTPUT_VALUE, flag or "")
        self._root.end()
        context_api.detach(self._token)

        spans = sorted(_COLLECTED.pop(self._trace_id, []), key=lambda s: s.start_time)
        doc = {
            "schema": "openinference-spans-v1",
            "trajectory_id": format(self._trace_id, "032x"),
            "variant": self.variant,
            "success": success,
            "flag": flag,
            "task": self.task,
            "n_spans": len(spans),
            "spans": [_span_to_dict(s) for s in spans],
        }
        return doc


def next_episode_path(traj_dir: str) -> Path:
    """Возвращает путь ep_NNNNN.json со следующим свободным номером."""
    d = Path(traj_dir)
    d.mkdir(parents=True, exist_ok=True)
    existing = sorted(d.glob("ep_*.json"))
    n = 0
    if existing:
        n = max(int(p.stem.split("_")[1]) for p in existing) + 1
    return d / f"ep_{n:05d}.json"
