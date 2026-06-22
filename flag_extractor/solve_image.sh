#!/usr/bin/env bash
# ============================================================================
# Универсальный извлекатель флага Oracle-CTF.
# Берёт образ Oracle (любой формат), поднимает БД, запускает ИИ-агента,
# который решает задание и достаёт флаг.
#
# Использование:
#   bash solve_image.sh <ОБРАЗ> --task ЗАДАНИЕ.txt [опции]
#   bash solve_image.sh running --host <IP> --task ЗАДАНИЕ.txt [опции]   # БД уже поднята
#
# Опции подключения (если экзамен-образ отличается от нашего стенда):
#   --host H --port P --service S            (по умолч. localhost 1521 FREEPDB1)
#   --user U --password PW                    привилегированный аккаунт
#   --sysdba                                  вход как sys (режим SYSDBA)
#   --bootstrap-user U --bootstrap-password PW   стартовый аккаунт (эскалация через credentials)
#   --flag-object CTF.CTF_FLAG                имя объекта с флагом
# ============================================================================
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
PROJECT="$(cd "$HERE/.." && pwd)"          # корень проекта (на уровень выше)
PY="$PROJECT/.venv/bin/python"
[ -x "$PY" ] || PY="python3"               # запасной интерпретатор

IMAGE=""; TASK=""
HOST="${ORACLE_HOST:-localhost}"; PORT="${ORACLE_PORT:-1521}"; SVC="${ORACLE_SERVICE:-FREEPDB1}"
ADMIN_USER="${ORACLE_ADMIN_USER:-dba_ctf}"; ADMIN_PW="${ORACLE_ADMIN_PASSWORD:-S3cr3tDBA!}"
BOOT_USER="${ORACLE_BOOTSTRAP_USER:-}"; BOOT_PW="${ORACLE_BOOTSTRAP_PASSWORD:-}"
SYSDBA="${ORACLE_SYSDBA:-0}"; FLAG_OBJ="${CTF_FLAG_OBJECT:-CTF.CTF_FLAG}"
CPW="ctf_admin"; CONTAINER="ctf_exam_oracle"

say(){ echo -e "\n========== $* =========="; }
usage(){ sed -n '2,30p' "$0"; }

while [ $# -gt 0 ]; do
  case "$1" in
    --task) TASK="$2"; shift 2;;
    --host) HOST="$2"; shift 2;;
    --port) PORT="$2"; shift 2;;
    --service) SVC="$2"; shift 2;;
    --user) ADMIN_USER="$2"; shift 2;;
    --password) ADMIN_PW="$2"; shift 2;;
    --sysdba) SYSDBA=1; shift;;
    --bootstrap-user) BOOT_USER="$2"; shift 2;;
    --bootstrap-password) BOOT_PW="$2"; shift 2;;
    --flag-object) FLAG_OBJ="$2"; shift 2;;
    -h|--help) usage; exit 0;;
    *) IMAGE="$1"; shift;;
  esac
done

# ---------- 1. Поднять Oracle из образа ----------
if [ -z "$IMAGE" ] || [ "$IMAGE" = "running" ] || [ "$IMAGE" = "skip" ]; then
  say "Образ не задан — использую уже запущенный Oracle ($HOST:$PORT/$SVC)"
else
  low="$(printf '%s' "$IMAGE" | tr 'A-Z' 'a-z')"
  case "$low" in
    *.tar|*.tar.gz|*.tgz)
      say "Docker-образ (tar): docker load"
      LOADED=$(docker load -i "$IMAGE" 2>/dev/null | sed -n 's/.*Loaded image: //p' | head -1)
      [ -z "$LOADED" ] && LOADED=$(docker images --format '{{.Repository}}:{{.Tag}}' | head -1)
      say "Запуск контейнера из образа: $LOADED"
      docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
      docker run -d --name "$CONTAINER" -p "$PORT:1521" \
        -e ORACLE_PASSWORD="$CPW" -e ORACLE_PWD="$CPW" "$LOADED" >/dev/null
      echo "Контейнер $CONTAINER поднят. Если sys-пароль образа известен — задай --password."
      ;;
    docker:*|*container-registry*)
      REF="${IMAGE#docker:}"
      say "Docker pull: $REF"
      docker pull "$REF"
      docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
      docker run -d --name "$CONTAINER" -p "$PORT:1521" \
        -e ORACLE_PASSWORD="$CPW" -e ORACLE_PWD="$CPW" "$REF" >/dev/null
      ;;
    *.iso|*.ova|*.vmdk|*.qcow2|*.img)
      say "VM/ISO образ — на macOS одной командой не поднять"
      echo "1) Открой образ в UTM (Apple Silicon) или VMware Fusion."
      echo "2) Сеть VM: Bridged или Host-only. Внутри VM узнай IP: ip addr"
      echo "3) Повтори: bash solve_image.sh running --host <IP_VM> --task ... [--user .. --password ..]"
      open -a UTM "$IMAGE" 2>/dev/null || open -a "VMware Fusion" "$IMAGE" 2>/dev/null || true
      exit 2;;
    *.rpm)
      say "RPM (Linux) — НЕ запускается на macOS нативно"
      echo "Вариант А: взять Docker-образ Oracle Free и запустить им."
      echo "Вариант Б: поднять Linux-VM, установить RPM, затем:"
      echo "  bash solve_image.sh running --host <IP> --task ... [creds]"
      exit 2;;
    *.zip)
      say "Windows-образ (.zip) — НЕ запускается на macOS"
      echo "Нужен Windows-хост. После установки: bash solve_image.sh running --host <IP> ..."
      exit 2;;
    *)
      if [ -f "$IMAGE/docker-compose.yml" ] || [ -f "$IMAGE/compose.yml" ]; then
        say "Каталог с docker compose: up -d"
        ( cd "$IMAGE" && docker compose up -d )
      else
        echo "Неизвестный формат образа: $IMAGE"; echo "Поддержка: .tar/.tgz, docker:REF, .iso/.ova/.vmdk, каталог compose."
        exit 2
      fi;;
  esac
fi

# ---------- 2. Ждём готовности Oracle ----------
say "Ожидание готовности Oracle ($HOST:$PORT/$SVC)"
ORACLE_HOST="$HOST" ORACLE_PORT="$PORT" ORACLE_SERVICE="$SVC" \
AUSER="$ADMIN_USER" APW="$ADMIN_PW" BUSER="$BOOT_USER" BPW="$BOOT_PW" SDBA="$SYSDBA" \
  "$PY" "$HERE/wait_oracle.py" || { echo "Oracle не готов — проверь образ/сеть/креды."; exit 1; }

# ---------- 3. Агент решает задание -> флаг ----------
say "Агент извлекает флаг"
# путь к заданию -> абсолютный (до смены каталога)
[ -n "$TASK" ] && [ -f "$TASK" ] && TASK="$(cd "$(dirname "$TASK")" && pwd)/$(basename "$TASK")"
cd "$PROJECT"   # чтобы относительные пути (adapters, data, trajectories) разрешались
export ORACLE_HOST="$HOST" ORACLE_PORT="$PORT" ORACLE_SERVICE="$SVC"
export ORACLE_ADMIN_USER="$ADMIN_USER" ORACLE_ADMIN_PASSWORD="$ADMIN_PW"
export ORACLE_BOOTSTRAP_USER="$BOOT_USER" ORACLE_BOOTSTRAP_PASSWORD="$BOOT_PW"
export ORACLE_SYSDBA="$SYSDBA" CTF_FLAG_OBJECT="$FLAG_OBJ"
if [ -n "$TASK" ]; then
  "$PY" "$PROJECT/scripts/demo.py" --task-file "$TASK"
else
  echo "Вставь текст задания из LMS, затем Ctrl-D:"
  "$PY" "$PROJECT/scripts/demo.py"
fi
