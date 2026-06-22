# -*- coding: utf-8 -*-
"""
«Глубокий» ReAct-агент: пошаговое решение с явным рассуждением.

Отличие от agent.py (one-shot):
  - сначала строит ПЛАН решения (reasoning, CHAIN-span);
  - затем выполняет операторы по одному, после каждого фиксирует НАБЛЮДЕНИЕ;
  - при ошибке рассуждает о причине и корректирует (LLM-span);
  - выше температура -> больше естественных ошибок и восстановлений.

Траектории в том же OpenInference-формате (+ поле mode="react"), нумерация
продолжается, поэтому глубокие трейсы доливаются ПОВЕРХ уже собранных.
"""
from __future__ import annotations

from opentelemetry import trace
from openinference.semconv.trace import (
    SpanAttributes as SA,
    OpenInferenceSpanKindValues as KIND,
)

from .config import CFG
from .llm import LLM
from .oracle_tool import OracleTool, split_statements
from . import tracing

_tracer = trace.get_tracer("oracle-ctf-agent")


def _chain_span(name: str, input_text: str, output_text: str):
    sp = _tracer.start_span(name)
    sp.set_attribute(SA.OPENINFERENCE_SPAN_KIND, KIND.CHAIN.value)
    sp.set_attribute(SA.INPUT_VALUE, input_text)
    sp.set_attribute(SA.OUTPUT_VALUE, output_text)
    return sp


PLAN_PROMPT = (
    "Разбери CTF-задание по администрированию Oracle на последовательность шагов. "
    "Кратко перечисли план (по одному действию на строку), без SQL."
)


class ReactAgent:
    """Пошаговый агент с рассуждением."""

    def __init__(self, llm: LLM, tool: OracleTool, cfg=CFG, max_steps: int = 14,
                 inject_fail_rate: float = 0.0):
        self.llm = llm
        self.tool = tool
        self.cfg = cfg
        self.max_steps = max_steps
        self.inject_fail_rate = inject_fail_rate

    def _plan(self, task: str) -> str:
        msgs = [
            {"role": "system", "content": self.cfg.system_prompt},
            {"role": "user", "content": f"{task}\n\n{PLAN_PROMPT}"},
        ]
        plan = self.llm.complete(msgs)
        # LLM-span (рассуждение) + CHAIN-span (план как узел графа)
        tracing.llm_span(msgs, plan, self.cfg.model).end()
        _chain_span("plan", task, plan).end()
        return plan

    def solve(self, variant: int, task: str) -> dict:
        self.tool.reset_state()
        # инъекция конфликта БД (часть прогонов) -> реальная ORA-ошибка -> рефлексия
        injected = None
        import random
        if self.inject_fail_rate and random.random() < self.inject_fail_rate:
            injected = self.tool.inject_conflict()
        traj = tracing.Trajectory(self.cfg.traj_dir, variant, task)
        traj._root.set_attribute("agent.mode", "react")
        if injected:
            traj._root.set_attribute("ctf.injected_conflict", injected)

        # --- фаза рассуждения: план ---
        plan = self._plan(task)

        # --- фаза решения: полный SQL с учётом плана ---
        msgs = [
            {"role": "system", "content": self.cfg.system_prompt},
            {"role": "user", "content":
                f"{task}\n\nПлан решения:\n{plan}\n\n"
                "Теперь выдай полное SQL-решение для Oracle."},
        ]
        sql = self.llm.complete(msgs)
        tracing.llm_span(msgs, sql, self.cfg.model).end()

        # --- фаза действия: пооператорно, с наблюдением и коррекцией ---
        statements = [
            s for s in split_statements(sql)
            if not s.lower().startswith("set role")
            and not (s.lower().startswith("select") and "ctf_flag" in s.lower())
        ]
        step = 0
        for stmt in statements:
            if step >= self.max_steps:
                break
            step += 1
            ok, res = self.tool.execute_sql(stmt)
            tracing.tool_span(stmt, res, ok).end()

            # при ошибке - рассуждение о причине + коррекция оператора
            attempts = 0
            while not ok and attempts < self.cfg.max_fix_attempts:
                attempts += 1
                fmsgs = [
                    {"role": "system", "content": self.cfg.system_prompt},
                    {"role": "user", "content":
                        f"Оператор:\n{stmt}\nОшибка Oracle:\n{res}\n"
                        "Объясни причину одной фразой и верни ИСПРАВЛЕННЫЙ оператор (только SQL)."},
                ]
                fix = self.llm.complete(fmsgs)
                tracing.llm_span(fmsgs, fix, self.cfg.model).end()
                _chain_span("reflect_error", res, fix).end()
                # берём первый оператор из исправления
                parts = split_statements(fix)
                stmt2 = parts[0] if parts else fix
                ok, res = self.tool.execute_sql(stmt2)
                tracing.tool_span(stmt2, res, ok).end()

        # --- финал: достать флаг ---
        ok_flag, flag_or_err = self.tool.read_flag()
        tracing.tool_span(
            "CONNECT CTF_STUDENT; SET ROLE CTF_ROLE IDENTIFIED BY ctf_role; "
            "SELECT flag FROM CTF.CTF_FLAG", flag_or_err, ok_flag).end()

        success = ok_flag and str(flag_or_err).startswith("FLAG{")
        doc = traj.finish(success, flag_or_err if success else None)
        doc["mode"] = "react"
        doc["injected_conflict"] = injected
        return doc
