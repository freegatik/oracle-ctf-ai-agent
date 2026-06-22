# -*- coding: utf-8 -*-
"""
Тесты отдельных компонентов системы (требование ТЗ: тестирование компонентов).

Чистые unit-тесты — без Oracle и без модели (не мешают сбору траекторий).
Покрывают: разбор SQL, генератор датасета, фиксацию траекторий (OpenInference),
strict OTLP-экспорт, конфиг.

Запуск:
  .venv/bin/python -m pytest tests/ -v
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))


# ---------------------------------------------------------------------------
# 1. Разбор SQL-скрипта на операторы (agent/oracle_tool.split_statements)
# ---------------------------------------------------------------------------
def test_split_statements_basic():
    from agent.oracle_tool import split_statements
    sql = "ALTER USER x ACCOUNT UNLOCK;\nSELECT 1 FROM dual;"
    parts = split_statements(sql)
    assert len(parts) == 2
    assert parts[0].startswith("ALTER USER")
    assert parts[1].startswith("SELECT")


def test_split_statements_skips_comments():
    from agent.oracle_tool import split_statements
    sql = "-- комментарий\nCREATE ROLE r;\n-- ещё\nGRANT x TO r;"
    parts = split_statements(sql)
    assert len(parts) == 2
    assert all(not p.startswith("--") for p in parts)


def test_split_statements_multiline():
    from agent.oracle_tool import split_statements
    sql = "CREATE PROFILE p LIMIT\n  SESSIONS_PER_USER 2\n  IDLE_TIME 10;"
    parts = split_statements(sql)
    assert len(parts) == 1
    assert "SESSIONS_PER_USER 2" in parts[0]


# ---------------------------------------------------------------------------
# 2. Генератор датасета — официальные варианты и валидность
# ---------------------------------------------------------------------------
def test_official_variants_match_pdf():
    """Эталоны из генератора совпадают со значениями из Примеры.pdf."""
    from generate_dataset import OFFICIAL
    assert OFFICIAL[0]["ts_size"] == 150 and OFFICIAL[0]["quota"] == 80
    assert OFFICIAL[1]["ts_size"] == 520 and OFFICIAL[1]["quota"] == 260
    assert OFFICIAL[2]["ts_size"] == 560 and OFFICIAL[2]["quota"] == 280
    p1 = dict(OFFICIAL[0]["profile"])
    assert p1["SESSIONS_PER_USER"] == 4 and p1["IDLE_TIME"] == 30
    assert p1["FAILED_LOGIN_ATTEMPTS"] == 3
    assert p1["PASSWORD_REUSE_TIME"] == 60 and p1["PASSWORD_REUSE_MAX"] == 4


def test_make_variant_solution_has_all_steps():
    """SQL-решение содержит все 8 обязательных шагов."""
    from generate_dataset import make_variant, OFFICIAL
    task, sql = make_variant(1, fixed=OFFICIAL[0])
    for must in [
        "ALTER USER compromised_user ACCOUNT UNLOCK",
        "FROM credentials",
        "CREATE TABLESPACE CTF_TABLESPACE",
        "MAXSIZE 1G",
        "CREATE PROFILE CTF_PROFILE LIMIT",
        "CREATE ROLE CTF_ROLE IDENTIFIED BY ctf_role",
        "CREATE USER CTF_STUDENT IDENTIFIED BY ctf_student",
        "GRANT CREATE SESSION TO CTF_STUDENT",
        "GRANT SELECT ON CTF.CTF_FLAG TO CTF_ROLE",
        "GRANT CTF_ROLE TO CTF_STUDENT",
        "SET ROLE CTF_ROLE IDENTIFIED BY ctf_role",
    ]:
        assert must in sql, f"отсутствует шаг: {must}"


def test_make_variant_randomized_valid():
    """Случайный вариант: квота <= размера TS, профиль 4-6 параметров."""
    import random
    from generate_dataset import make_variant, PROFILE_PARAMS
    random.seed(123)
    for _ in range(20):
        task, sql = make_variant(random.randint(1, 1000))
        # размер и квота присутствуют
        assert "CREATE TABLESPACE CTF_TABLESPACE" in sql
        # все параметры профиля из известного пула
        prof = sql.split("CREATE PROFILE CTF_PROFILE LIMIT")[1].split(";")[0]
        names = [ln.split()[0] for ln in prof.strip().splitlines() if ln.strip()]
        assert 4 <= len(names) <= 6
        assert all(n in PROFILE_PARAMS for n in names)


def test_chat_format():
    from generate_dataset import make_variant, OFFICIAL, to_chat
    task, sql = make_variant(1, fixed=OFFICIAL[0])
    rec = to_chat(task, sql)
    roles = [m["role"] for m in rec["messages"]]
    assert roles == ["system", "user", "assistant"]


# ---------------------------------------------------------------------------
# 3. Фиксация траекторий — OpenInference атрибуты и структура
# ---------------------------------------------------------------------------
def test_tracing_openinference_attributes(tmp_path):
    from agent import tracing
    traj = tracing.Trajectory(str(tmp_path), variant=7, task="тест")
    tracing.llm_span([{"role": "user", "content": "q"}], "SQL", "m").end()
    tracing.tool_span("ALTER USER x ACCOUNT UNLOCK", "OK", True).end()
    doc = traj.finish(True, "FLAG{t}")

    kinds = {s["attributes"]["openinference.span.kind"] for s in doc["spans"]}
    assert {"AGENT", "LLM", "TOOL"} <= kinds
    # обязательные OpenInference-атрибуты
    tool = next(s for s in doc["spans"]
                if s["attributes"]["openinference.span.kind"] == "TOOL")
    assert tool["attributes"]["tool.name"] == "execute_sql"
    assert "input.value" in tool["attributes"]
    assert "output.value" in tool["attributes"]
    llm = next(s for s in doc["spans"]
               if s["attributes"]["openinference.span.kind"] == "LLM")
    assert any(k.startswith("llm.input_messages") for k in llm["attributes"])


def test_tracing_parent_nesting(tmp_path):
    """Дочерние span'ы привязаны к root AGENT span (один trace_id)."""
    from agent import tracing
    traj = tracing.Trajectory(str(tmp_path), variant=1, task="t")
    tracing.tool_span("X", "OK", True).end()
    doc = traj.finish(False, None)
    trace_ids = {s["trace_id"] for s in doc["spans"]}
    assert len(trace_ids) == 1  # все в одной трассе
    parents = [s for s in doc["spans"] if s["parent_id"] is None]
    assert len(parents) == 1  # ровно один корень


# ---------------------------------------------------------------------------
# 4. Strict OTLP-экспорт — валидная структура
# ---------------------------------------------------------------------------
def test_otlp_export_structure(tmp_path):
    import export_openinference as exp
    # подготовим минимальный ep-файл
    traj_dir = tmp_path / "trajectories"
    traj_dir.mkdir()
    doc = {
        "schema": "openinference-spans-v1", "trajectory_id": "a" * 32,
        "spans": [{
            "name": "tool.execute_sql", "span_id": "b" * 16, "trace_id": "a" * 32,
            "parent_id": None, "start_time": 1, "end_time": 2, "status": "OK",
            "attributes": {"openinference.span.kind": "TOOL",
                           "tool.name": "execute_sql", "input.value": "X"},
        }],
    }
    (traj_dir / "ep_00000.json").write_text(json.dumps(doc))
    # перенаправим пути модуля
    exp.TRAJ = traj_dir
    exp.OUT = traj_dir / "openinference_otlp.json"
    exp.main()
    otlp = json.loads(exp.OUT.read_text())
    assert "resourceSpans" in otlp
    span = otlp["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
    assert span["traceId"] == "a" * 32
    assert any(a["key"] == "openinference.span.kind" for a in span["attributes"])


# ---------------------------------------------------------------------------
# 5. Конфиг — DSN собирается корректно
# ---------------------------------------------------------------------------
def test_config_dsn():
    from agent.config import Config
    c = Config()
    assert "/" in c.dsn and ":" in c.dsn
    assert c.dsn.endswith(c.oracle_service)
