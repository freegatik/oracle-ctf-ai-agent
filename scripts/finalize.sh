#!/usr/bin/env bash
# Финальный прогон после сбора всех траекторий. Запускать когда deep-сбор завершён
# (Oracle свободен). Результаты -> finalize.log.
set -uo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python
LOG=finalize.log
: > "$LOG"

say() { echo -e "\n========== $1 ==========" | tee -a "$LOG"; }

say "1. STRICT OTLP EXPORT"
$PY scripts/export_openinference.py 2>&1 | tee -a "$LOG"

say "2. VERIFY (ТЗ)"
$PY scripts/verify.py 2>&1 | tee -a "$LOG"

say "3. SHOWCASE (deep провал->recovery)"
$PY scripts/pick_showcase.py 2>&1 | tee -a "$LOG"

say "4. HELD-OUT EVAL (50 невиданных, обобщение)"
$PY scripts/eval_testset.py 2>&1 | tee -a "$LOG"

say "5. NOVEL TASKS (рукописные вне генератора, live Oracle -> флаг)"
for t in tests/novel_tasks/novel_*.txt; do
  echo "--- $t ---" | tee -a "$LOG"
  $PY scripts/demo.py --task-file "$t" 2>&1 | grep -aE "ФЛАГ|не получен|FAIL|OK\]" | tee -a "$LOG"
done

say "5b. ROBUSTNESS (100 НОВЫХ задач вне обучения, структурно)"
$PY scripts/eval_novel.py --n 100 2>&1 | tee -a "$LOG"

say "6. COVERAGE (pytest)"
PHOENIX_COLLECTOR_ENDPOINT= $PY -m pytest tests/ --cov=agent --cov=scripts \
  --cov-report=term-missing -q 2>&1 | tail -25 | tee -a "$LOG"

say "ФИНАЛ ЗАВЕРШЁН — см. finalize.log"
