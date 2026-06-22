# -*- coding: utf-8 -*-
"""
Интеграционные тесты СУБД (требование ТЗ: интеграция с СУБД).

Только READ-ONLY проверки — не трогают объекты CTF_*, поэтому безопасны
даже во время сбора траекторий. Скипаются, если Oracle недоступен.

Запуск:
  .venv/bin/python -m pytest tests/test_oracle_integration.py -v
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _conn():
    import oracledb
    from agent.config import CFG
    return oracledb.connect(user=CFG.admin_user, password=CFG.admin_password,
                            dsn=CFG.dsn)


@pytest.fixture(scope="module")
def conn():
    try:
        c = _conn()
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"Oracle недоступен: {e}")
    yield c
    c.close()


def test_db_alive(conn):
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM dual")
    assert cur.fetchone()[0] == 1


def test_flag_object_exists(conn):
    cur = conn.cursor()
    cur.execute("SELECT flag FROM CTF.CTF_FLAG WHERE id=1")
    row = cur.fetchone()
    assert row and row[0].startswith("FLAG{")


def test_credentials_table(conn):
    cur = conn.cursor()
    cur.execute("SELECT username, password FROM credentials")
    row = cur.fetchone()
    assert row and len(row) == 2


def test_compromised_user_seeded(conn):
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM dba_users WHERE username='COMPROMISED_USER'")
    assert cur.fetchone()[0] == 1


def test_resource_limit_enabled(conn):
    """Профили должны применяться (RESOURCE_LIMIT=TRUE) — иначе лимиты игнорятся."""
    cur = conn.cursor()
    cur.execute("SELECT value FROM v$parameter WHERE name='resource_limit'")
    row = cur.fetchone()
    assert row and row[0].upper() == "TRUE"
