# 图书资产管理系统（公开模板版）

## 说明

这是一个公开模板仓库，用于展示图书资产管理系统的结构、脚本、同步流程和报表格式。

本仓库不保存真实图书数据。真实数据应保留在私有仓库：

- `lipingxu/dzy_data`

这样可以避免在公开仓库中暴露个人书单、购入价格、售出记录、备注和私有访问信息。

## 结构说明

- `inventory_core.py`：核心逻辑，负责 CSV 合并、状态重算、历史记录和报表生成
- `auto_sync_data.py`：同步入口脚本，用于处理抓取结果并更新主数据
- `manual_overrides.csv`：手工覆盖文件，保留你自己的购入价、售出价、状态和备注
- `price_history.csv`：历史价格日记
- `report_auto.html`：主报表页面
- `book_detail.html`：书籍详情页
- `.github/workflows/scheduled-price-sync.yml`：GitHub Actions 自动同步工作流
- `backups/`：同步前备份目录

## 生产环境推荐架构

推荐使用双仓库模型：

1. 私有仓库：保存真实数据，进行自动同步与部署
2. 公开仓库：保留示例/模板代码，供共享、展示和复用

## 自动同步方式

当前生产环境仍使用以下链路：

- 外部 cronjob 触发 GitHub Actions
- GitHub Actions 读取 `DZY_CURL_COMMAND`
- 拉取多抓鱼数据并更新 CSV / HTML
- 将内容提交到私有仓库
- 使用 Cloudflare Pages 进行私有页面部署
- Cloudflare Access 限制访问权限

## 私有化部署注意事项

如果你想在真实环境中使用，请在私有仓库中配置：

- `DZY_CURL_COMMAND`
- GitHub Actions 运行权限
- Cloudflare Pages 项目
- Cloudflare Access 允许邮箱列表

## 模板使用建议

如果你是从这个公开模板复制出来使用：

- 先清空 `inventory_auto.csv` 和 `manual_overrides.csv`
- 保留表头即可
- 在自己的私有仓库里配置真实的抓取命令和访问权限
- 运行同步后再开始维护自己的书单

## 免责声明

这个仓库仅用于代码示例和模板复用，不能直接替代真实的私有数据仓库。

若要部署真实的书单系统，请使用 `dzy_data` 私有仓库作为数据源，并保持公开模板仓库无真实数据。
