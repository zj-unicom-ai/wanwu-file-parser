# Docker 部署

CPU 调度服务 (:8083) 与 GPU/NPU OCR 推理服务 **解耦**，各自独立 compose。CPU 镜像不含 paddleocr/paddlepaddle，OCR 全部走 HTTP。

## 架构

- **CPU 调度服务** (`:8083`)：FastAPI 接收文件、HTTP 调用 OCR API、后处理。**永不 import paddleocr**。
- **OCR 推理服务**：PaddleOCR-VL 官方产线服务 `:8080` + VLM 推理 `:8118`；或 MinerU API `:8000`。

CPU 通过统一 OCR 地址调用远端 OCR（解析优先级：`*_ADDRESS`（完整覆盖） > `OCR_BASE_URL` + `*_API_PATH` > 默认值）：

- PaddleOCR-VL：`PADDLEOCRVL_ADDRESS`（仅 host，client 追加 `/layout-parsing`、`/restructure-pages`）
- MinerU：`MINERU_API_ADDRESS`（**完整端点含 `/file_parse`**，client 直接 POST 不再追加路径）
- 共享 host：`OCR_BASE_URL`（两模型同 host 时设此项，各自拼 `*_API_PATH`）

## Network

The CPU compose file uses an external Docker network named `wanwu-net`. This network must exist before starting the service:

```bash
docker network create wanwu-net 2>/dev/null || true   # skip if already exists
```

For standalone deployment, start your own MinIO + nginx reverse proxy, update `MINIO_ADDRESS` / `MINIO_DOWNLOAD_URL` in `.env`, and change the network from `wanwu-net` to a local bridge network.


## 目录结构

按 **`<模型>-<硬件>`** 组合组织。PaddleOCR-VL 覆盖 9 种硬件，MinerU 覆盖 3 种。

```text
docker/
├── docker-compose.yml                 # 默认：仅 CPU 调度服务 (:8083)，命名卷
├── Dockerfile                         # 纯 CPU 调度镜像（无 paddleocr）
├── .env.example                       # 全局环境变量模板
├── README.md                          # 本文档
│
├── paddleocr-cuda-amd64/              # PaddleOCR-VL × NVIDIA GPU（产线:8080 + VLM:8118）
│   ├── compose.yml                    #   含 build: 块，docker compose build 自建镜像
│   ├── .env.example
│   ├── config/pipeline_config_{vllm,fastdeploy}.yaml   # server_url→:8118
│   ├── pipeline.Dockerfile            # 自建产线镜像
│   └── vlm.Dockerfile                 # 自建 VLM 镜像
├── paddleocr-cuda-sm120-amd64/        # PaddleOCR-VL × NVIDIA SM120 (Blackwell)
├── paddleocr-rocm-amd64/              # PaddleOCR-VL × AMD GPU (ROCm)
├── paddleocr-dcu-amd64/               # PaddleOCR-VL × 海光 DCU
├── paddleocr-ascend910b-arm/          # PaddleOCR-VL × 华为昇腾 910B
├── paddleocr-iluvatar-amd64/          # PaddleOCR-VL × 天数智芯
├── paddleocr-intel-amd64/             # PaddleOCR-VL × Intel GPU
├── paddleocr-kunlunxin-amd64/         # PaddleOCR-VL × 昆仑芯 XPU
├── paddleocr-metax-amd64/             # PaddleOCR-VL × 摩曦 MetaX（默认 fastdeploy）
│
├── mineru-x86-cpu/                    # MinerU × x86 CPU（mineru-api :8000）
├── mineru-cuda-amd64/                 # MinerU × NVIDIA GPU
└── mineru-ascend910b-arm/             # MinerU × 华为昇腾 910B
```

## 快速开始

### 1. 准备配置

```bash
cd docker
cp .env.example .env          # docker 目录下的全局模板：MODEL_TYPE / *_ADDRESS / 存储
vim .env                      # 改 MODEL_TYPE / OCR 地址 / MinIO 等
```

### 2. 部署矩阵

| 角色 | 硬件 | 组合目录 | 端口 |
| --- | --- | --- | --- |
| CPU 服务 | x86 / ARM | `docker/docker-compose.yml` | `:8083` |
| PaddleOCR-VL | NVIDIA GPU | `docker/paddleocr-cuda-amd64/` | 产线 `:8080` + VLM `:8118` |
| PaddleOCR-VL | NVIDIA SM120 | `docker/paddleocr-cuda-sm120-amd64/` | 产线 `:8080` + VLM `:8118` |
| PaddleOCR-VL | AMD GPU (ROCm) | `docker/paddleocr-rocm-amd64/` | 产线 `:8080` + VLM `:8118` |
| PaddleOCR-VL | 海光 DCU | `docker/paddleocr-dcu-amd64/` | 产线 `:8080` + VLM `:8118` |
| PaddleOCR-VL | 昇腾 910B | `docker/paddleocr-ascend910b-arm/` | 产线 `:8080` + VLM `:8118` |
| PaddleOCR-VL | 天数智芯 | `docker/paddleocr-iluvatar-amd64/` | 产线 `:8080` + VLM `:8118` |
| PaddleOCR-VL | Intel GPU | `docker/paddleocr-intel-amd64/` | 产线 `:8080` + VLM `:8118` |
| PaddleOCR-VL | 昆仑芯 XPU | `docker/paddleocr-kunlunxin-amd64/` | 产线 `:8080` + VLM `:8118` |
| PaddleOCR-VL | 摩曦 MetaX | `docker/paddleocr-metax-amd64/` | 产线 `:8080` + VLM `:8118` |
| MinerU | x86 CPU | `docker/mineru-x86-cpu/` | `:8000` |
| MinerU | NVIDIA GPU | `docker/mineru-cuda-amd64/` | `:8000` |
| MinerU | 昇腾 910B | `docker/mineru-ascend910b-arm/` | `:8000` |

### 3. 启动

```bash
# ① 仅 CPU 服务（OCR 在远端，或本机不需要 OCR）
docker compose -f docker/docker-compose.yml up -d --build

# ② CPU + PaddleOCR-VL (NVIDIA GPU) 同机
docker compose -f docker/docker-compose.yml -f docker/paddleocr-cuda-amd64/compose.yml up -d

# ③ CPU + PaddleOCR-VL (昇腾 910B) 同机
docker compose -f docker/docker-compose.yml -f docker/paddleocr-ascend910b-arm/compose.yml up -d

# ④ CPU + MinerU (GPU) 同机（MODEL_TYPE=mineru）
docker compose -f docker/docker-compose.yml -f docker/mineru-cuda-amd64/compose.yml up -d

# ⑤ 跨机部署：GPU/NPU 机单独起 OCR，CPU 机设远端地址后起 CPU 服务
#    PaddleOCR-VL: export PADDLEOCRVL_ADDRESS=http://<ocr-ip>:8080            # 仅 host
#    MinerU:       export MINERU_API_ADDRESS=http://<ocr-ip>:8000/file_parse   # 完整端点含 /file_parse
```

> 同机叠加两个 compose 时，CPU 服务经 Docker 内网以服务名访问 OCR（`http://paddleocr-vl-api:8080`、`http://mineru-api:8000`）。CPU compose 与 OCR 组合分别用独立 bridge 网络，跨机时 CPU 侧改用宿主机 IP。

## 命名卷

CPU compose 用 Docker 命名卷（`wanwu-file-parser-data`、`wanwu-file-parser-logs`）替代宿主机 bind mount —— 无宿主目录耦合、无权限问题、容器重建后数据保留。查看卷：

```bash
docker volume ls | grep wanwu-file-parser
docker volume inspect wanwu-file-parser-data
```

MinerU 组合同样用命名卷（`mineru-models`、`mineru-output`）持久化模型缓存与解析输出，避免重启重下模型。

## PaddleOCR-VL 组合的三点改造（相对官方 accelerators）

每个 `paddleocr-<hardware>/` 组合的 `compose.yml` 在官方 accelerators compose 基础上做三点改造：

1. **VLM `command:` 显式 `--port 8118`**：官方 vlm 镜像 CMD 默认 `--port 8080`，与产线服务 :8080 冲突。统一覆盖为 8118，VLM healthcheck 也用 `:8118`。
2. **产线 `command:` 指向挂载的 config**：`paddlex --serve --pipeline /home/paddleocr/config/pipeline_config_${VLM_BACKEND}.yaml`（从 `./config` 挂载）。
3. **`volumes: ./config:/home/paddleocr/config:ro`**：config 中 `genai_config.server_url` 由官方默认 `:8080` 改为 `http://paddleocr-vlm-server:8118/v1`，使产线 :8080 正确连接 VLM :8118。

各硬件差异仅在镜像 tag、产线 `--device` flag、设备/卷透传（见各 compose 顶部注释）。

### 自建 PaddleOCR 镜像（替代官方预置镜像）

默认直接拉官方预置镜像。如需自定义版面模型/预处理，用 `docker compose build` 自建（各组合 `compose.yml` 内已含 `build:` 块，复用服务 `image:` tag）：

```bash
# 自建 PaddleOCR-VL 产线 + VLM 镜像（NVIDIA GPU 为例）
docker compose -f docker/paddleocr-cuda-amd64/compose.yml build

# 自建后直接 up（优先用本地构建结果，不再拉官方镜像）
docker compose -f docker/paddleocr-cuda-amd64/compose.yml up -d

# 覆盖构建参数：版本、离线模型、VLM 后端
PADDLEOCR_VERSION=">=3.4.0,<3.5" PADDLEX_VERSION=">=3.4.0,<3.5" \
  BUILD_FOR_OFFLINE=true VLM_BACKEND=vllm \
  docker compose -f docker/paddleocr-cuda-amd64/compose.yml build
```

构建参数（见各组合 `.env.example` / `docker/.env.example`）：`PADDLEOCR_VERSION`、`PADDLEX_VERSION`（pip 版本约束）、`BUILD_FOR_OFFLINE`（true 时预下模型到镜像）、`VLM_BACKEND`（vllm | fastdeploy，metax 默认 fastdeploy）。

## CPU 镜像纯度校验

```bash
docker build -f docker/Dockerfile -t wanwu-file-parser:cpu .
docker run --rm wanwu-file-parser:cpu python -c "import app.models.strategy; print('ok')"
docker run --rm wanwu-file-parser:cpu sh -c "pip list | grep -i paddle || echo 'no paddle (correct)'"
```

## 端口

| 端口 | 服务 | 说明 |
| --- | --- | --- |
| 8083 | doc-parser-server | CPU 调度服务（对外） |
| 8080 | paddleocr-vl-api | PaddleOCR-VL 产线服务（`/layout-parsing`、`/health`） |
| 8118 | paddleocr-vlm-server | VLM 推理服务（产线内部调用，CPU 不直连） |
| 8000 | mineru-api | MinerU 文档解析 API 服务 |
