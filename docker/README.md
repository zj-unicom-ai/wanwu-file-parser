# Docker deployment

The CPU dispatch service (:8083) is **decoupled** from the GPU/NPU OCR service. The default compose starts only the CPU service (no paddleocr in the image). OCR runs as a separate HTTP service (PaddleOCR-VL pipeline or MinerU API) and is addressed via `PADDLEOCRVL_ADDRESS` / `MINERU_API_ADDRESS` / `OCR_BASE_URL`.

## CPU service only (no GPU)

```bash
cp .env.example .env          # edit MODEL_TYPE / *_ADDRESS / storage
docker compose -f docker/docker-compose.yml up -d --build
curl -f http://localhost:8083/rag/health
```

## CPU + remote OCR (same host or cross-host)

Set the OCR endpoint(s) in `.env`:

- PaddleOCR-VL: `PADDLEOCRVL_ADDRESS=http://<gpu-ip>:8080` (host only; client appends `/layout-parsing` + `/restructure-pages`).
- MinerU: `MINERU_API_ADDRESS=http://<mineru-ip>:8000/file_parse` (full endpoint; client POSTs directly).
- Shared host: `OCR_BASE_URL=http://<ocr-host>:8000` + the per-model `*_API_PATH`.

Then start only the CPU compose; the OCR service runs independently (official PaddleOCR-VL images or `mineru-api`).

## Hardware-specific OCR compose overlays

To co-locate OCR on the same Docker host, overlay a hardware combo compose (PaddleOCR-VL covers 9 hardware combos, MinerU covers 3 — modeled on the upstream 改造技术方案 matrix):

```bash
# CPU + PaddleOCR-VL (NVIDIA GPU)
docker compose -f docker/docker-compose.yml -f docker/paddleocr-cuda-amd64/compose.yml up -d
# CPU + MinerU (GPU)
docker compose -f docker/docker-compose.yml -f docker/mineru-cuda-amd64/compose.yml up -d
```

Each hardware combo directory contains its own `compose.yml` + `.env.example` + (for PaddleOCR) `config/` pipeline yaml with `server_url` pointing at the VLM :8118. See the upstream `AGENTS.md` §六 matrix for the full hardware list.

## CPU image purity

```bash
docker build -f docker/Dockerfile -t wanwu-file-parser:cpu .
docker run --rm wanwu-file-parser:cpu python -c "import app.models.strategy; print('ok')"
docker run --rm wanwu-file-parser:cpu sh -c "pip list | grep -i paddle || echo 'no paddle (correct)'"
```
