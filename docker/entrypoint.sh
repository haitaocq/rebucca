#!/usr/bin/env sh
# Rebucca 容器入口：数据卷初始化 + 权限兜底后交给 supervisord
set -e

DATA_DIR=/app/db

# 首次启动：数据卷无数据库时，用镜像内预置库初始化（含默认 admin 账号）
if [ ! -f "$DATA_DIR/rebucca.sqlite3" ]; then
    install -o rebucca -g rebucca -m 0644 /app/rebucca.sqlite3 "$DATA_DIR/rebucca.sqlite3"
else
    chown rebucca:rebucca "$DATA_DIR/rebucca.sqlite3"
fi

# 用数据卷内的数据库软链替换镜像副本，保证读写落盘持久化
rm -f /app/rebucca.sqlite3
ln -s "$DATA_DIR/rebucca.sqlite3" /app/rebucca.sqlite3

# 权限兜底（命名卷首次挂载可能继承 root 属主）
chown -R rebucca:rebucca \
    /app/db \
    /app/static/upload \
    /app/static/storage \
    /app/log \
    /app/zlm/bin.x86.gcc9.4 2>/dev/null || true

exec supervisord -c /etc/supervisord.conf
