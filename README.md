# wanwu-file-parser

A **CPU-only** document parsing dispatch service. MIT-licensed. Built with **FastAPI**.

A clean, independent reimplementation (FastAPI, MIT) of the document-parsing dispatch architecture described in the upstream `AGENTS.md` 「改造技术方案」.

## Design

The pure-CPU dispatch service (:8083) is **decoupled** from the GPU/NPU OCR model service. The CPU service never imports `paddleocr`/`paddlepaddle` — all OCR happens over HTTP to a remote PaddleOCR-VL pipeline or MinerU API.

```
CPU server (with wanwu platform)            GPU server (independent OCR service)
┌──────────────────────────────────┐        ┌────────────────────────────────────┐
│ wanwu-file-parser :8083          │  HTTP  │ paddleocr-vl-api :8080 (pipeline)   │
│  FastAPI + strategy (lazy)       │ ─────▶ │  /layout-parsing + /restructure-pages│
│  PaddleOCRVLClient (HTTP+base64) │        │  (layout PP-DocLayoutV2 + VLM)       │
│  MineruClient (HTTP multipart)   │        └─────────────────┬──────────────────┘
│  storage (MinIO/OSS)             │                          │ HTTP /v1
│  requirements (no paddle)        │                          ▼
│  docker/Dockerfile (CPU)         │        ┌────────────────────────────────────┐
└──────────────────────────────────┘        │ paddleocr-vlm-server :8118 (VLM)    │
                                            └────────────────────────────────────┘
```

### Unified OCR addressing

One set of variables replaces the historical triple-meaning `MODEL_ADDRESS`. Resolution priority (`config.resolve_ocr_endpoint`): `*_ADDRESS` (full override) > `OCR_BASE_URL` + `*_API_PATH` > legacy default.

| Variable | Meaning |
| --- | --- |
| `OCR_BASE_URL` | Shared host (host only, optional). When set, mineru appends `MINERU_API_PATH`, paddleocrvl uses it as base. |
| `PADDLEOCRVL_ADDRESS` | PaddleOCR-VL base (host only). Client appends `PADDLEOCRVL_API_LAYOUT_PARSING_PATH` and `…RESTRUCTURE_PAGES_PATH`. |
| `MINERU_API_ADDRESS` | MinerU full endpoint (incl. `/file_parse`). Client POSTs directly, appends nothing. |
| `MINERU_API_PATH` | MinerU endpoint path (only joined with `OCR_BASE_URL`). |

> The two clients have different endpoint contracts: `MineruClient` POSTs to the resolved full endpoint (no path append); `PaddleOCRVLClient` uses a host-only base and appends the two `*_PATH` sub-endpoints.

### PaddleOCR-VL two-stage base64 JSON protocol

1. `POST {base}/layout-parsing` — body `{"file": "<base64>", "fileType": 0|1}` (`0=PDF`, `1=image incl. TIFF`).
2. `POST {base}/restructure-pages` — body `{"pages": [...], "concatenatePages": true}` → concatenated markdown + images.

Image keys are normalized by stripping the leading `imgs/` prefix while keeping the page subdirectory (`imgs/page1/0.jpg` → `page1/0.jpg`), so multi-page documents with same-name images never collide.

### Excel (.xlsx/.xls) text + image split

- `.xlsx` with embedded images: cell text is read to markdown and kept; each embedded image is extracted to a temp file and sent to the PaddleOCR-VL API for recognition; results are concatenated. (Never full-page-OCR the whole sheet — that loses table text.)
- `.xlsx` without images: returned directly as markdown.
- `.xls`: xlrd reads the cells into a markdown table (same as `.xlsx`), but cannot extract embedded images — so `.xls` returns **text only** (images dropped). There is no PDF/full-page-OCR fallback (the Stirling-PDF conversion dependency was removed).

### Office documents (.doc/.docx/.ppt/.pptx)

The `paddleocrvl` backend has **no Office→PDF converter** (Stirling-PDF dependency removed). Upload a PDF/image instead, or switch to the `mineru` backend — which handles Office formats natively. Excel (`.xls/.xlsx`) is exempt: it is read directly into markdown as described above.

## Run

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
# .env optional for local runs — config reads env vars with sane defaults.
# Template: docker/.env.example (MODEL_TYPE / *_ADDRESS / storage).
uvicorn app.main:app --host 0.0.0.0 --port 8083
```

### API

```bash
# Health
curl http://localhost:8083/rag/health

# Parse a document
curl -F 'file_name=demo.pdf' -F 'file=@./demo.pdf' \
  http://localhost:8083/rag/model_parser_file
```

Supported uploads: `.pdf .png .jpeg .jpg .webp .gif .tif .tiff .bmp .docx .doc .ppt .pptx .xls .xlsx`.

### Test

```bash
pytest -q
```

## Docker

CPU-only image (no paddle):

```bash
docker compose -f docker/docker-compose.yml up -d --build
```

To run OCR, overlay a hardware-specific compose (PaddleOCR-VL × 9 hardware combos, MinerU × 3). See `docker/README.md`.

## License

MIT — see [LICENSE](LICENSE).
