#!/usr/bin/env bash
# Запуск QLoRA-обучения. Модель скачается с HF при первом запуске (~4.3GB).
set -euo pipefail
cd "$(dirname "$0")/.."
.venv/bin/python -m mlx_lm lora --config lora_config.yaml "$@"
