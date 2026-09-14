# wanwu-file-parser

一个**纯 CPU** 的文档解析分发服务，与ocr模型解耦，可以分离部署。基于 **FastAPI** 构建，采用 MIT 协议。

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

| 变量                    | 含义                                                                                                                |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------- |
| `OCR_BASE_URL`        | 共享主机地址（仅 host，可选）。设置后，mineru 会拼接`MINERU_API_PATH`，paddleocrvl 以其作为 base。                |
| `PADDLEOCRVL_ADDRESS` | PaddleOCR-VL base（仅 host）。客户端会拼接`PADDLEOCRVL_API_LAYOUT_PARSING_PATH` 和 `…RESTRUCTURE_PAGES_PATH`。 |
| `MINERU_API_ADDRESS`  | MinerU 完整端点（含`/file_parse`）。客户端直接 POST，不拼接任何路径。                                             |
| `MINERU_API_PATH`     | MinerU 端点路径（仅与`OCR_BASE_URL` 拼接使用）。                                                                  |

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

Office 文档支持**三种处理模式**，通过环境变量 `OFFICE_PROCESSING_MODE` 切换：

| 模式               | 说明                                                                     | 依赖                                |
| ------------------ | ------------------------------------------------------------------------ | ----------------------------------- |
| `auto`（默认）   | 先试`doc2md` 直取（CPU，无需 GPU），失败回退 `LibreOffice→PDF→OCR` | 两者可选                            |
| `direct_extract` | 仅用`doc2md` 直取 Markdown（无 OCR 推理、无 GPU）                      | `pip install "paddleocr[doc2md]"` |
| `convert_pdf`    | 仅用`LibreOffice→PDF→OCR`（传统路径）                                | `apt-get install libreoffice-*`   |

**`doc2md` 直取模式**（`direct_extract` / `auto`）利用 PaddleOCR 内置的 `doc2md` 功能，直接解析 Office 文档 XML 为 Markdown——**无需 OCR 推理、无需 GPU**。支持 `.docx`（Word）、`.pptx`（PowerPoint）；不支持 `.doc`/`.ppt` 旧格式。

**`convert_pdf` 模式**通过 LibreOffice headless 将 Office 转为 PDF，再走 OCR 流水线。支持 `.doc/.docx/.ppt/.pptx` 全部格式。

Dockerfile 中已预留两个可选安装层（默认注释），按需取消注释：

```dockerfile
# 方式一：LibreOffice→PDF→OCR（convert_pdf / auto 回退）
# RUN apt-get update && apt-get install -y --no-install-recommends \
#     libreoffice-core libreoffice-writer libreoffice-impress \
#     && rm -rf /var/lib/apt/lists/*

# 方式二：doc2md 直取 Markdown（direct_extract / auto 首选）
# pip install "paddleocr[doc2md]"
```

Excel（`.xls/.xlsx`）例外：如上所述直接读取为 markdown，不走 Office 处理路径。

## Docker 部署（推荐）

CPU 调度服务（`:8083`）与 GPU/NPU OCR 推理服务**解耦**，各自独立 compose。CPU 镜像不含 `paddleocr`/`paddlepaddle`，OCR 全部走 HTTP。架构与 OCR 寻址详见上方[设计](#设计)部分。

### 快速开始

#### 1. 仅 CPU 服务（OCR 在远端，或本机不需要 OCR）

```bash
docker compose -f docker/docker-compose.yml up -d --build
```

#### 2. CPU + PaddleOCR-VL 同机（NVIDIA GPU）

```bash
docker compose \
  -f docker/docker-compose.yml \
  -f docker/paddleocr-cuda-amd64/compose.yml \
  up -d
```

#### 3. CPU + MinerU 同机（GPU）

```bash
docker compose \
  -f docker/docker-compose.yml \
  -f docker/mineru-cuda-amd64/compose.yml \
  up -d
```

#### 4. 跨机部署

GPU/NPU 机单独起 OCR，CPU 机设远端地址后起 CPU 服务：

```bash
# PaddleOCR-VL: export PADDLEOCRVL_ADDRESS=http://<ocr-ip>:8080            # 仅 host
# MinerU:       export MINERU_API_ADDRESS=http://<ocr-ip>:8000/file_parse   # 完整端点含 /file_parse
docker compose -f docker/docker-compose.yml up -d --build
```

### 部署矩阵

| 角色         | 硬件           | 组合目录                             | 端口                          |
| ------------ | -------------- | ------------------------------------ | ----------------------------- |
| CPU 服务     | x86 / ARM      | `docker/docker-compose.yml`        | `:8083`                     |
| PaddleOCR-VL | NVIDIA GPU     | `docker/paddleocr-cuda-amd64/`     | 产线`:8080` + VLM `:8118` |
| PaddleOCR-VL | AMD GPU (ROCm) | `docker/paddleocr-rocm-amd64/`     | 产线`:8080` + VLM `:8118` |
| PaddleOCR-VL | 昇腾 910B      | `docker/paddleocr-ascend910b-arm/` | 产线`:8080` + VLM `:8118` |
| MinerU       | x86 CPU        | `docker/mineru-x86-cpu/`           | `:8000`                     |
| MinerU       | NVIDIA GPU     | `docker/mineru-cuda-amd64/`        | `:8000`                     |

> 完整硬件组合（9 种 PaddleOCR-VL + 3 种 MinerU）见 `docker/README.md`。

### 端口

| 端口 | 服务                 | 说明                                                      |
| ---- | -------------------- | --------------------------------------------------------- |
| 8083 | doc-parser-server    | CPU 调度服务（对外）                                      |
| 8080 | paddleocr-vl-api     | PaddleOCR-VL 产线服务（`/layout-parsing`、`/health`） |
| 8118 | paddleocr-vlm-server | VLM 推理服务（产线内部调用，CPU 不直连）                  |
| 8000 | mineru-api           | MinerU 文档解析 API 服务                                  |

## 本地运行

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

## 交流群

欢迎加入钉钉群「**万悟文档解析开源交流群**」参与讨论、反馈问题。

- **钉钉群号：** `201775000578`
- **群二维码：**

![钉钉群二维码](assets/群二维码-20260908-195128.png)

## 治理

- [贡献指南](CONTRIBUTING.md)
- [安全策略](SECURITY.md)
- [贡献者公约](CODE_OF_CONDUCT.md)

## 协议

MIT —— 见 [LICENSE](LICENSE)。
