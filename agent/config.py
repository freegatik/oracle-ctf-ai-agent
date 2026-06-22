# -*- coding: utf-8 -*-
"""Параметры агента. Управляются через переменные окружения."""
import os
from dataclasses import dataclass, field


@dataclass
class Config:
    # --- Oracle ---
    oracle_host: str = os.getenv("ORACLE_HOST", "localhost")
    oracle_port: int = int(os.getenv("ORACLE_PORT", "1521"))
    oracle_service: str = os.getenv("ORACLE_SERVICE", "FREEPDB1")
    # привилегированный пользователь, под которым агент делает админ-операции
    admin_user: str = os.getenv("ORACLE_ADMIN_USER", "dba_ctf")
    admin_password: str = os.getenv("ORACLE_ADMIN_PASSWORD", "S3cr3tDBA!")
    # стартовый (низкопривилегированный) аккаунт образа: если задан и прямой
    # вход админом не удался — агент войдёт им, прочитает credentials и
    # переподключится добытыми данными (реальная эскалация по сценарию ТЗ).
    bootstrap_user: str = os.getenv("ORACLE_BOOTSTRAP_USER", "")
    bootstrap_password: str = os.getenv("ORACLE_BOOTSTRAP_PASSWORD", "")
    credentials_table: str = os.getenv("CREDENTIALS_TABLE", "credentials")
    # вход в режиме SYSDBA (нужно при подключении как sys)
    sysdba: bool = os.getenv("ORACLE_SYSDBA", "0") in ("1", "true", "True")

    # --- объекты CTF (настраиваемы под образ; дефолты = наш стенд) ---
    flag_object: str = os.getenv("CTF_FLAG_OBJECT", "CTF.CTF_FLAG")
    student_user: str = os.getenv("CTF_STUDENT_USER", "CTF_STUDENT")
    student_password: str = os.getenv("CTF_STUDENT_PASSWORD", "ctf_student")
    role_name: str = os.getenv("CTF_ROLE_NAME", "CTF_ROLE")
    role_password: str = os.getenv("CTF_ROLE_PASSWORD", "ctf_role")

    # --- LLM ---
    model: str = os.getenv("MODEL", "mlx-community/Qwen2.5-Coder-7B-Instruct-4bit")
    adapter: str | None = os.getenv("ADAPTER", "adapters")
    max_tokens: int = int(os.getenv("MAX_TOKENS", "600"))
    # дефолт 0 = детерминированно (демо/eval). Сбор deep передаёт TEMPERATURE=0.6 явно.
    temperature: float = float(os.getenv("TEMPERATURE", "0.0"))

    # --- Агент ---
    max_fix_attempts: int = int(os.getenv("MAX_FIX_ATTEMPTS", "2"))
    # фолбэк: если детерминированный прогон не дал флаг - повторы со сэмплингом
    # (срабатывает ТОЛЬКО при провале; пустой список = выключить)
    fallback_temps: tuple = (0.5, 0.7, 0.9)

    # --- Траектории ---
    traj_dir: str = os.getenv("TRAJ_DIR", "trajectories")

    system_prompt: str = field(default=(
        "Ты - эксперт по администрированию Oracle Database. "
        "На вход даётся CTF-задание на русском языке. "
        "Выдай корректное и полное SQL-решение для Oracle, выполняющее все пункты по порядку.\n"
        "\n"
        "Порядок шагов решения:\n"
        "1) ALTER USER compromised_user ACCOUNT UNLOCK;\n"
        "2) SELECT username, password FROM credentials; (вход под полученными данными)\n"
        "3) CREATE TABLESPACE CTF_TABLESPACE DATAFILE 'ctf_tablespace01.dbf' "
        "SIZE <N>M AUTOEXTEND ON NEXT 10M MAXSIZE 1G;\n"
        "4) CREATE PROFILE CTF_PROFILE LIMIT <параметры>;\n"
        "5) CREATE ROLE CTF_ROLE IDENTIFIED BY ctf_role;\n"
        "6) CREATE USER CTF_STUDENT IDENTIFIED BY ctf_student DEFAULT TABLESPACE CTF_TABLESPACE "
        "TEMPORARY TABLESPACE TEMP QUOTA <Q>M ON CTF_TABLESPACE PROFILE CTF_PROFILE ACCOUNT UNLOCK;\n"
        "7) GRANT CREATE SESSION TO CTF_STUDENT; GRANT SELECT ON CTF.CTF_FLAG TO CTF_ROLE; "
        "GRANT CTF_ROLE TO CTF_STUDENT; ALTER USER CTF_STUDENT DEFAULT ROLE ALL EXCEPT CTF_ROLE;\n"
        "8) (под CTF_STUDENT) SET ROLE CTF_ROLE IDENTIFIED BY ctf_role; SELECT * FROM CTF.CTF_FLAG;\n"
        "\n"
        "Соответствие русских формулировок параметрам профиля Oracle:\n"
        "одновременные сессии = SESSIONS_PER_USER; время простоя/бездействия = IDLE_TIME (мин); "
        "время соединения = CONNECT_TIME (мин); CPU на сессию = CPU_PER_SESSION; "
        "CPU на вызов = CPU_PER_CALL; логические чтения за сессию = LOGICAL_READS_PER_SESSION; "
        "логические чтения на вызов = LOGICAL_READS_PER_CALL; "
        "неуспешные попытки входа = FAILED_LOGIN_ATTEMPTS; "
        "время блокировки учётной записи = PASSWORD_LOCK_TIME (дни); "
        "срок действия пароля = PASSWORD_LIFE_TIME (дни); "
        "льготный период = PASSWORD_GRACE_TIME (дни); "
        "запрет повтора пароля N дней = PASSWORD_REUSE_TIME (дни); "
        "запрет последних N паролей = PASSWORD_REUSE_MAX.\n"
        "\n"
        "Правила: имена объектов и пароли использовать точно как заданы "
        "(CTF_TABLESPACE, CTF_PROFILE, CTF_ROLE, ctf_role, CTF_STUDENT, ctf_student, CTF.CTF_FLAG). "
        "Роль выдавать, но не делать ролью по умолчанию. Доступ к CTF.CTF_FLAG - только через роль. "
        "Числовые значения брать из задания дословно. Возвращать только SQL."
    ))

    @property
    def dsn(self) -> str:
        return f"{self.oracle_host}:{self.oracle_port}/{self.oracle_service}"


CFG = Config()
