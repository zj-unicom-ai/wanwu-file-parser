# wanwu-file-parser

一个**纯 CPU** 的文档解析分发服务。基于 **FastAPI** 构建，采用 MIT 协议。

> **说明：** 本项目默认使用中文 README。英文版本见 [README_EN.md](README_EN.md)。

## 设计

纯 CPU 分发服务（:8083）与 GPU/NPU OCR 模型服务**解耦**。CPU 服务从不导入 `paddleocr`/`paddlepaddle` —— 所有 OCR 都通过 HTTP 调用远端的 PaddleOCR-VL 流水线或 MinerU API 完成。

```
CPU 服务器（含 wanwu 平台）                GPU 服务器（独立 OCR 服务）
┌──────────────────────────────────┐        ┌────────────────────────────────────┐
│ wanwu-file-parser :8083          │  HTTP  │ paddleocr-vl-api :8080 (pipeline)   │
│  FastAPI + 策略（懒加载）          │ ─────▶ │  /layout-parsing + /restructure-pages│
│  PaddleOCRVLClient (HTTP+base64) │        │  (版面 PP-DocLayoutV2 + VLM)        │
│  MineruClient (HTTP multipart)   │        └─────────────────┬──────────────────┘
│  storage (MinIO/OSS)             │                          │ HTTP /v1
│  requirements（无 paddle）        │                          ▼
│  docker/Dockerfile (CPU)         │        ┌────────────────────────────────────┐
└──────────────────────────────────┘        │ paddleocr-vlm-server :8118 (VLM)    │
                                            └────────────────────────────────────┘
```

### 统一的 OCR 寻址

用一组变量取代了历史上具有三重含义的 `MODEL_ADDRESS`。解析优先级（`config.resolve_ocr_endpoint`）：`*_ADDRESS`（完整覆盖）> `OCR_BASE_URL` + `*_API_PATH` > 遗留默认值。

| 变量 | 含义 |
| --- | --- |
| `OCR_BASE_URL` | 共享主机地址（仅 host，可选）。设置后，mineru 会拼接 `MINERU_API_PATH`，paddleocrvl 以其作为 base。 |
| `PADDLEOCRVL_ADDRESS` | PaddleOCR-VL base（仅 host）。客户端会拼接 `PADDLEOCRVL_API_LAYOUT_PARSING_PATH` 和 `…RESTRUCTURE_PAGES_PATH`。 |
| `MINERU_API_ADDRESS` | MinerU 完整端点（含 `/file_parse`）。客户端直接 POST，不拼接任何路径。 |
| `MINERU_API_PATH` | MinerU 端点路径（仅与 `OCR_BASE_URL` 拼接使用）。 |

> 两个客户端的端点契约不同：`MineruClient` 向解析出的完整端点 POST（不拼接路径）；`PaddleOCRVLClient` 使用仅含 host 的 base，并拼接两个 `*_PATH` 子端点。

### PaddleOCR-VL 两阶段 base64 JSON 协议

1. `POST {base}/layout-parsing` —— body 为 `{"file": "<base64>", "fileType": 0|1}`（`0=PDF`，`1=图片含 TIFF`）。
2. `POST {base}/restructure-pages` —— body 为 `{"pages": [...], "concatenatePages": true}` → 拼接后的 markdown + 图片。

图片 key 会被标准化：去掉前导 `imgs/` 前缀，但保留页子目录（`imgs/page1/0.jpg` → `page1/0.jpg`），从而避免多页文档中同名图片冲突。

### Excel（.xlsx/.xls）文本 + 图片分离处理

- 含内嵌图片的 `.xlsx`：单元格文本读取为 markdown 并保留；每张内嵌图片提取到临时文件，发送给 PaddleOCR-VL API 进行识别；结果拼接返回。（绝不整页 OCR 整个表格——那样会丢失表格文本。）
- 不含图片的 `.xlsx`：直接作为 markdown 返回。
- `.xls`：xlrd 将单元格读取为 markdown 表格（与 `.xlsx` 相同），但无法提取内嵌图片——因此 `.xls` 仅返回**文本**（图片丢弃）。没有 PDF/整页 OCR 回退（Stirling-PDF 转换依赖已被移除）。

### Office 文档（.doc/.docx/.ppt/.pptx）

`paddleocrvl` 后端**没有 Office→PDF 转换器**（Stirling-PDF 依赖已移除）。请改上传 PDF/图片，或切换到 `mineru` 后端——后者原生支持 Office 格式。Excel（`.xls/.xlsx`）例外：如上所述直接读取为 markdown。

## 运行

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
# 本地运行时 .env 可选——config 读取环境变量，并提供合理的默认值。
# 模板：docker/.env.example（MODEL_TYPE / *_ADDRESS / storage）。
uvicorn app.main:app --host 0.0.0.0 --port 8083
```

### API

```bash
# 健康检查
curl http://localhost:8083/rag/health

# 解析文档
curl -F 'file_name=demo.pdf' -F 'file=@./demo.pdf' \
  http://localhost:8083/rag/model_parser_file
```

支持上传的格式：`.pdf .png .jpeg .jpg .webp .gif .tif .tiff .bmp .docx .doc .ppt .pptx .xls .xlsx`。

### 测试

```bash
pytest -q
```

## Docker

纯 CPU 镜像（无 paddle）：

```bash
docker compose -f docker/docker-compose.yml up -d --build
```

如需运行 OCR，叠加硬件专用的 compose 文件（PaddleOCR-VL × 9 种硬件组合，MinerU × 3 种）。详见 `docker/README.md`。

## 协议

MIT —— 见 [LICENSE](LICENSE)。
