# 图书资产管理系统

这是一个图书库存管理模板，用于帮助你把“多抓鱼书单 + 手动调价 + 本地/云端报表”串起来。它不要求你一开始就上 GitHub，也不要求你必须做自动定时同步。最推荐的入门路径是：

- 先用纯本地模式跑通
- 再用 GitHub 手动模式备份和同步
- 最后再用 GitHub 定时自动模式实现定时更新

这个仓库本身是公开模板，不存放真实书单；真实数据应保留在私有仓库中。

## 先说结论：三个场景怎么选

### 场景 A：纯本地模式
适合：
- 你还没准备好 GitHub
- 你只是想本地维护一份书单
- 你想先学会同步、手工维护和报表查看

优点：
- 最简单、最容易上手
- 没有 Token / Secret / GitHub Actions
- 适合初学者

### 场景 B：GitHub 手动模式
适合：
- 你想把数据放在 GitHub 上做备份
- 你需要共享或者多机同步
- 你愿意用 GitHub Actions 手动触发同步

优点：
- 代码和 CSV 可备份
- 能在浏览器上查看/回溯
- 能把主表和人工覆盖字段得以长期保存

### 场景 C：GitHub 定时自动模式
适合：
- 你已经跑通手动模式
- 你希望每隔几小时自动更新价格和报表
- 你愿意维护 GitHub Secret 和外部 cron

优点：
- 自动抓取最新价格
- 适合长期运行
- 适合作为个人图书资产管理系统

------------------------------------------------------------

# 目录说明

- `inventory_core.py`：核心逻辑，负责主表合并、状态计算、时间线历史和报表生成
- `auto_sync_data.py`：同步入口脚本，用于处理 JSON / curl / 剪贴板数据
- `auto_fetch.py`：浏览器抓取模式，打开多抓鱼页面并自动抓取响应数据
- `manual_overrides.csv`：人工维护文件，保存你的购入价、售出价、备注、处理标签等
- `inventory_auto.csv`：主库存表，来自抓取结果与 manual 合并后的最终表
- `price_history.csv`：历史价格记录
- `report_auto.html`：总览报表
- `book_detail.html`：单本书详情页
- `override_editor.py`：本地 `manual_overrides.csv` 编辑器
- `override_editor.html`：编辑器页面
- `.github/workflows/scheduled-price-sync.yml`：GitHub Actions 工作流

------------------------------------------------------------

# 关键机制：总表与 manual 的关系

这个项目的核心设计非常重要：

- `inventory_auto.csv` 是“自动生成的总表”
- `manual_overrides.csv` 是“你手工维护的覆盖字段表”
- 新增书籍会自动补入 `manual_overrides.csv`
- `记录ID`、`ISBN`、`书名` 会自动对齐
- 但你的购入价、售出价、备注、处理标签等，通常由你自己填写并保留

也就是说：

- 你不需要手动维护所有书籍的唯一标识
- 你只需要维护真正属于你自己的字段
- 同步脚本不会轻易覆盖你的手工数据

这就是为什么这个项目适合做“自动抓取 + 人工修正”的资产管理系统。

------------------------------------------------------------

# 场景 A：纯本地模式（推荐新手先用）

这个模式最适合第一次上手。

## 1. 安装环境

在项目根目录执行：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip playwright
python -m playwright install chromium
```

如果你已经安装好了 Python 和 Playwright，可以跳过这一步。

## 2. 准备初始数据

这个仓库自带示例数据，但你第一次使用时，建议把示例数据清空成“仅保留表头”的状态。

需要处理的文件：

- `inventory_auto.csv`
- `manual_overrides.csv`
- `price_history.csv`

保留表头即可，删掉示例记录。

## 3. 直接抓取数据

### 方式 1：从 JSON 文件同步

如果你已经拿到 `latest_data.json`：

```bash
python3 auto_sync_data.py latest_data.json
```

### 方式 2：从剪贴板同步

把多抓鱼请求结果复制到剪贴板后：

```bash
python3 auto_sync_data.py
```

### 方式 3：用浏览器自动抓取

```bash
python3 auto_fetch.py
```

这个脚本会：

- 打开浏览器
- 访问多抓鱼卖书页面
- 等待数据返回
- 自动写入 `latest_data.json`
- 运行同步脚本更新总表和报表

## 4. 查看报表

同步成功后，打开：

```bash
open report_auto.html
```

如果你用的是 Linux / 其他环境，可以直接打开该 HTML 文件即可。

## 5. 手工维护购买和售价

本地最方便的做法是启动编辑器：

```bash
python3 override_editor.py
```

默认浏览器会打开：

```text
http://127.0.0.1:8765
```

你可以在这里：

- 编辑 `manual_overrides.csv`
- 修改 `购入价格`
- 修改 `售出价格`
- 修改 `备注`
- 维护 `处理标签`

这部分内容就是你自己的“人工资产信息”，对总表和报表都会产生影响。

## 6. 纯本地模式的优先建议

如果你还没有 GitHub 经验，建议先做到这一步：

- 能抓取多抓鱼数据
- 能更新 `inventory_auto.csv`
- 能打开 `report_auto.html`
- 能用 `override_editor.py` 修改 `manual_overrides.csv`

这就算真正跑通了。

------------------------------------------------------------

# 场景 B：GitHub 手动模式

在纯本地模式跑通后，你可以把数据和脚本放到 GitHub 上进行备份与共享。

## 1. 建一个私有仓库

建议：

- 名称随意，建议类似 `dzy_data` 或你自己的库存仓库名
- 设为私有
- 只保留真实数据，不要公开

## 2. 把这个模板推到私有仓库

你可以：

- 先 clone 这个公开模板仓库
- 修改为自己的私有仓库内容
- 逐步上传 `inventory_auto.csv`、`manual_overrides.csv`、`report_auto.html` 等文件

## 3. 配置 Secret：`DZY_CURL_COMMAND`

这是最关键的 GitHub 配置项。  
它保存的是你用于抓取多抓鱼数据的完整 curl 命令。它通常包含 Cookie / 会话信息，所以它必须放在私有仓库的 Secrets 中，而不能写在公开仓库里。

在 GitHub 仓库里：

- 进入 Settings
- 选择 Secrets and variables
- 选择 Actions
- 新增 `DZY_CURL_COMMAND`

值内容看起来像：

```bash
curl 'https://...' \
  -H 'Cookie: ...' \
  -H 'User-Agent: ...' \
  ...
```

注意：

- 不要把这个值放进公开仓库文件
- 不要把它写进 README 的示例里
- 不要把它提交到公开 git 历史里

## 4. 配置 GitHub Actions 权限

工作流中已经写了：

```yaml
permissions:
  contents: write
```

这意味着 GitHub Actions 可以直接提交更新后的 CSV 和 HTML 文件。

## 5. 手动触发工作流

在 GitHub 页面中：

- 打开 Actions
- 选择 `Scheduled Price Sync`
- 点击 Run workflow / workflow_dispatch

如果你没有设置 `DZY_CURL_COMMAND`，工作流会直接失败。

## 6. 本地手动推送 manual

如果你在本地修改了 `manual_overrides.csv`，可以直接：

```bash
git add manual_overrides.csv
git commit -m "chore: update manual overrides"
git pull --rebase origin main
git push origin main
```

然后你也可以在 GitHub 上手动触发同步工作流，重新生成总表和报表。

如果使用 `override_editor.py`，建议点击“保存 → 推送 → 触发同步”。编辑器会先确认本地和远端已经同步，再触发 GitHub Actions，避免工作流读取旧版 `manual_overrides.csv`。

`git pull --rebase` 的作用是：当远端已经有新的自动同步提交时，把你本地尚未推送的 manual 修改重新接到远端最新提交之后，保持历史线性，减少无意义 merge commit。

PR（Pull Request）适合修改同步脚本、报表逻辑、GitHub Actions 等代码类变更；日常只改自己的书单状态、购入价和备注时，通常直接推送到私有数据仓库的 `main` 更简单。

## 7. GitHub 手动模式的适用建议

这个模式适用于：

- 你要远程备份自己的书单数据
- 你要在多台电脑上协作
- 你想先验证 GitHub Action 能稳定工作

------------------------------------------------------------

# 场景 C：GitHub 定时自动模式

这个模式是长期目标，适合正式投入使用。

## 1. 先确保手动模式正常

在正式开启定时自动前，先确认：

- GitHub Secret `DZY_CURL_COMMAND` 正确
- 工作流能正常触发
- 报表能生成
- `manual_overrides.csv` 不会被错误覆盖

## 2. 外部 cron 定时触发

项目本身没有内置 `schedule`，因为这是公开模板。实现定时通常由外部 cron / 定时任务系统触发 GitHub Actions。

一个典型思路是：

- 每 4 小时触发一次
- 例如：00:00、04:00、08:00、12:00、16:00、20:00
- 触发时调用 GitHub API 调用 workflow_dispatch

示例思路：

```bash
curl -X POST \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  https://api.github.com/repos/OWNER/REPO/actions/workflows/scheduled-price-sync.yml/dispatches \
  -d '{"ref":"main"}'
```

注意：

- 这里的 `YOUR_TOKEN` 是 GitHub token，不是 `DZY_CURL_COMMAND`
- 这条命令通常放在外部定时任务上，而不是仓库里
- 你需要自己保证 token 安全和权限正确

## 3. 需要特别注意的时区

仓库工作流里设置了：

```yaml
TZ: Asia/Shanghai
```

这表示它默认按北京时间处理日志和时间戳。  
如果你在另一个时区运行 cron，需要自己确认触发时间和更新时刻是否符合你的预期。

## 4. 什么时候适合定时自动

建议在以下条件满足后再启用：

- 你已经完成一次手动同步成功
- 你确认总表和 manual 规则没有问题
- 你确认 `DZY_CURL_COMMAND` 仍然有效
- 你已准备好 GitHub token 权限和 cron 任务

## 5. 自动模式的风险

自动模式最大的风险不在脚本本身，而在于：

- Secret 过期
- Cookie 失效
- GitHub 权限错误
- 定时任务触发太频繁
- 新增书籍的人工字段被错误覆盖

一旦这些问题出现，报表可能会“看起来正常，但实际上数据不是你想要的”。

------------------------------------------------------------

# 你应该怎么选择：从 0 到 1 的建议顺序

最稳妥的学习路径是：

## 第一步：纯本地模式

先只做本地：

```bash
python3 auto_fetch.py
python3 override_editor.py
```

目标：

- 能抓数据
- 能更新 CSV
- 能打开报表
- 能维护手工字段

## 第二步：GitHub 手动模式

在本地体验正常后：

- 建私有仓库
- 配置 `DZY_CURL_COMMAND`
- 手动触发 Action
- 观察更新结果

## 第三步：GitHub 定时自动模式

当你对流程非常熟悉以后：

- 配置 cron
- 定时调用 GitHub Actions
- 每 4 小时自动更新

这三种模式是递进关系，不是必须同时做。

------------------------------------------------------------

# 安全注意事项

## 1. 公开模板不能放真实数据

请注意：

- 不要在公开仓库中存放真实书单
- 不要公开真实价格
- 不要公开 `DZY_CURL_COMMAND`
- 不要公开 Cookie / token / session 信息

## 2. 自动抓取比手工编辑更危险

抓取脚本会读取真实的书籍数据，价格和备注也可能包含你不想泄露的内容。  
所以：

- 真实数据一定放私有仓库
- 公开仓库仅保留模板和示例

## 3. `duozhuayu_source.txt` 是临时文件

工作流里会临时写入：

- `duozhuayu_source.txt`

这个文件包含抓取命令内容，属于敏感临时文件，建议忽略它：

```gitignore
duozhuayu_source.txt
```

------------------------------------------------------------

# 常见问题

## 问题 1：为什么 `python3 auto_sync_data.py` 会提示“格式错误”

因为脚本会先尝试读取 JSON 或完整 curl 命令。如果你没有传入有效内容，也没有剪贴板数据，它就会报错。  
这是正常行为，说明脚本正在等待有效输入。

## 问题 2：我改了 `manual_overrides.csv`，为什么总表没变

因为：

- `manual_overrides.csv` 不是最终总表
- 它需要经过同步脚本合并到主表中
- 你需要执行同步脚本或者触发 GitHub Actions

## 问题 3：为什么 GitHub Actions 失败

通常是因为：

- `DZY_CURL_COMMAND` 缺失
- Secret 过期
- 工作流没有写权限
- 目标分支受保护

## 问题 4：浏览器没自动打开编辑器

直接在浏览器中访问：

```text
http://127.0.0.1:8765
```

如果没反应，先确认编辑器程序有没有正常启动。

------------------------------------------------------------

# 最后给你一个最推荐的实操顺序

如果你是第一次使用，我建议这样走：

1. 先用纯本地模式跑通
2. 用 `override_editor.py` 手工维护 `manual_overrides.csv`
3. 在本地确认报表与价格更新正常
4. 才创建私有 GitHub 仓库
5. 再在 GitHub 手动触发工作流
6. 最后才考虑外部 cron 定时自动

这条路径最稳，也最容易避免“装了很多东西却不知道为什么不工作”的情况。

如果你还没建立自己的私有仓库，先不要急着配复杂自动化；先把本地工作流跑通，才是最重要的第一步。
