#!/usr/bin/env sh
# Rebucca 容器入口：数据卷初始化 + 权限兜底后交给 supervisord
set -e

# 单数据卷 /app/data 下的数据库目录（db/upload/storage/log 统一收敛于此）
DATA_DIR=/app/data/db

# 首次启动：数据卷无数据库时，用镜像内预置库初始化（含默认 admin 账号）
if [ ! -f "$DATA_DIR/rebucca.sqlite3" ]; then
    install -o rebucca -g rebucca -m 0644 /app/rebucca.sqlite3 "$DATA_DIR/rebucca.sqlite3"
else
    chown rebucca:rebucca "$DATA_DIR/rebucca.sqlite3"
fi

# 用数据卷内的数据库软链替换镜像副本，保证读写落盘持久化
rm -f /app/rebucca.sqlite3
ln -s "$DATA_DIR/rebucca.sqlite3" /app/rebucca.sqlite3

# 内置资源（模型权重等）同步进数据卷：仅补齐缺失文件，绝不覆盖用户上传。
# 单卷架构下已有卷会遮蔽镜像内 /app/data/upload 的新增内容，故需在启动时显式同步。
BUILTIN_UPLOAD=/opt/builtin/upload
if [ -d "$BUILTIN_UPLOAD" ]; then
    mkdir -p /app/data/upload
    cp -an "$BUILTIN_UPLOAD/." /app/data/upload/ 2>/dev/null || true
fi

# 权限兜底（命名卷首次挂载可能继承 root 属主；软链本身也一并修正）
chown -h rebucca:rebucca \
    /app/db \
    /app/log \
    /app/static/upload \
    /app/static/storage 2>/dev/null || true
chown -R rebucca:rebucca \
    /app/data \
    /app/zlm/bin.x86.gcc9.4 2>/dev/null || true

exec supervisord -c /etc/supervisord.conf
