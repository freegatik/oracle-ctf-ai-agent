# -*- coding: utf-8 -*-
"""
ReAct-агент решения Oracle CTF.

Цикл:
  1. LLM: задание -> SQL-скрипт (фиксируется LLM-span).
  2. Выполнить операторы по очереди (TOOL-span на каждый).
  3. При ошибке -> LLM-коррекция (LLM-span), повтор (лимит попыток).
  4. Финал: read_flag (TOOL-span) -> success/failure.
Вся работа над одним заданием = одна траектория (root AGENT span).
"""
from __future__ import annotations

import json
from pathlib import Path

from .config import CFG
from .llm import LLM
from .oracle_tool import OracleTool, split_statements
from . import tracing


class Agent:
    def __init__(self, llm: LLM, tool: OracleTool, cfg=CFG):
        self.llm = llm
        self.tool = tool
        self.cfg = cfg

    def _run_script(self, sql: str) -> tuple[bool, list[str]]:
        """Выполнить все операторы скрипта, фиксируя TOOL-span'ы.
        Возврат (все_ок, список_ошибок)."""
        errors = []
        all_ok = True
        for stmt in split_statements(sql):
            low = stmt.lower()
            # SET ROLE и финальный SELECT флага выполняются отдельно в read_flag.
            # ВАЖНО: GRANT SELECT ON CTF.CTF_FLAG оставляем - он обязателен.
            if low.startswith("set role"):
                continue
            if low.startswith("select") and "ctf_flag" in low:
                continue
            ok, res = self.tool.execute_sql(stmt)
            sp = tracing.tool_span(stmt, res, ok)
            sp.end()
            if not ok:
                all_ok = False
                errors.append(f"[{stmt[:60]}...] -> {res}")
        return all_ok, errors

    def solve(self, variant: int, task: str) -> dict:
        """Решить одно задание, вернуть документ траектории."""
        self.tool.reset_state()  # чистый старт
        traj = tracing.Trajectory(self.cfg.traj_dir, variant, task)

        # --- шаг 1: первичное решение ---
        msgs, sql = self.llm.solve(task)
        tracing.llm_span(msgs, sql, self.cfg.model).end()
        all_ok, errors = self._run_script(sql)

        # --- шаги коррекции ---
        attempt = 0
        while errors and attempt < self.cfg.max_fix_attempts:
            attempt += 1
            err_text = "\n".join(errors)
            self.tool.reset_state()  # откат перед повторным прогоном
            fmsgs, sql = self.llm.fix(task, sql, err_text)
            tracing.llm_span(fmsgs, sql, self.cfg.model).end()
            all_ok, errors = self._run_script(sql)

        # --- финал: достать флаг ---
        ok_flag, flag_or_err = self.tool.read_flag()
        sp = tracing.tool_span(
            "CONNECT CTF_STUDENT; SET ROLE CTF_ROLE IDENTIFIED BY ctf_role; "
            "SELECT flag FROM CTF.CTF_FLAG",
            flag_or_err, ok_flag)
        sp.end()

        success = ok_flag and str(flag_or_err).startswith("FLAG{")

        # фолбэк: если детерминированный прогон не дал флаг, повторяем со
        # сэмплингом (другой вариант ответа модели). Срабатывает только при провале.
        for temp in (self.cfg.fallback_temps if not success else ()):
            self.tool.reset_state()
            fmsgs, sql = self.llm.solve(task, temperature=temp)
            tracing.llm_span(fmsgs, sql, self.cfg.model).end()
            self._run_script(sql)
            ok_flag, flag_or_err = self.tool.read_flag()
            tracing.tool_span(
                f"[retry t={temp}] SET ROLE; SELECT flag", flag_or_err, ok_flag).end()
            if ok_flag and str(flag_or_err).startswith("FLAG{"):
                success = True
                break

        doc = traj.finish(success, flag_or_err if success else None)
        return doc


def save_trajectory(doc: dict, cfg=CFG) -> Path:
    path = tracing.next_episode_path(cfg.traj_dir)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
