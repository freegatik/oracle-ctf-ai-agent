# Извлечение флага из образа Oracle — инструкция

Скрипт `solve_image.sh` берёт образ Oracle (любой формат), поднимает СУБД,
запускает дообученного ИИ-агента, который решает задание и достаёт флаг.

Запускать из этой папки. Агент работает на этом Mac, образ — только источник БД.

---

## Быстрый старт (3 шага)

1. **Скопировать образ с флешки** на компьютер (например в `~/Downloads`).
2. **Сохранить текст задания** из LMS в файл `task.txt`.
3. **Одна команда:**
   ```bash
   bash solve_image.sh ~/Downloads/<образ> --task task.txt
   ```
   В конце вывода: `ФЛАГ ПОЛУЧЕН: FLAG{...}` — скопировать в LMS.

---

## По форматам образа (со страницы Oracle Free)

| Формат файла | Команда |
|--------------|---------|
| Docker-образ `*.tar` / `*.tgz` | `bash solve_image.sh образ.tar --task task.txt` |
| Docker из реестра | `bash solve_image.sh docker:container-registry.oracle.com/database/free:latest --task task.txt` |
| Каталог с `docker-compose.yml` | `bash solve_image.sh путь_к_каталогу --task task.txt` |
| VM: `*.iso` `*.ova` `*.vmdk` `*.qcow2` | поднять в UTM/VMware (скрипт подскажет), затем см. «БД уже поднята» |
| RPM (Linux) `*.rpm` | на macOS нативно нельзя — взять Docker-вариант либо Linux-VM |
| Windows `*.zip` | на macOS нельзя — нужен Windows-хост |

### Если БД уже поднята (своя, VM, удалённый хост)
```bash
bash solve_image.sh running --host <IP> --port 1521 --service FREEPDB1 --task task.txt
```

---

## Если образ отличается от нашего стенда (доступ/имена)

Экзамен-образ может иметь другие учётные данные или имена объектов. Доступ узнать
у преподавателя/в LMS, передать флагами:

```bash
# вход известным администратором:
bash solve_image.sh running --task task.txt --user <админ> --password <пароль>

# вход как sys (режим SYSDBA):
bash solve_image.sh running --task task.txt --user sys --password <пароль> --sysdba

# дан только стартовый аккаунт -> агент сам прочитает credentials и переподключится:
bash solve_image.sh running --task task.txt \
     --bootstrap-user <юзер> --bootstrap-password <пароль>

# иное имя объекта с флагом / сервиса:
bash solve_image.sh running --task task.txt --flag-object CTF.CTF_FLAG --service FREE
```

Все опции:
`--host --port --service --user --password --sysdba --bootstrap-user --bootstrap-password --flag-object`

---

## Как это работает внутри
1. **Поднятие БД** — по формату: `docker load`+`run`, `docker pull`+`run`,
   `docker compose up`, либо подсказка для VM/ISO.
2. **Ожидание готовности** — `wait_oracle.py` опрашивает listener, пока БД не примет
   соединение (или не вернёт ошибку авторизации = БД уже поднята).
3. **Решение** — `scripts/demo.py`: модель генерирует SQL, агент выполняет его в Oracle
   по шагам, восстанавливается после ошибок, под `CTF_STUDENT` активирует роль и читает флаг.
   При неудаче детерминированного прогона включается резервный повтор со сэмплингом.

---

## Если флаг не получен — короткий чеклист
- `ORA-12541/TNS` — БД ещё поднимается или неверный host/port. Подождать/проверить сеть.
- `ORA-01017` — неверные креды. Уточнить `--user/--password` (возможно нужен `--sysdba`).
- `ORA-00942` — другое имя объекта флага. Указать `--flag-object <схема.таблица>`.
- Долгая «загрузка модели» при первом запуске (~60с) — норма, повтор быстрее.
- Прогрев заранее: `.venv/bin/python scripts/demo.py --variant 1` (на своём стенде).
