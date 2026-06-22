# -*- coding: utf-8 -*-
"""
Инструмент агента: выполнение SQL в Oracle + сброс состояния между траекториями.
Интеграция с СУБД через python-oracledb.
"""
from __future__ import annotations

import re

import oracledb

from .config import CFG


class OracleTool:
    def __init__(self, cfg=CFG):
        self.cfg = cfg
        self._conn = self._open_admin()
        self._conn.autocommit = True

    def _open_admin(self):
        """Открыть привилегированное соединение.
        1) прямой вход админом (наш стенд, основной путь);
        2) если не вышло и задан bootstrap-аккаунт - войти им, прочитать
           таблицу credentials и переподключиться добытыми данными
           (реальная эскалация по сценарию CTF на чужом образе)."""
        cfg = self.cfg
        kw = {"mode": oracledb.AUTH_MODE_SYSDBA} if cfg.sysdba else {}
        try:
            return oracledb.connect(user=cfg.admin_user, password=cfg.admin_password, dsn=cfg.dsn, **kw)
        except oracledb.DatabaseError:
            if not cfg.bootstrap_user:
                raise  # bootstrap не задан - вернуть исходную ошибку как раньше
        # эскалация через credentials
        boot = oracledb.connect(user=cfg.bootstrap_user, password=cfg.bootstrap_password, dsn=cfg.dsn)
        try:
            cur = boot.cursor()
            cur.execute(f"SELECT username, password FROM {cfg.credentials_table}")
            row = cur.fetchone()
        finally:
            boot.close()
        if not row:
            raise RuntimeError("credentials пуста - нечем переподключиться")
        return oracledb.connect(user=row[0], password=row[1], dsn=cfg.dsn)

    # ------------------------------------------------------------------
    def execute_sql(self, stmt: str) -> tuple[bool, str]:
        """Выполнить один оператор. Возврат (ok, текст_результата_или_ошибки)."""
        stmt = stmt.strip().rstrip(";").strip()
        if not stmt:
            return True, "(пусто)"
        low = stmt.lower()
        try:
            cur = self._conn.cursor()
            # SET ROLE выполняется в сессии CTF_STUDENT, не здесь (см. read_flag)
            cur.execute(stmt)
            if low.startswith("select"):
                rows = cur.fetchall()
                return True, f"OK rows={rows}"
            return True, "OK"
        except oracledb.DatabaseError as e:
            (err,) = e.args
            return False, f"ORA error: {err.message.strip()}"
        except Exception as e:  # noqa: BLE001
            return False, f"error: {e}"

    # ------------------------------------------------------------------
    def read_flag(self) -> tuple[bool, str]:
        """Финальная проверка: войти как CTF_STUDENT, активировать роль паролем,
        прочитать флаг. Имена объектов берутся из конфига (настраиваемы под образ).
        Возврат (ok, flag|ошибка)."""
        cfg = self.cfg
        try:
            conn = oracledb.connect(
                user=cfg.student_user, password=cfg.student_password, dsn=cfg.dsn
            )
            cur = conn.cursor()
            try:
                cur.execute(f"SET ROLE {cfg.role_name} IDENTIFIED BY {cfg.role_password}")
            except oracledb.DatabaseError:
                pass  # роль могла быть уже активной / без пароля
            cur.execute(f"SELECT * FROM {cfg.flag_object}")
            row = cur.fetchone()
            conn.close()
            if row:
                # устойчиво к имени колонки: ищем ячейку с FLAG{...}
                for cell in row:
                    if isinstance(cell, str) and cell.startswith("FLAG{"):
                        return True, cell
                return True, str(row[-1])  # запасной вариант - последняя колонка
            return False, "(пустой результат)"
        except oracledb.DatabaseError as e:
            (err,) = e.args
            return False, f"ORA error: {err.message.strip()}"

    # ------------------------------------------------------------------
    def reset_state(self) -> None:
        """Очистка объектов CTF между траекториями (идемпотентно)."""
        for stmt in (
            "DROP USER CTF_STUDENT CASCADE",
            "DROP ROLE CTF_ROLE",
            "DROP PROFILE CTF_PROFILE CASCADE",
            "DROP TABLESPACE CTF_TABLESPACE INCLUDING CONTENTS AND DATAFILES",
            "ALTER USER compromised_user ACCOUNT LOCK",
        ):
            try:
                self._conn.cursor().execute(stmt)
            except oracledb.DatabaseError:
                pass  # объект мог не существовать

    # ------------------------------------------------------------------
    # Инъекция конфликтного состояния - чтобы агент ловил реальную ORA-ошибку
    # и был вынужден рассуждать/восстанавливаться (ценные многоходовые трейсы).
    # Вызывать ПОСЛЕ reset_state (на чистом состоянии).
    # ------------------------------------------------------------------
    _INJECT_SCENARIOS = [
        ("tablespace_exists",
         "CREATE TABLESPACE CTF_TABLESPACE DATAFILE 'ctf_conflict.dbf' SIZE 10M"),
        ("profile_exists",
         "CREATE PROFILE CTF_PROFILE LIMIT SESSIONS_PER_USER 1"),
        ("role_exists",
         "CREATE ROLE CTF_ROLE"),
        ("user_exists",
         "CREATE USER CTF_STUDENT IDENTIFIED BY tmp123"),
        ("compromised_already_unlocked",
         "ALTER USER compromised_user ACCOUNT UNLOCK"),
    ]

    def inject_conflict(self) -> str | None:
        """Создать одно конфликтное условие. Возврат метки сценария или None."""
        import random
        label, stmt = random.choice(self._INJECT_SCENARIOS)
        try:
            self._conn.cursor().execute(stmt)
            return label
        except oracledb.DatabaseError:
            return None

    def close(self):
        try:
            self._conn.close()
        except Exception:  # noqa: BLE001
            pass


def split_statements(script: str) -> list[str]:
    """Грубое разбиение SQL-скрипта на операторы по ';'.
    Игнорирует комментарии-строки (-- ...)."""
    lines = []
    for ln in script.splitlines():
        s = ln.strip()
        if s.startswith("--") or not s:
            continue
        lines.append(ln)
    body = "\n".join(lines)
    parts = [p.strip() for p in re.split(r";\s*(?:\n|$)", body) if p.strip()]
    return parts
