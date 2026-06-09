#!/usr/bin/env bash
set -euo pipefail

CONFIG_DIR="${APP_CONFIG_DIR:-/app/config}"  # 可用 env 覆盖
BACKUP_IN_IMAGE="/app/config.ini.backup"     # 镜像内的备份文件

echo "[entrypoint] Using CONFIG_DIR=${CONFIG_DIR}"
mkdir -p "${CONFIG_DIR}"

# 1) 如果宿主机映射目录中没有 config.ini.backup，就从镜像备份复制一份
if [ ! -f "${CONFIG_DIR}/config.ini.backup" ] && [ -f "${BACKUP_IN_IMAGE}" ]; then
  echo "[entrypoint] Seeding config.ini.backup into mounted config dir..."
  cp -n "${BACKUP_IN_IMAGE}" "${CONFIG_DIR}/config.ini.backup"
fi

# 2) 如果没有 config.ini，就用当前目录里的 backup 生成（优先用宿主机里的那份）
if [ ! -f "${CONFIG_DIR}/config.ini" ] && [ -f "${CONFIG_DIR}/config.ini.backup" ]; then
  echo "[entrypoint] Creating config.ini from config.ini.backup..."
  cp -n "${CONFIG_DIR}/config.ini.backup" "${CONFIG_DIR}/config.ini"
fi

# 你之前的数据库迁移等步骤（可选）
echo "[entrypoint] Running migrations..."
python manage.py migrate --noinput || true

echo "[entrypoint] Starting app: $*"
exec "$@"
