# 安全策略

## 报告安全漏洞

如果您发现 **wanwu-file-parser** 存在安全漏洞，请**不要**在公开 Issue 中提交。

请通过以下方式私下报告：

1. **钉钉群**：加入「万悟文档解析开源交流群」（群号 `201775000578`），私聊维护者
2. **GitHub Security Advisory**：使用 GitHub 的 [安全公告功能](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability) 私下报告

报告时请包含以下信息：

- 漏洞类型（如 SQL 注入、XSS、路径遍历、SSRF 等）
- 受影响的版本/文件
- 复现步骤
- 影响评估
- 建议的修复方案（如有）

## 响应时间

| 阶段 | 目标响应时间 |
|------|-------------|
| 确认收到报告 | 48 小时内 |
| 初步评估 | 7 天内 |
| 修复发布 | 30 天内（高危）/ 90 天内（中低危） |

## 支持的版本

本项目遵循滚动发布模式，仅对最新版本提供安全更新。

## 安全最佳实践

部署本项目时请遵循以下安全实践：

### 1. 密钥管理

- **不要**将 `MINIO_ACCESS_KEY`、`MINIO_SECRET_KEY`、`OSS_ACCESS_KEY`、`OSS_SECRET_KEY` 等密钥硬编码到代码或提交到版本库
- 使用环境变量或 Docker Secrets 管理密钥
- 生产环境请替换 MinIO 默认密钥 `minioadmin/minioadmin`

### 2. 网络隔离

- CPU 调度服务与 OCR 推理服务部署在不同主机或不同网络段
- 仅暴露必要端口（对外仅 `:8083`）
- OCR 推理服务端口（`:8080`、`:8118`、`:8000`）不应对外暴露

### 3. 文件上传安全

- 本项目已实现文件类型白名单校验（`is_allowed_filename`）
- 本项目已实现路径遍历防护（`is_path_traversal`）
- 建议在反向代理层限制上传文件大小
- 建议对上传目录设置 `noexec` 挂载选项

### 4. 日志安全

- 日志中不记录文件内容（仅记录文件名、处理状态、耗时）
- 日志中不记录密钥/Token
- 生产环境建议将日志发送到集中式日志系统

## 依赖安全

本项目使用以下公共镜像源安装依赖：

- **pip**：阿里云 PyPI 镜像（`https://mirrors.aliyun.com/pypi/simple`）
- **apt**：阿里云 Debian 镜像

建议定期运行依赖漏洞扫描：

```bash
pip install pip-audit
pip-audit
```

## 致谢

感谢安全研究人员和社区成员帮助提升本项目的安全性。
