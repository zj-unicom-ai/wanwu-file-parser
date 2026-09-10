# 贡献指南

感谢您对 **wanwu-file-parser** 项目的关注！欢迎提交 Issue、Pull Request 参与共建。

## 开发环境准备

```bash
# 1. 克隆仓库
git clone <repo-url>
cd wanwu-file-parser

# 2. 创建虚拟环境（Python >= 3.10）
python -m venv .venv
source .venv/bin/activate

# 3. 安装开发依赖（含 pytest、httpx 等测试工具）
pip install -e ".[dev]"
```

## 代码规范

本项目使用 [ruff](https://docs.astral.sh/ruff/) 进行代码风格检查和格式化。

```bash
# 检查代码风格
ruff check app/ tests/

# 自动格式化
ruff format app/ tests/
```

提交前请确保 `ruff check` 和 `ruff format --check` 均通过。

## 提交 Pull Request

1. **Fork** 本仓库并创建特性分支：
   ```bash
   git checkout -b feat/your-feature
   ```

2. **编写代码**，确保：
   - 通过 `ruff check` 和 `ruff format --check`
   - 通过全部测试：`pytest tests/ -v`
   - 新功能有对应的测试覆盖

3. **提交**（建议遵循 [Conventional Commits](https://www.conventionalcommits.org/)）：
   ```bash
   git commit -m "feat: add xxx support"
   git commit -m "fix: resolve yyy issue"
   git commit -m "docs: update zzz"
   ```

4. **推送并发起 PR**，在 PR 描述中说明：
   - 本次变更的目的
   - 涉及的模块
   - 是否需要更新文档

## 测试

```bash
# 运行全部测试
pytest tests/ -v

# 运行单个测试文件
pytest tests/test_api.py -v
```

## Issue 提交

提交 Issue 时请包含以下信息：

- **环境信息**：操作系统、Python 版本、Docker 版本
- **复现步骤**：尽可能详细
- **预期行为** vs **实际行为**
- **日志输出**（如有）

## 项目结构

```
wanwu-file-parser/
├── app/                    # 主应用代码
│   ├── api.py              # FastAPI 路由
│   ├── config.py           # 配置（pydantic-settings）
│   ├── main.py             # 应用入口
│   ├── models/             # OCR 客户端（MinerU / PaddleOCR-VL）
│   ├── services/           # 解析编排、Excel、文件服务
│   └── utils/              # 日志、监控、存储抽象
├── tests/                  # 测试套件
├── docker/                 # Docker 部署（CPU + 各硬件 OCR 组合）
├── .github/workflows/      # GitHub Actions CI
├── pyproject.toml          # 项目元数据与依赖
├── README.md               # 中文文档
└── README_EN.md            # English documentation
```

## 许可证

本项目采用 [MIT License](LICENSE)。提交的代码将自动以同一许可证发布。

## 联系方式

- **Issue**：[GitHub Issues](../../issues)
- **钉钉群**：「万悟文档解析开源交流群」群号 `201775000578`
