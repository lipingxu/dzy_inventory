# 图书资产管理系统（公开模板）

这是一个**公开模板仓库**，用于展示图书库存同步与报表流程。  
请不要在本仓库存放真实书单、价格、备注、Cookie 或 Token。

## 1) 推荐使用方式（新用户）

建议使用双仓库：

- **公开仓库**：放这份模板代码（可分享）
- **私有仓库**：放你的真实数据与自动同步（不可公开）

这样可以避免泄露个人书单和交易信息。

## 2) 目录说明

- `auto_sync_data.py`：同步入口（支持 JSON 文件 / curl 文本 / 剪贴板）
- `inventory_core.py`：主逻辑（主表更新、manual 合并、报表生成、历史价格）
- `manual_overrides.csv`：人工维护字段（购入/售出/备注等）
- `price_history.csv`：价格历史
- `report_auto.html`：总览报表
- `book_detail.html`：单书详情页
- `override_editor.py` + `override_editor.html`：本地 manual 编辑器
- `.github/workflows/scheduled-price-sync.yml`：GitHub Actions 手动触发工作流

## 3) 快速开始

### 3.1 环境准备

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip playwright
python -m playwright install chromium
```

### 3.2 清理示例数据（首次使用）

把 `inventory_auto.csv`、`manual_overrides.csv`、`price_history.csv` 清空为仅保留表头，再开始你的私有数据同步。

## 4) 三种同步入口

### A. 用已抓取的 JSON 文件同步

```bash
python3 auto_sync_data.py latest_data.json
```

### B. 用 curl 文本同步（文件里是完整 curl 命令）

```bash
python3 auto_sync_data.py duozhuayu_source.txt
```

### C. 从剪贴板同步（不带参数）

```bash
python3 auto_sync_data.py
```

> 若剪贴板不是有效 JSON/curl，会报“格式错误”，这是预期行为。

## 5) manual 与总表的同步规则

系统会先更新主表，再同步 `manual_overrides.csv`：

- 新书会自动补进 manual
- `记录ID` / `ISBN` / `书名` 会自动对齐
- 人工字段（如购入价、售出价、备注）保留为你填写的值
- manual 中保留的历史购入记录，即使上游列表消失，也会继续保留并合并回主表

## 6) 本地编辑器（改 manual 最方便）

启动：

```bash
python3 override_editor.py
```

默认地址：`http://127.0.0.1:8765`

可选参数：

```bash
python3 override_editor.py --host 127.0.0.1 --port 8765 --no-browser
```

编辑器支持：

- 保存到本地 CSV
- 提交并推送 `manual_overrides.csv`
- 触发 GitHub Actions 同步
- 一键“保存 → 推送 → 触发同步”

## 7) GitHub Actions 与定时触发说明

仓库内工作流目前只有 `workflow_dispatch`（手动触发），没有内置 `schedule`。  
如果你要自动每 4 小时运行，请在外部 cron 系统调用 GitHub API 触发该工作流。

工作流依赖 Secret：

- `DZY_CURL_COMMAND`：完整 curl 命令（高敏感，必须只放在私有仓库）

工作流需要 `contents: write` 才能提交更新后的 CSV/HTML。

## 8) Token 与凭据区别

- **git push 凭据**：用于本地 `git push`
- **`GITHUB_TOKEN` / `GH_TOKEN` 环境变量**：仅用于本地编辑器触发 GitHub Actions API

请不要把长期有效 token 明文写进公开仓库文件。

## 9) 常见问题

- 浏览器未自动打开：手动访问 `http://127.0.0.1:8765`
- 同步失败：检查 `DZY_CURL_COMMAND` 是否有效、是否过期
- Actions 未提交：检查仓库权限是否允许写入，以及分支保护策略

## 10) 安全建议

- 真实数据只放私有仓库
- 公开仓库只保留模板与示例
- 不要公开部署包含真实书单的页面
