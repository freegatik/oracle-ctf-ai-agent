# -*- coding: utf-8 -*-
"""Policy агента - дообученная QLoRA-модель Qwen2.5-Coder через mlx-lm."""
from __future__ import annotations

from mlx_lm import generate, load
from mlx_lm.sample_utils import make_sampler

from .config import CFG


class LLM:
    def __init__(self, cfg=CFG):
        self.cfg = cfg
        adapter = cfg.adapter if cfg.adapter else None
        self.model, self.tokenizer = load(cfg.model, adapter_path=adapter)
        # temp>0 -> вариативность: часть прогонов даст ORA-ошибку -> fix-loop,
        # естественные неудачные попытки в траекториях (реализм + требование ТЗ)
        self._sampler = make_sampler(temp=cfg.temperature)

    def complete(self, messages: list[dict], temperature: float | None = None) -> str:
        prompt = self.tokenizer.apply_chat_template(
            messages, add_generation_prompt=True, tokenize=False
        )
        # temperature задан - разовый сэмплер (фолбэк), иначе дефолтный (детерминированный)
        sampler = make_sampler(temp=temperature) if temperature is not None else self._sampler
        out = generate(
            self.model, self.tokenizer, prompt=prompt,
            max_tokens=self.cfg.max_tokens, sampler=sampler, verbose=False,
        ).strip()
        # обрезать утечку спец-токенов чата (модель иногда печатает их как текст)
        for stop in ("<|im_end|>", "<|endoftext|>", "<|im_start|>"):
            if stop in out:
                out = out.split(stop)[0]
        return out.strip()

    def solve(self, task: str, temperature: float | None = None) -> tuple[list[dict], str]:
        """Первичное решение задания. Возврат (input_messages, output_sql)."""
        msgs = [
            {"role": "system", "content": self.cfg.system_prompt},
            {"role": "user", "content": task},
        ]
        return msgs, self.complete(msgs, temperature=temperature)

    def fix(self, task: str, prev_sql: str, error: str) -> tuple[list[dict], str]:
        """Коррекция после ошибки СУБД."""
        msgs = [
            {"role": "system", "content": self.cfg.system_prompt},
            {"role": "user", "content": task},
            {"role": "assistant", "content": prev_sql},
            {"role": "user", "content":
                f"При выполнении возникла ошибка Oracle:\n{error}\n"
                "Исправь SQL-решение целиком с учётом ошибки. Верни только SQL."},
        ]
        return msgs, self.complete(msgs)
