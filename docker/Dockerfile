# Pure-CPU dispatch image for wanwu-file-parser.
# Never imports paddleocr/paddlepaddle — all OCR is over HTTP to a remote service.
# 基础镜像走国内镜像源前缀(本机 docker.io 直连超时)。
# 实测稳定的源(docker.xuanyuan.me 限流429、docker.1ms.run 断流EOF,仅 daocloud 稳定):
#   - docker.m.daocloud.io  ← 当前使用
#   - docker.1ms.run         (备选,偶发断流)
#   - docker.xuanyuan.me     (备选,限流)
FROM docker.m.daocloud.io/library/python:3.12-slim

# 国内镜像源:apt 走阿里云(Debian 默认源实测 23kB/s 极慢),pip 走阿里云 PyPI(pypi.org 已放弃)。
# 基镜像为 Debian 13 trixie,apt 源是 deb822 格式(/etc/apt/sources.list.d/debian.sources),
# sed 把 deb.debian.org → mirrors.aliyun.com 即可(与 DocParserServer legacy Dockerfile 一致)。
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple \
    PIP_TRUSTED_HOST=mirrors.aliyun.com

WORKDIR /app

# System deps: curl backs the healthcheck. No LibreOffice/Stirling — Office→PDF
# conversion is not done in this image (use the mineru backend for Office, or
# supply a PDF/image). 先把 apt 源换成阿里云再 update。
RUN sed -i 's|deb.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Optional: LibreOffice headless for Office→PDF fallback (.doc/.docx/.ppt/.pptx).
# Uncomment to enable local Office conversion. Without this, Office files are
# rejected with a hint to use the mineru backend or supply a PDF/image.
# RUN apt-get update && apt-get install -y --no-install-recommends \
#     libreoffice-core libreoffice-writer libreoffice-impress \
#     && rm -rf /var/lib/apt/lists/*

# Optional: PaddleOCR doc2md for Office→Markdown direct extraction (CPU-only,
# no GPU required). Uncomment to enable. Parses .docx/.pptx XML directly to
# Markdown (headings, tables as HTML, images, math formulas via OMML→LaTeX).
# pip install "paddleocr[doc2md]"

# Install dependencies first for better layer caching. pip 走阿里云 PyPI(见上方 PIP_INDEX_URL)。
COPY pyproject.toml README.md ./
COPY app ./app
RUN pip install --upgrade pip && pip install .

EXPOSE 8083

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8083/rag/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8083"]
