#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ждёт готовности Oracle: опрашивает listener/БД, пока не примет соединение.
Параметры через env (выставляет solve_image.sh). DB считается готовой, если
соединение установлено ЛИБО ошибка авторизации (ORA-01017/01045) - значит БД
поднята, просто креды иные. Ошибки listener/сервиса -> ждём дальше."""
import os, sys, time
import oracledb

H = os.getenv("ORACLE_HOST", "localhost")
P = os.getenv("ORACLE_PORT", "1521")
S = os.getenv("ORACLE_SERVICE", "FREEPDB1")
U = os.getenv("AUSER", "dba_ctf")
PW = os.getenv("APW", "")
BU = os.getenv("BUSER", "")
BPW = os.getenv("BPW", "")
SDBA = os.getenv("SDBA", "0") in ("1", "true", "True")
TIMEOUT = int(os.getenv("WAIT_TIMEOUT", "420"))

dsn = f"{H}:{P}/{S}"
# коды, означающие "БД поднята" (дальше ждать не нужно)
DB_UP_CODES = (1017, 1045, 28000, 1005)   # auth/locked - listener+DB живы

def try_connect(user, pw):
    kw = {"mode": oracledb.AUTH_MODE_SYSDBA} if SDBA else {}
    c = oracledb.connect(user=user, password=pw, dsn=dsn, **kw)
    c.close()

deadline = time.time() + TIMEOUT
last = ""
while time.time() < deadline:
    for u, p in [(U, PW)] + ([(BU, BPW)] if BU else []):
        try:
            try_connect(u, p)
            print(f"ORACLE READY (вход {u})")
            sys.exit(0)
        except oracledb.DatabaseError as e:
            (err,) = e.args
            last = err.message.strip()
            code = getattr(err, "code", 0)
            if code in DB_UP_CODES:
                print(f"ORACLE READY (БД поднята, код {code}: проверь креды при решении)")
                sys.exit(0)
        except Exception as e:  # noqa: BLE001
            last = str(e)
    print(f"  ... жду ({last[:70]})", flush=True)
    time.sleep(6)

print(f"TIMEOUT: Oracle не готов за {TIMEOUT}с. Последнее: {last}")
sys.exit(1)
