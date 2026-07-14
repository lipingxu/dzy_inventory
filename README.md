# 图书资产管理系统 (Inventory Management System)

## 项目简介
该系统已从单纯的价格追踪器升级为专业的**图书资产财务管理系统**。它不仅能记录购入/售出记录，还能通过多抓鱼行情实时计算资产总额、浮动盈亏，并提供可视化的资产走势图。

## 核心功能升级 (2026-05-28)

### 1. 财务级报表看板
*   **多维指标**: 实时统计“总投入成本”、“购入书籍总估值”、“总浮动盈亏”及“已实现利润”。
*   **走势可视化**: 集成 **ECharts**，展示近 7 次同步的**总浮动盈亏走势图**，盈亏波动轨迹一目了然。
*   **智能持仓识别**: 
    *   **持有 (资产)**：填入购入价格（包括 0）的书籍，计入财务统计。
    *   **未持有 (观察)**：购入价格留空的书籍，标记为 `观察` 徽章，仅供查价，不计入盈亏。

### 2. 深度交互前端
*   **动态排序**: 全表列支持点击排序，并带有蓝色的 **↑/↓ 排序箭头** 视觉反馈。
*   **实时搜索**: 支持按书名、ISBN 快速过滤，瞬间定位目标书籍。
*   **极致排版**: 日期列标题精简为 `MM-DD` 格式，备注列自动后置，确保核心财务数据始终处于视觉中心。

### 3. 工业级数据安全
*   **ISBN 自动加锁**: 系统在保存 CSV 时自动为 ISBN 添加单引号前缀 (`'`)，**彻底杜绝** Excel 打开时产生的科学计数法和精度丢失问题。
*   **非侵入性存储**: 支持用户在 CSV 中自由添加任何“自定义列”（如购买渠道、书况备注等），系统会自动识别并保留这些备注，绝不删除。
*   **智能修复**: 同步时通过书名匹配自动修复之前损坏的 ISBN 数据。

### 4. 报表系统修复 (2026-05-29)
*   **已售结项渲染修复**: 修复了“已售结项”区域因字符串格式化错误导致的 Python 代码外露问题。
*   **动态列匹配逻辑优化**: 确保自定义备注列在“已售结项”区域能与表头完美对齐并正确显示。

### 6. 报表视觉精简 (2026-06-03)
*   **最高价徽章简化**：移除徽章上冗余的“可出(最高价)”文字，仅保留 🔥 图标，表格更紧凑、视觉更聚焦。

### 8. 浮动盈亏口径统一 (2026-06-09)
*   **顶部卡片与走势图口径完全一致**：修复了"总浮动盈亏"顶部数字与"总浮动盈亏走势"末点不一致的 Bug。
*   **统一口径**：以 CSV 中"购入价格"字段是否填写为唯一判定标准——
    *   **填了数字（含 0）** → 计入统计。当日多抓鱼无报价时按 0 估值（视为"今日卖不出去"），保证浮亏不会因抓数失败而虚减。
    *   **完全留空** → 观察书籍，不计入任何财务统计。
*   **场景示例**：朋友赠书/凑单赠品可填 `0`，照样参与盈亏统计（成本 0，市价即浮盈）。

### 9. 购入/售出统计折叠区 (2026-07-11)
*   **数量统计更细化**：报表顶部新增可折叠的“购入 / 售出统计”区，集中展示 `累计购入`、`当前持有`、`已售出`、`观察中`、`已移除`。
*   **首页财务区更清晰**：顶部第一张卡片改为 `当前持有`，与折叠区里的累计流转口径分开展示，避免混淆。

### 10. 顶部财务卡片口径升级 (2026-07-12)
*   顶部卡片调整为：`累计购入金额`、`累计卖出金额`、`当前持仓估值`、`持仓盈亏`、`实际盈亏（已实现）`。
*   其中“持仓盈亏”仅反映当前仍持有书籍的浮动结果，“实际盈亏”仅反映已卖出书籍的已实现结果。

### 11. 分组看板增强 (2026-07-13)
*   新增两个可折叠面板：`持有待处理（待售 / 已看）` 与 `观察清单（未持有）`，用于把操作视角和持仓视角分开展示。
*   每个面板都支持按列排序（与主表一致）。
*   如需进入“持有待处理”面板，可在 `manual_overrides.csv` 新增 `处理标签` 列并填写：`待售` 或 `已看`。
*   当前库存仅显示已购入（`状态=持有`）的书；观察书籍单独放在“观察清单”。
*   当前库存表中的灰色书会自动沉底；`已售结项` 区也调整为默认折叠，页面层次更清晰。
*   折叠面板与主库存标题会直接显示数量（如“观察清单（12 本）”“已售结项（9 本）”），查看更直观。

### 7. 同名不同版本图书匹配修复 (2026-06-07)
*   **严格 ISBN 匹配**：修复了"同名不同 ISBN"的图书（如两本《三国演义》不同版本）在同步时被错误合并为同一行、导致历史数据互相覆盖的 Bug。现在只要新数据带 ISBN，就严格按 ISBN 匹配旧记录，不再回退到书名匹配。
*   **副标题入名**：从多抓鱼 API 解析时，自动把 `subtitle` 拼接到书名后（如 `三国演义（插图本）`），让同名不同版本的图书在报表中一眼可辨。
*   **保留用户自定义书名**：旧 CSV 中已有书名时不再被远端数据覆盖，方便用户自行标注"大字本""精装版"等版本信息。

### 5. 架构与可靠性升级 (2026-06-01)
*   **公共逻辑抽取**: 新增 `inventory_core.py`，集中存放所有共享业务逻辑（CSV 处理、报表生成、API 解析等）。`auto_sync_data.py` 瘦身为纯入口脚本，从此一处修复全局生效。
*   **CSV 原子写入**: 写入策略改为先写 `*.csv.tmp` 后 `os.replace`，**杜绝同步过程中崩溃导致主数据文件损坏**。
*   **自动备份**: 每次同步前自动备份当前 CSV 到 `backups/` 目录（命名格式 `inventory-YYYYMMDD_HHMMSS.csv`），默认保留最近 30 份。
*   **更严的日期识别**: 日期列判断改用 `datetime.strptime` 严格校验，避免形如 `2026-备注` 的自定义列被误判。
*   **异常可观测**: 移除裸 `except: pass`，统一替换为 `logging.warning`，便于排查异常数据。

## 快速操作指南

### 方式 A：一键全自动同步 (推荐)
1.  **准备环境**：首次使用需安装依赖：
    ```bash
    pip install playwright --break-system-packages
    playwright install chromium
    ```
2.  **执行同步**：运行 `python3 auto_fetch.py`。
    *   脚本会自动打开浏览器并导航至多抓鱼（首次运行需扫码登录，之后自动保持）。
    *   自动截获数据并同步至 `inventory_auto.csv`。
    *   完成后**自动弹出** `report_auto.html` 查看报表。

### 方式 B：手动同步 (备选)
1.  **多抓鱼取数**：在 Chrome 开发者工具 `Network` 中，右键点击 `inquiry-books` -> `Copy` -> `Copy response`。
2.  **执行同步**：将复制内容保存到本地文件后运行 `python3 auto_sync_data.py <你的数据文件>`。
3.  **查看报表**：双击打开 `report_auto.html`。

### 2. 资产维护
*   **录入成本**：在 `manual_overrides.csv` 的 `购入价格` 列填入数字。
*   **添加备注**：直接在 `manual_overrides.csv` 末尾增加新列（如“备注”），系统下次运行会将其自动展示在报表最右侧。
*   **标记已售**：在 `manual_overrides.csv` 的 `售出价格` 列填入金额，书籍会自动转入“已售结项”区。
*   **本地可视化编辑**：运行 `python3 override_editor.py` 打开本地编辑页，可直接编辑 `manual_overrides.csv`，并通过按钮执行“保存 → 提交推送 → 触发同步”。
*   **删除书籍（推荐）**：在项目根目录运行 `delete_book.py`，会同时删除两个 CSV 中的目标书籍：
    ```bash
    python3 delete_book.py --isbn 9787020188284
    # 或
    python3 delete_book.py --title "棋王 树王 孩子王"
    ```
    * 若检测到该书有购入记录（购入价格非空，含 0），脚本会先提示并要求你输入 `YES` 才继续删除。
    * 如需跳过确认可使用：`python3 delete_book.py --isbn <ISBN> --force`

## 项目结构
```
inventory_core.py    # 共享核心模块（CSV 同步 / 报表生成 / API 解析）
auto_sync_data.py    # 入口 B：自动化模式 (读文件参数, 写 inventory_auto.csv)
manual_overrides.csv # 人工覆盖文件（按 ISBN 录入购入价/售出价/备注）
auto_fetch.py        # Playwright 自动抓取，调用 auto_sync_data.py
override_editor.py   # 本地 override 可视化编辑器（保存/推送/触发同步）
override_editor.html # 本地编辑器页面
delete_book.py       # 按 ISBN/书名同时删除两个 CSV 的目标书籍
.github/workflows/   # GitHub Actions 执行工作流（由外部 cronjob 触发）
backups/             # 每次同步前的 CSV 自动备份（git 忽略）
```

## 手工覆盖文件（推荐编辑入口）
`manual_overrides.csv` 是一个可选的旁路文件，用来单独维护你想手工改的字段。

推荐列：
```csv
ISBN,书名,购入价格,售出价格,备注,处理标签
```

`处理标签` 可选值：`待售`、`已看`（用于报表中的“持有待处理”折叠面板）。

规则：
- 程序会优先按 `ISBN` 精确合并；若 `ISBN` 为空则回退按 `书名` 合并
- 每次同步会自动维护 `manual_overrides.csv`：首次自动初始化，后续自动补新书
- `书名` 会跟随主表更新，方便你识别目标行
- `购入价格` / `售出价格` / `备注` / `处理标签` 以手工文件为准（强覆盖关系）
- 手工文件中的上述字段会在同步时回写并持久化到主表 `inventory_auto.csv`（包含清空值）
- `处理标签` 建议用于运营分组：填 `待售` / `已看` 会进入“持有待处理”折叠面板；留空则不进入该面板
- `manual_overrides.csv` 里有但主表暂无的 ISBN 会保留，避免误删历史手工记录
- 这个文件已使用 UTF-8 with BOM，直接双击用 Excel 打开通常不会乱码；如果仍乱码，可用 Excel 的“数据 -> 自文本/CSV”导入并手动选择 UTF-8
- 程序会自动将 `manual_overrides.csv` 的 ISBN 写成文本保护格式（前置单引号），尽量避免 Excel 科学计数法

## 云端同步（外部 cronjob 触发 GitHub Actions）
1. 在仓库 `Settings -> Secrets and variables -> Actions` 新增密钥：`DZY_CURL_COMMAND`。
   * 值为你在浏览器里可用的 `curl ...inquiry-books...` 命令（建议先在本地验证可用）。
2. 提交本仓库后，进入 `Actions` 页面启用工作流 `Scheduled Price Sync`。
3. 当前机制为：由外部 cronjob 从每天 **00:00** 开始，**每 4 小时** 请求 GitHub 触发该工作流执行（也可手动点 `Run workflow` 立即执行）。
4. 每次成功执行后会自动更新并提交：
   * `last_checked.txt`
   * `inventory_auto.csv`
   * `manual_overrides.csv`
   * `report_auto.html`

### 本地编辑器触发同步（与 cron job 同机制）
1. 运行：
   ```bash
   python3 override_editor.py
   ```
2. 浏览器中可直接编辑 `manual_overrides.csv`，并使用以下按钮：
   - **保存到本地 CSV**
   - **提交并推送 override**
   - **触发 GitHub 同步**
   - **保存 → 推送 → 触发同步**
   - **删除**：仅从当前编辑器表格中移除这一行；需要你后续点击“保存到本地 CSV”才会真正写入 `manual_overrides.csv`
3. “触发 GitHub 同步”走的就是当前 cron job 同样的 **GitHub `workflow_dispatch` 机制**，目标工作流为 `scheduled-price-sync.yml`。
4. 如需启用触发按钮，需要在本地启动前设置 `GITHUB_TOKEN`（或 `GH_TOKEN`）：
   ```bash
   export GITHUB_TOKEN=你的令牌
   python3 override_editor.py
   ```
5. Token 推荐使用 **GitHub Fine-grained personal access token**，并至少给当前仓库以下权限：
   - **Actions: Read and write**（用于触发 `workflow_dispatch`）
   - **Contents: Read and write**（用于本地编辑器里的提交并推送）
6. Token 创建位置：
   - GitHub 右上角头像 → **Settings** → **Developer settings** → **Personal access tokens** → **Fine-grained tokens**
7. 如果你想长期在本机可用，可写入 shell 配置文件（如 `~/.zshrc`）：
   ```bash
   export GITHUB_TOKEN=你的令牌
   source ~/.zshrc
   ```
8. 推荐使用“保存 → 推送 → 触发同步”，因为 GitHub Actions 只能读取**已推送到远端仓库**的内容，无法直接读取你本地尚未推送的修改。
9. 注意：编辑器中的“删除”按钮**不会**自动删除 `inventory_auto.csv` 中的对应书，也不会自动 commit / push / trigger workflow；它只是删除当前 override 编辑行。若该书仍存在于主表或多抓鱼返回列表，后续同步时这行可能再次被自动补回。

### 手机查看方式
开启 GitHub Pages（`Settings -> Pages`，选择 `Deploy from a branch`，`main` + `/root`）后，可通过：
`https://<你的GitHub用户名>.github.io/<仓库名>/report_auto.html` 随时查看最新报表。

## 给别人使用（书单不同也可直接用）
1. **先复制仓库**：建议 Fork 本仓库到自己的 GitHub 账号。
2. **清空你的个人数据再开始**（可选但推荐）：
   - 清空或删除 `inventory_auto.csv`、`manual_overrides.csv` 的旧内容；
   - 保留文件表头即可，首次同步会自动按对方书单补齐。
3. **配置自己的抓取凭据**：在对方仓库的 `Settings -> Secrets and variables -> Actions` 设置 `DZY_CURL_COMMAND`（必须是对方自己浏览器可用的 curl 命令）。
4. **运行一次同步初始化**：在 Actions 手动运行 `Scheduled Price Sync`（或本地执行 `python3 auto_sync_data.py <数据文件>`）。
5. **后续维护方式**：
   - 自动行情来自多抓鱼；
   - 手工字段统一在 `manual_overrides.csv` 维护（购入价/售出价/备注/处理标签），同步时会回写到主表。

### 最小初始化模板（可直接复制）
如果要从“空仓库”开始，建议至少保留以下两个文件及表头：

`inventory_auto.csv`
```csv
ISBN,书名,状态,购入价格,售出价格,历史最高价,备注,处理标签
```

`manual_overrides.csv`
```csv
ISBN,书名,购入价格,售出价格,备注,处理标签
```

说明：
- 首次同步后，程序会自动补齐书籍行与日期列。
- `manual_overrides.csv` 中的手工字段在同步时会优先合并并回写到 `inventory_auto.csv`。

## 报表视觉逻辑
*   **红色/↑**：价格上涨、浮盈。
*   **绿色/↓**：价格下跌、浮亏。
*   **灰色行**：多抓鱼当前暂不回收的书籍。
*   **观察徽章**：尚未买入、仅作行情监控的书籍。
