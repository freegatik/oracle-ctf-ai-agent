#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Генератор обучающего датасета для CTF по администрированию Oracle Database.

Каждый пример = (русскоязычное задание -> эталонное SQL-решение).
Формат вывода: JSONL в chat-формате {"messages": [...]} для mlx-lm LoRA.

Структура задания (фиксированная, как в реальном экзамене):
  1. Разблокировать compromised_user
  2. Получить креды из таблицы credentials и войти
  3. Создать табличное пространство CTF_TABLESPACE (размер варьируется)
  4. Создать профиль CTF_PROFILE (набор ограничений варьируется)
  5. Создать роль CTF_ROLE с паролем ctf_role
  6. Создать пользователя CTF_STUDENT (квота/профиль варьируются)
  7. Выдать минимальные привилегии + роль без default + SELECT на CTF.CTF_FLAG через роль
  8. Под CTF_STUDENT активировать роль паролем и забрать флаг

Варьируется: размер TS, квота, поднабор параметров профиля, их значения,
русские формулировки. Имена объектов фиксированы (так в экзамене).
"""

import argparse
import json
import random
from pathlib import Path

# ---------------------------------------------------------------------------
# Пул параметров профиля.
# Каждый параметр: oracle-имя, генератор значения, список (шаблон_фразы) с {v}.
# {v} подставляется уже отформатированным (с единицами там, где нужно в тексте).
# В SQL всегда идёт «сырое» число (oracle ждёт минуты/дни/число — как в задании).
# ---------------------------------------------------------------------------

def _r(lo, hi, step=1):
    return random.randrange(lo, hi + 1, step)

PROFILE_PARAMS = {
    "SESSIONS_PER_USER": {
        "value": lambda: _r(1, 10),
        "phrases": [
            "Количество одновременных сессий = {v}",
            "Максимум одновременных сессий пользователя = {v}",
            "Лимит параллельных сессий = {v}",
            "Число одновременных подключений = {v}",
        ],
    },
    "IDLE_TIME": {
        "value": lambda: _r(5, 60, 5),
        "phrases": [
            "Время простоя = {v} минут",
            "Время простоя сессии = {v} минут",
            "Максимальное время бездействия = {v} минут",
            "Допустимый простой соединения = {v} минут",
        ],
    },
    "CONNECT_TIME": {
        "value": lambda: _r(30, 240, 10),
        "phrases": [
            "Время соединения = {v} минут",
            "Максимальное время подключения = {v} минут",
            "Лимит времени сессии = {v} минут",
        ],
    },
    "CPU_PER_SESSION": {
        "value": lambda: _r(10000, 100000, 1000),
        "phrases": [
            "Лимит CPU на сессию = {v}",
            "Ограничение процессорного времени за сессию = {v}",
            "Максимум CPU за сессию = {v}",
        ],
    },
    "CPU_PER_CALL": {
        "value": lambda: _r(1000, 10000, 500),
        "phrases": [
            "Лимит CPU на вызов = {v}",
            "Ограничение процессорного времени на вызов = {v}",
            "Максимум CPU на один вызов = {v}",
        ],
    },
    "LOGICAL_READS_PER_SESSION": {
        "value": lambda: _r(50000, 500000, 10000),
        "phrases": [
            "Лимит логических чтений за сессию = {v}",
            "Ограничение логических чтений на сессию = {v}",
            "Максимум логических чтений за сессию = {v}",
        ],
    },
    "LOGICAL_READS_PER_CALL": {
        "value": lambda: _r(1000, 50000, 1000),
        "phrases": [
            "Лимит логических чтений на вызов = {v}",
            "Ограничение логических чтений за вызов = {v}",
            "Максимум логических чтений на один вызов = {v}",
        ],
    },
    "FAILED_LOGIN_ATTEMPTS": {
        "value": lambda: _r(3, 10),
        "phrases": [
            "Ограничение на неуспешные попытки входа = {v}",
            "Число неудачных попыток входа до блокировки = {v}",
            "Максимум неуспешных попыток авторизации = {v}",
            "Допустимое число ошибок входа = {v}",
        ],
    },
    "PASSWORD_LOCK_TIME": {
        "value": lambda: _r(1, 30),
        "phrases": [
            "Время блокировки учётной записи = {v} день",
            "Срок блокировки учётной записи = {v} дней",
            "Период блокировки после превышения попыток = {v} дней",
        ],
    },
    "PASSWORD_LIFE_TIME": {
        "value": lambda: _r(30, 180, 5),
        "phrases": [
            "Срок действия пароля = {v} дней",
            "Время жизни пароля = {v} дней",
            "Период действия пароля = {v} дней",
        ],
    },
    "PASSWORD_GRACE_TIME": {
        "value": lambda: _r(3, 14),
        "phrases": [
            "Льготный период после истечения пароля = {v} дней",
            "Грейс-период смены пароля = {v} дней",
            "Льготный срок после окончания действия пароля = {v} дней",
        ],
    },
    "PASSWORD_REUSE_TIME": {
        "value": lambda: _r(30, 365, 5),
        "phrases": [
            "Запрет на повторное использование пароля в течение {v} дней",
            "Нельзя повторно использовать пароль {v} дней",
            "Минимальный срок до повторного использования пароля = {v} дней",
        ],
    },
    "PASSWORD_REUSE_MAX": {
        "value": lambda: _r(3, 12),
        "phrases": [
            "Запрет на повторное использование последних {v} паролей",
            "Нельзя повторять последние {v} паролей",
            "Запоминать {v} предыдущих паролей",
        ],
    },
}

# ---------------------------------------------------------------------------
# Шаблоны вступительной/общей части (варьируем формулировки)
# ---------------------------------------------------------------------------

UNLOCK_PHRASES = [
    "Разблокируйте пользователя compromised_user.",
    "Снимите блокировку с учётной записи compromised_user.",
    "Разблокируйте заблокированного пользователя compromised_user.",
]

CREDS_PHRASES = [
    "Получите учётные данные из таблицы credentials и выполните вход под ними.",
    "Извлеките логин и пароль из таблицы credentials и подключитесь под этой учётной записью.",
    "Считайте учётные данные из таблицы credentials и войдите под ними.",
]

TS_PHRASES = [
    "Создайте табличное пространство объёмом {sz} МБ с авторасширением и верхним пределом 1 ГБ. Назовите его CTF_TABLESPACE.",
    "Создайте табличное пространство CTF_TABLESPACE размером {sz} МБ с автоматическим расширением и максимумом 1 ГБ.",
    "Создайте табличное пространство на {sz} МБ с авторасширением (предел 1 ГБ) и именем CTF_TABLESPACE.",
]

ROLE_PHRASES = [
    "Создайте роль CTF_ROLE с паролем ctf_role.",
    "Создайте защищённую паролем роль CTF_ROLE (пароль ctf_role).",
]

GRANT_PHRASES = [
    "Выдайте пользователю минимальные привилегии для подключения к базе данных. "
    "Назначьте ему роль CTF_ROLE без установки её по умолчанию. "
    "Предоставьте через эту роль право выборки данных из объекта CTF.CTF_FLAG.",
    "Предоставьте пользователю минимальные права для входа в базу. "
    "Назначьте роль CTF_ROLE, но не делайте её ролью по умолчанию. "
    "Через эту роль выдайте право на чтение объекта CTF.CTF_FLAG.",
]

FLAG_PHRASES = [
    "Под пользователем CTF_STUDENT активируйте роль с использованием её пароля и "
    "получите флаг из объекта CTF.CTF_FLAG.",
    "Войдя как CTF_STUDENT, включите роль её паролем и считайте флаг из CTF.CTF_FLAG.",
]

USER_HEADER_PHRASES = [
    "Создайте пользователя CTF_STUDENT с паролем ctf_student со следующими параметрами:",
    "Создайте учётную запись CTF_STUDENT (пароль ctf_student) с такими параметрами:",
]

PROFILE_HEADER_PHRASES = [
    "Создайте профиль CTF_PROFILE со следующими ограничениями:",
    "Создайте профиль CTF_PROFILE с такими лимитами:",
]

# --- обогащение формулировок (разнообразие стилей -> робастность модели) ---
try:
    import phrasings_aug as _AUG
    _AUG.merge_into(PROFILE_PARAMS)            # +синонимы к параметрам
    UNLOCK_PHRASES = UNLOCK_PHRASES + _AUG.EXTRA_UNLOCK
    CREDS_PHRASES = CREDS_PHRASES + _AUG.EXTRA_CREDS
    TS_PHRASES = TS_PHRASES + _AUG.EXTRA_TS
    ROLE_PHRASES = ROLE_PHRASES + _AUG.EXTRA_ROLE
    PROFILE_HEADER_PHRASES = PROFILE_HEADER_PHRASES + _AUG.EXTRA_PROFILE_HEADER
    USER_HEADER_PHRASES = USER_HEADER_PHRASES + _AUG.EXTRA_USER_HEADER
    GRANT_PHRASES = GRANT_PHRASES + _AUG.EXTRA_GRANT
    FLAG_PHRASES = FLAG_PHRASES + _AUG.EXTRA_FLAG
    _BULLETS = _AUG.BULLET_STYLES
    _USER_STYLES = _AUG.USER_FIELD_STYLES
except Exception:  # noqa: BLE001
    _AUG = None
    _BULLETS = [lambda items: "\n".join(f"— {t};" for t in items)]
    _USER_STYLES = None


# ---------------------------------------------------------------------------
# Генерация одного варианта
# ---------------------------------------------------------------------------

def make_variant(idx, fixed=None):
    """Возвращает (task_text, sql_solution).
    fixed: dict для жёсткого воспроизведения официальных вариантов."""
    if fixed:
        ts_size = fixed["ts_size"]
        quota = fixed["quota"]
        chosen = fixed["profile"]  # list of (oracle_name, value)
    else:
        ts_size = _r(50, 900, 10)
        # квота 40-90% от размера TS, кратно 10, минимум 10
        quota = max(10, int(ts_size * random.uniform(0.4, 0.9)) // 10 * 10)
        n = random.randint(4, 6)
        names = random.sample(list(PROFILE_PARAMS.keys()), n)
        chosen = [(nm, PROFILE_PARAMS[nm]["value"]()) for nm in names]

    # ---- ТЕКСТ ЗАДАНИЯ ----
    lines = [f"Вариант {idx}", ""]
    lines.append(random.choice(UNLOCK_PHRASES))
    lines.append(random.choice(CREDS_PHRASES))
    lines.append("")
    lines.append(random.choice(TS_PHRASES).format(sz=ts_size))
    lines.append("")
    lines.append(random.choice(PROFILE_HEADER_PHRASES))
    items = [random.choice(PROFILE_PARAMS[nm]["phrases"]).format(v=val)
             for nm, val in chosen]
    lines.append(random.choice(_BULLETS)(items))   # рандомный стиль списка
    lines.append("")
    lines.append(random.choice(ROLE_PHRASES))
    lines.append("")
    lines.append(random.choice(USER_HEADER_PHRASES))
    if _USER_STYLES:
        lines.extend(random.choice(_USER_STYLES)(quota))
    else:
        lines.append("— Табличное пространство по умолчанию: CTF_TABLESPACE;")
        lines.append("— Временное табличное пространство: TEMP;")
        lines.append(f"— Квота на использование CTF_TABLESPACE: {quota} МБ;")
        lines.append("— Профиль: CTF_PROFILE;")
        lines.append("— Учётная запись разблокирована.")
    lines.append("")
    lines.append(random.choice(GRANT_PHRASES))
    lines.append("")
    lines.append(random.choice(FLAG_PHRASES))
    task = "\n".join(lines)

    # ---- SQL РЕШЕНИЕ ----
    prof_lines = "\n".join(f"  {nm} {val}" for nm, val in chosen)
    sql = f"""-- 1. Разблокировать скомпрометированного пользователя
ALTER USER compromised_user ACCOUNT UNLOCK;

-- 2. Получить учётные данные и войти под ними
SELECT username, password FROM credentials;
-- CONNECT <username>/<password>   (значения берутся из выборки выше)

-- 3. Табличное пространство CTF_TABLESPACE
CREATE TABLESPACE CTF_TABLESPACE
  DATAFILE 'ctf_tablespace01.dbf'
  SIZE {ts_size}M
  AUTOEXTEND ON NEXT 10M MAXSIZE 1G;

-- 4. Профиль CTF_PROFILE
CREATE PROFILE CTF_PROFILE LIMIT
{prof_lines};

-- 5. Роль CTF_ROLE с паролем
CREATE ROLE CTF_ROLE IDENTIFIED BY ctf_role;

-- 6. Пользователь CTF_STUDENT
CREATE USER CTF_STUDENT IDENTIFIED BY ctf_student
  DEFAULT TABLESPACE CTF_TABLESPACE
  TEMPORARY TABLESPACE TEMP
  QUOTA {quota}M ON CTF_TABLESPACE
  PROFILE CTF_PROFILE
  ACCOUNT UNLOCK;

-- 7. Минимальные привилегии + роль (не по умолчанию) + право через роль
GRANT CREATE SESSION TO CTF_STUDENT;
GRANT SELECT ON CTF.CTF_FLAG TO CTF_ROLE;
GRANT CTF_ROLE TO CTF_STUDENT;
ALTER USER CTF_STUDENT DEFAULT ROLE ALL EXCEPT CTF_ROLE;

-- 8. Под CTF_STUDENT активировать роль паролем и забрать флаг
-- CONNECT CTF_STUDENT/ctf_student
SET ROLE CTF_ROLE IDENTIFIED BY ctf_role;
SELECT * FROM CTF.CTF_FLAG;"""

    return task, sql


# ---------------------------------------------------------------------------
# Три официальных варианта (из Примеры.pdf) — для гарантии покрытия
# ---------------------------------------------------------------------------

OFFICIAL = [
    {  # Вариант 1
        "ts_size": 150, "quota": 80,
        "profile": [
            ("SESSIONS_PER_USER", 4),
            ("IDLE_TIME", 30),
            ("FAILED_LOGIN_ATTEMPTS", 3),
            ("PASSWORD_REUSE_TIME", 60),
            ("PASSWORD_REUSE_MAX", 4),
        ],
    },
    {  # Вариант 2
        "ts_size": 520, "quota": 260,
        "profile": [
            ("SESSIONS_PER_USER", 3),
            ("LOGICAL_READS_PER_SESSION", 130000),
            ("CPU_PER_CALL", 6500),
            ("CONNECT_TIME", 80),
            ("PASSWORD_LIFE_TIME", 28),
            ("PASSWORD_GRACE_TIME", 4),
        ],
    },
    {  # Вариант 3
        "ts_size": 560, "quota": 280,
        "profile": [
            ("IDLE_TIME", 20),
            ("LOGICAL_READS_PER_CALL", 11000),
            ("CPU_PER_SESSION", 32000),
            ("FAILED_LOGIN_ATTEMPTS", 3),
            ("PASSWORD_LOCK_TIME", 1),
            ("SESSIONS_PER_USER", 2),
        ],
    },
]

SYSTEM_PROMPT = (
    "Ты — эксперт по администрированию Oracle Database. "
    "На вход даётся CTF-задание на русском языке. "
    "Выдай корректное и полное SQL-решение для Oracle, "
    "выполняющее все пункты задания по порядку."
)


def to_chat(task, sql):
    return {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": task},
            {"role": "assistant", "content": sql},
        ]
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=1000, help="всего примеров")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default="data")
    ap.add_argument("--valid-frac", type=float, default=0.1)
    ap.add_argument("--test-frac", type=float, default=0.05)
    args = ap.parse_args()

    random.seed(args.seed)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    examples = []

    # официальные варианты — несколько перефразировок каждого, чтобы точно выучил
    for rep in range(8):
        for i, fx in enumerate(OFFICIAL, start=1):
            task, sql = make_variant(i, fixed=fx)
            examples.append(to_chat(task, sql))

    # остальные — случайные
    while len(examples) < args.n:
        idx = random.randint(1, 1000)
        task, sql = make_variant(idx)
        examples.append(to_chat(task, sql))

    random.shuffle(examples)

    n_valid = int(args.n * args.valid_frac)
    n_test = int(args.n * args.test_frac)
    valid = examples[:n_valid]
    test = examples[n_valid:n_valid + n_test]
    train = examples[n_valid + n_test:]

    for name, data in [("train", train), ("valid", valid), ("test", test)]:
        p = out / f"{name}.jsonl"
        with p.open("w", encoding="utf-8") as f:
            for ex in data:
                f.write(json.dumps(ex, ensure_ascii=False) + "\n")
        print(f"{name}: {len(data)} -> {p}")

    # отдельно: 3 официальных варианта как «золотой» тест-набор
    gold = out / "gold_official.jsonl"
    with gold.open("w", encoding="utf-8") as f:
        for i, fx in enumerate(OFFICIAL, start=1):
            task, sql = make_variant(i, fixed=fx)
            f.write(json.dumps(to_chat(task, sql), ensure_ascii=False) + "\n")
    print(f"gold_official: 3 -> {gold}")


if __name__ == "__main__":
    main()
