# syntax=docker/dockerfile:1
# =============================================================================
# Rebucca 单镜像：Django 应用 + ZLMediaKit + FFmpeg（仅 OnnxRuntime，CPU 推理）
# 构建: docker build -t rebucca:1.002 .
# 运行: docker compose up -d
# 优化点:
#   - 多阶段构建：编译工具与运行时隔离
#   - 静态 FFmpeg 替代 apt 版（476MB 编码库 → 单二进制 ~75MB，省 ~400MB）
#   - opencv-python-headless：无 GUI 依赖（省 ~79MB + 系统库）
#   - 删除 onnxruntime 拖入的 sympy/mpmath（仅量化工具用，推理不需要，省 79MB）
#   - 删除 venv 中 pip/wheel 与 __pycache__（运行时不需要）
#   - COPY --chown 一次完成属主设置，消除重复 chown 层（省 ~75MB）
#   - 非 root 运行 + tini 作为 PID1
# =============================================================================

########## Stage 0: 静态 FFmpeg（仅 ffmpeg 二进制，含 libx264） ##########
FROM debian:bookworm-slim AS ffmpeg
RUN apt-get update \
    && apt-get install -y --no-install-recommends xz-utils ca-certificates wget \
    && wget -q -O /ffmpeg.tar.xz https://github.com/BtbN/FFmpeg-Builds/releases/latest/download/ffmpeg-master-latest-linux64-gpl.tar.xz \
    && mkdir -p /opt/ffmpeg \
    && tar -xJf /ffmpeg.tar.xz -C /opt/ffmpeg --strip-components=1 \
    && rm -f /ffmpeg.tar.xz \
    && apt-get purge -y --auto-remove xz-utils wget \
    && rm -rf /var/lib/apt/lists/*

########## Stage 1: Python 依赖 ##########
FROM python:3.11-slim-bookworm AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONUNBUFFERED=1

# 个别包无 manylinux wheel 时兜底编译（本阶段工具不进入最终镜像）
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY docker/requirements.txt .

RUN python -m venv /opt/venv \
    && . /opt/venv/bin/activate \
    && pip install -r requirements.txt \
    # 运行时瘦身：移除 pip/wheel 与 onnxruntime 冗余依赖 sympy/mpmath（仅量化工具需要）
    && rm -rf /opt/venv/lib/python3.11/site-packages/pip* \
             /opt/venv/lib/python3.11/site-packages/wheel* \
             /opt/venv/lib/python3.11/site-packages/sympy* \
             /opt/venv/lib/python3.11/site-packages/mpmath* \
             /opt/venv/bin/pip* \
             /opt/venv/bin/wheel* \
    && find /opt/venv -name '__pycache__' -type d -exec rm -rf {} + \
    && find /opt/venv \( -name '*.pyc' -o -name '*.pyo' \) -delete

########## Stage 2: 运行镜像 ##########
FROM python:3.11-slim-bookworm AS runtime

# 精简 apt 依赖：不再装 apt 版 ffmpeg（改静态）与 libgl1（headless）
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libglib2.0-0 \
        libgomp1 \
        libsrtp2-1 \
        tini \
        ca-certificates \
        locales \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv
COPY --from=ffmpeg /opt/ffmpeg/bin/ffmpeg /usr/local/bin/ffmpeg

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    # 让 ZLM 使用自带的 libssl1.1/libcrypto/libsrtp2（宿主无需再装 openssl 1.1）
    LD_LIBRARY_PATH="/app/zlm/bin.x86.gcc9.4" \
    # 单进程模式运行 runserver（容器内无文件热更新），RUN_MAIN=true 触发后台服务自举
    RUN_MAIN="true"

# 非 root 运行（uid 1000）；--chown 一次完成属主，避免额外 chown 层
RUN useradd --create-home --uid 1000 rebucca

WORKDIR /app
# --exclude 排除 static/upload：权重后续单独 COPY 到数据目录，避免跨层重复
COPY --chown=1000:1000 --exclude=static/upload . .

# ZLM 工作目录可写（快照/转码输出）
RUN mkdir -p /app/zlm/bin.x86.gcc9.4/www \
    && chown -R 1000:1000 /app/zlm/bin.x86.gcc9.4

# 数据目录整合：db/upload/storage/log 统一收敛到 /app/data 单卷，
# 原应用路径以软链保留（代码路径不变，写操作透明落入 /app/data）
RUN mkdir -p /app/data/db /app/data/log /app/data/storage /app/data/upload \
    && ln -s /app/data/upload /app/static/upload \
    && ln -s /app/data/storage /app/static/storage \
    && ln -s /app/data/db /app/db \
    && ln -s /app/data/log /app/log \
    && chown -R 1000:1000 /app/data

# 内置资源（模型权重等）放到非挂载路径，入口脚本再同步进数据卷。
# 原因：/app/data 是命名卷挂载点，已存在的卷会遮蔽镜像内该目录的新增内容，
# 直接 COPY 到 /app/data/upload 只能对“空卷首次创建”生效，升级时无法补入新模型。
COPY --chown=1000:1000 static/upload /opt/builtin/upload

COPY docker/entrypoint.sh /usr/local/bin/rebucca-entrypoint
RUN chmod +x /usr/local/bin/rebucca-entrypoint

COPY docker/supervisord.conf /etc/supervisord.conf

# Web / ZLM 各端口 / SIP
EXPOSE 10001 10002 10554 10935 30001 15060/udp

# 持久化数据卷（db/upload/storage/log 统一收敛于此单卷）
VOLUME ["/app/data"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:10001/login',timeout=3).status==200 else 1)"]

ENTRYPOINT ["tini", "--", "/usr/local/bin/rebucca-entrypoint"]
