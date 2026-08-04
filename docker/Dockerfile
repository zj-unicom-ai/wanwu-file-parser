# Pure-CPU dispatch image for wanwu-file-parser.
# Never imports paddleocr/paddlepaddle — all OCR is over HTTP to a remote service.
# 基础镜像走国内镜像源前缀(本机 docker.io 直连超时)。
# 实测稳定的源(docker.xuanyuan.me 限流429、docker.1ms.run 断流EOF,仅 daocloud 稳定):
#   - docker.m.daocloud.io  ← 当前使用
#   - docker.1ms.run         (备选,偶发断流)
#   - docker.xuanyuan.me     (备选,限流)
FROM docker.m.daocloud.io/library/python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps: libxml2/libxslt are pulled by beautifulsoup4/lxml wheels; curl
# backs the healthcheck. No LibreOffice/Stirling — Office→PDF conversion is not
# done in this image (use the mineru backend for Office, or supply a PDF/image).
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies first for better layer caching.
COPY pyproject.toml README.md ./
COPY app ./app
RUN pip install --upgrade pip && pip install .

EXPOSE 8083

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8083/rag/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8083"]
