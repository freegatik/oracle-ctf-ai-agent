#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Генератор НОВЫХ задач для проверки робастности — формулировки НАМЕРЕННО отличаются
от обучающего генератора (generate_dataset.py): другие стили списков (нумерованный,
телеграфный, разговорный), синонимы, иной порядок. Значения и наборы параметров —
случайные. Структура (8 шагов, имена CTF_*) та же (это фикс-формат экзамена).

Возвращает (task_text, expected) где expected = {ts_size, quota, profile:[(name,val)]},
чтобы eval_novel.py мог структурно проверить ответ модели.

НЕ пересекается по фразам с обучающим набором -> честная проверка обобщения.
"""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_dataset import PROFILE_PARAMS  # переиспользуем диапазоны значений

# --- НОВЫЕ формулировки параметров профиля (синонимичные, не из обучения) ---
NOVEL_PHRASES = {
    "SESSIONS_PER_USER": [
        "не больше {v} параллельных сессий одного юзера",
        "потолок одновременных коннектов = {v}",
        "{v} сессий максимум на пользователя",
    ],
    "IDLE_TIME": [
        "сессия висит без дела не дольше {v} мин",
        "простой режь на {v} минутах",
        "неактивность — лимит {v} минут",
    ],
    "CONNECT_TIME": [
        "держать коннект не дольше {v} минут",
        "общее время сессии — потолок {v} мин",
    ],
    "CPU_PER_SESSION": [
        "процессорное время за сессию — до {v}",
        "CPU-бюджет сессии {v}",
    ],
    "CPU_PER_CALL": [
        "на один вызов CPU не выше {v}",
        "процессор на вызов — потолок {v}",
    ],
    "LOGICAL_READS_PER_SESSION": [
        "логических чтений за сессию — не больше {v}",
        "чтений (логических) на сессию максимум {v}",
    ],
    "LOGICAL_READS_PER_CALL": [
        "логических чтений на вызов — до {v}",
        "на вызов логических чтений не более {v}",
    ],
    "FAILED_LOGIN_ATTEMPTS": [
        "после {v} провальных логинов — блок",
        "{v} ошибок входа и аккаунт закрыт",
        "терпим {v} неудачных попыток входа",
    ],
    "PASSWORD_LOCK_TIME": [
        "блок аккаунта на {v} дн после превышения",
        "запирать учётку на {v} суток",
    ],
    "PASSWORD_LIFE_TIME": [
        "пароль живёт {v} дней",
        "срок годности пароля — {v} суток",
    ],
    "PASSWORD_GRACE_TIME": [
        "грейс на смену пароля {v} дней",
        "льгота после протухания пароля — {v} дн",
    ],
    "PASSWORD_REUSE_TIME": [
        "нельзя брать старый пароль {v} дней",
        "повтор пароля запрещён {v} суток",
    ],
    "PASSWORD_REUSE_MAX": [
        "помнить {v} прошлых паролей",
        "последние {v} паролей — табу",
    ],
}

BULLET_STYLES = [
    lambda items: "\n".join(f"{i}) {t}" for i, t in enumerate(items, 1)),  # нумер.
    lambda items: "\n".join(f"* {t}" for t in items),                       # звёзды
    lambda items: "\n".join(f"— {t};" for t in items),                      # тире
    lambda items: "; ".join(items) + ".",                                   # в строку
]

INTROS = [
    "Снимите блокировку с аккаунта compromised_user, затем достаньте пару "
    "логин/пароль из credentials и зайдите под ней.",
    "compromised_user заблокирован — разблокируй. В credentials лежат креды, "
    "прочитай и авторизуйся ими.",
    "Разблокировать compromised_user. Вытащить учётку из credentials, войти.",
]

TS_TMPL = [
    "Заведи табличное пространство CTF_TABLESPACE: старт {sz} МБ, само растёт, потолок 1 ГБ.",
    "CTF_TABLESPACE — {sz} мегабайт на старте, авторасширение до 1 ГБ предел.",
    "Табличное пространство CTF_TABLESPACE объёмом {sz}М, autoextend, максимум гигабайт.",
]

ROLE_TMPL = [
    "Роль CTF_ROLE защити паролем ctf_role.",
    "CTF_ROLE — роль с паролем ctf_role.",
]

USER_TMPL = [
    "Учётка CTF_STUDENT / ctf_student: домашнее таблспейс CTF_TABLESPACE, временное "
    "TEMP, квота {q} МБ на CTF_TABLESPACE, профиль CTF_PROFILE, открыта.",
    "Пользователь CTF_STUDENT (пароль ctf_student): default tablespace CTF_TABLESPACE, "
    "temp TEMP, на CTF_TABLESPACE квота {q}М, профиль CTF_PROFILE, разблокирован.",
]

GRANT_TMPL = [
    "Дай только то, без чего не залогиниться. CTF_ROLE назначь, но не дефолтной. "
    "Через роль открой чтение CTF.CTF_FLAG.",
    "Минимум прав для входа. Роль CTF_ROLE — выдать без default. Через неё SELECT на CTF.CTF_FLAG.",
]

FLAG_TMPL = [
    "Зайдя как CTF_STUDENT, подними роль её паролем и забери флаг из CTF.CTF_FLAG.",
    "Под CTF_STUDENT включи роль паролем, прочитай флаг из CTF.CTF_FLAG.",
]


def make_novel(seed_n: int):
    ts = random.randrange(50, 900, 10)
    quota = max(10, int(ts * random.uniform(0.4, 0.9)) // 10 * 10)
    n = random.randint(4, 6)
    names = random.sample(list(PROFILE_PARAMS), n)
    profile = [(nm, PROFILE_PARAMS[nm]["value"]()) for nm in names]

    items = [random.choice(NOVEL_PHRASES[nm]).format(v=v) for nm, v in profile]
    bullets = random.choice(BULLET_STYLES)(items)

    parts = [
        random.choice(INTROS), "",
        random.choice(TS_TMPL).format(sz=ts), "",
        "Профиль CTF_PROFILE ограничь так:", bullets, "",
        random.choice(ROLE_TMPL), "",
        random.choice(USER_TMPL).format(q=quota), "",
        random.choice(GRANT_TMPL), "",
        random.choice(FLAG_TMPL),
    ]
    task = "\n".join(parts)
    return task, {"ts_size": ts, "quota": quota, "profile": profile}


if __name__ == "__main__":
    random.seed(2026)
    t, e = make_novel(1)
    print(t)
    print("\nEXPECTED:", e)
