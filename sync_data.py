import json
import subprocess
import sys
import os
import csv
from datetime import datetime

# ==========================================
# 核心配置与工具函数
# ==========================================

def get_clipboard_content():
    """获取 macOS 剪贴板内容"""
    try:
        return subprocess.check_output(['pbpaste']).decode('utf-8').strip()
    except:
        return None

def format_num(val):
    """数字格式化"""
    if val == int(val): return str(int(val))
    return f"{val:g}"

# ==========================================
# 数据处理与数据库 (CSV) 逻辑
# ==========================================

def migrate_and_update_csv(books_data, capture_date, csv_path='inventory.csv'):
    """更新 inventory.csv，执行状态转换与草稿清理逻辑"""
    fixed_headers = ['ISBN', '书名', '状态', '购入价格', '售出价格', '历史最高价']
    
    # 1. 迁移旧数据逻辑 (兼容最初的 history.csv)
    if not os.path.exists(csv_path) and os.path.exists('history.csv'):
        with open('history.csv', 'r', encoding='utf-8-sig', newline='') as f:
            reader = csv.DictReader(f)
            old_rows = list(reader)
            for r in old_rows:
                r['状态'] = r.get('状态', '持有')
                r['售出价格'] = r.get('售出价格', '')
        temp_headers = fixed_headers + [h for h in old_rows[0].keys() if h not in fixed_headers] if old_rows else fixed_headers
        with open(csv_path, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=temp_headers)
            writer.writeheader()
            writer.writerows(old_rows)

    # 2. 读取当前仓库数据
    rows = []
    if os.path.exists(csv_path):
        with open(csv_path, 'r', encoding='utf-8-sig', newline='') as f:
            reader = csv.DictReader(f)
            reader.fieldnames = [name.strip() for name in reader.fieldnames] if reader.fieldnames else []
            rows = list(reader)

    # 3. 确定日期列、自定义列并归一化
    existing_dates = []
    custom_headers = []
    if rows:
        # 首先找出所有的日期列和自定义列
        all_keys = set()
        for r in rows: all_keys.update(r.keys())
        
        # 区分日期列和自定义列
        for k in all_keys:
            if k in fixed_headers: continue
            # 简单的日期判断逻辑：包含短横线或斜杠且长度在 8-10 之间
            if ('-' in k or '/' in k) and 8 <= len(k) <= 10:
                existing_dates.append(k)
            else:
                custom_headers.append(k)
        
        # 日期归一化处理
        cleaned_rows = []
        for r in rows:
            new_r = {}
            for k, v in r.items():
                if k == 'ISBN' and v and v.startswith("'"):
                    v = v[1:]
                
                if k in existing_dates:
                    try:
                        parts = k.replace('/', '-').split('-')
                        new_k = f"{parts[0]}-{int(parts[1]):02d}-{int(parts[2]):02d}"
                    except: new_k = k
                else: new_k = k
                new_r[new_k] = v
            cleaned_rows.append(new_r)
        rows = cleaned_rows
        
        # 重新整理归一化后的日期
        all_keys_new = set()
        for r in rows: all_keys_new.update(r.keys())
        existing_dates = sorted([k for k in all_keys_new if k not in fixed_headers and k not in custom_headers])

    try:
        parts = capture_date.split('-')
        capture_date = f"{parts[0]}-{int(parts[1]):02d}-{int(parts[2]):02d}"
    except: pass

    if capture_date and capture_date not in existing_dates:
        existing_dates.append(capture_date)
    
    existing_dates.sort()
    tracked_dates = existing_dates[-7:] if len(existing_dates) > 7 else existing_dates
    # 新表头结构：固定列 + 自定义列 + 追踪日期列
    new_headers = fixed_headers + sorted(custom_headers) + tracked_dates

    # 4. 匹配并更新
    isbn_map = {r['ISBN'].strip(): r for r in rows if r.get('ISBN') and r.get('ISBN').strip()}
    title_map = {r['书名'].strip(): r for r in rows if r.get('书名') and r.get('书名').strip()}

    hit_keys = set() # 记录本次抓取到的书
    for book_id, info in books_data.items():
        isbn = info['isbn'].strip() if info['isbn'] else ""
        title = info['title'].strip()
        price = info['price']
        
        matched_row = isbn_map.get(isbn) or title_map.get(title)
        key = (isbn or title).strip()
        hit_keys.add(key)
        
        if matched_row:
            if isbn: matched_row['ISBN'] = isbn
            matched_row['书名'] = title
            # 如果是“已移除”状态，但今天又出现在抓包里，则恢复为“持有”或“未持有”
            if matched_row.get('状态') == '已移除':
                matched_row['状态'] = '未持有'
            # 更新当日行情
            matched_row[capture_date] = price
        else:
            new_row = {h: '' for h in new_headers}
            new_row.update({
                'ISBN': isbn, '书名': title, '状态': '未持有', 
                '购入价格': '', '售出价格': '', '历史最高价': '0.00',
                capture_date: price
            })
            rows.append(new_row)

    # 5. 状态转换与草稿清理
    final_data = []
    seen_keys = set()
    for row in rows:
        key = (row.get('ISBN') or row.get('书名', '')).strip()
        if not key or key in seen_keys: continue
        seen_keys.add(key)

        # 规则 A：自动转“已售” (只要售出价格 > 0 且当前不是已售)
        try:
            sp_val = float(row.get('售出价格') or 0)
            if sp_val > 0:
                row['状态'] = '已售'
        except: pass

        # 核心逻辑：区分“持有”与“未持有”
        if row['状态'] not in ['已售', '已移除']:
            # 只要购入价格列不为空（即使是0），就视为持有；只有留空才视为未持有
            bp_raw = row.get('购入价格', '').strip()
            row['状态'] = '持有' if bp_raw != '' else '未持有'

        # 规则 B：识别“已移除” (不在今日抓包里 且 没有购入价 且 没有售出价)
        if key not in hit_keys:
            try:
                bp_raw = row.get('购入价格', '').strip()
                sp_raw = row.get('售出价格', '').strip()
                if bp_raw == '' and sp_raw == '' and row.get('状态') in ['持有', '未持有']:
                    row['状态'] = '已移除'
            except: pass

        # 维护历史最高价
        old_max = float(row.get('历史最高价') or 0)
        current_prices = []
        for k, v in row.items():
            if k not in fixed_headers and v:
                try: current_prices.append(float(v))
                except: pass
        new_max = max(old_max, max(current_prices) if current_prices else 0)

        out_row = {h: row.get(h, '') for h in new_headers}
        out_row['历史最高价'] = f"{new_max:.2f}"
        
        # 保护 ISBN：写入 CSV 前加上单引号，防止 Excel 破坏
        if out_row.get('ISBN') and not out_row['ISBN'].startswith("'"):
            out_row['ISBN'] = f"'{out_row['ISBN']}"

        for d in tracked_dates:
            if out_row.get(d):
                try: out_row[d] = f"{float(out_row[d]):.2f}"
                except: pass
        final_data.append(out_row)

    # 6. 安全写入
    with open(csv_path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=new_headers)
        writer.writeheader()
        writer.writerows(final_data)
        
    return new_headers, final_data

# ==========================================
# 报表生成逻辑 (HTML)
# ==========================================

def generate_report(headers, rows, books_data, ordered_ids=None):
    fixed_fields = ['ISBN', '书名', '状态', '购入价格', '售出价格', '历史最高价']
    # 更加严谨地识别日期列
    date_headers = [h for h in headers if ('-' in h or '/' in h) and 8 <= len(h) <= 10]
    # 识别自定义列
    custom_headers = [h for h in headers if h not in fixed_fields and h not in date_headers]
    
    latest_date = date_headers[-1] if date_headers else None
    
    # 过滤掉“已移除”的书籍，包含持有和未持有的
    inventory_rows = [r for r in rows if r.get('状态') in ['持有', '未持有']]
    sold_rows = [r for r in rows if r.get('状态') == '已售']

    # 1. 计算核心指标 (针对所有状态为“持有”的书籍)
    purchased_rows = [r for r in inventory_rows if r.get('状态') == '持有']
    
    total_investment = 0
    total_valuation_purchased = 0
    for r in purchased_rows:
        try:
            total_investment += float(r.get('购入价格') or 0)
            # 即使购入价为 0，只要持有，其当前估值也计入总资产
            total_valuation_purchased += float(r.get(latest_date) or 0) if latest_date else 0
        except: pass
    
    floating_profit = total_valuation_purchased - total_investment
    
    total_realized_profit = 0
    for r in sold_rows:
        try:
            total_realized_profit += (float(r.get('售出价格') or 0) - float(r.get('购入价格') or 0))
        except: pass

    # 2. 准备盈亏趋势图数据 (仅针对持有书籍)
    trend_data = []
    for d in date_headers:
        day_profit = 0
        for r in purchased_rows:
            try:
                price = float(r.get(d) or 0)
                if price > 0: # 只有当天有价格才计算，避免缺失数据导致盈利暴跌
                    day_profit += (price - float(r.get('购入价格') or 0))
            except: pass
        # 日期缩短为 MM-DD
        d_short = d[5:] if len(d) > 5 else d
        trend_data.append({"date": d_short, "value": round(day_profit, 2)})

    # 建立快速查找映射
    lookup_map = {}
    for b in books_data.values():
        if b.get('isbn'): lookup_map[b['isbn']] = b
        if b.get('title'): lookup_map[b['title']] = b

    if ordered_ids:
        order_map = {}
        for idx, bid in enumerate(ordered_ids):
            b_info = books_data.get(bid, {})
            if b_info.get('isbn'): order_map[b_info['isbn']] = idx
            if b_info.get('title'): order_map[b_info['title']] = idx
        inventory_rows.sort(key=lambda x: order_map.get(x['ISBN']) if x['ISBN'] in order_map else order_map.get(x['书名'], 999999))

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>图书资产管理系统</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 20px; background: #f4f7f9; color: #334155; }}
        .header-section {{ display: flex; align-items: flex-end; justify-content: space-between; margin-bottom: 20px; }}
        h1 {{ margin: 0; font-size: 1.8rem; color: #1e293b; }}
        
        .update-badge {{ 
            background: #fff; color: #64748b; padding: 6px 15px; border-radius: 50px; 
            font-size: 0.8rem; border: 1px solid #e2e8f0; display: flex; align-items: center;
        }}

        .summary-box {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 15px; margin-bottom: 25px; }}
        .card {{ background: #fff; padding: 18px; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); border: 1px solid #e2e8f0; }}
        .card-label {{ font-size: 0.8rem; color: #64748b; margin-bottom: 8px; font-weight: 500; }}
        .card-val {{ font-size: 1.4rem; font-weight: 800; color: #0f172a; }}
        .val-p {{ color: #ef4444; }}
        .val-n {{ color: #22c55e; }}

        #chart-container {{ background: #fff; padding: 20px; border-radius: 12px; margin-bottom: 25px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); border: 1px solid #e2e8f0; height: 300px; }}

        .section {{ background: #fff; padding: 20px; border-radius: 12px; margin-bottom: 25px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); border: 1px solid #e2e8f0; }}
        .section-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; }}
        h2 {{ font-size: 1.1rem; color: #1e293b; margin: 0; border-left: 4px solid #3b82f6; padding-left: 10px; }}
        
        .search-box {{ padding: 8px 15px; border-radius: 8px; border: 1px solid #e2e8f0; width: 250px; outline: none; transition: all 0.2s; }}
        .search-box:focus {{ border-color: #3b82f6; box-shadow: 0 0 0 3px rgba(59,130,246,0.1); }}

        .table-wrapper {{ overflow-x: auto; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 0.9rem; min-width: 1000px; }}
        th, td {{ padding: 12px; text-align: center; border-bottom: 1px solid #f1f5f9; }}
        th {{ background: #f8fafc; color: #64748b; font-weight: 600; cursor: pointer; position: relative; white-space: nowrap; }}
        th:hover {{ background: #f1f5f9; }}
        th.sortable::after {{ content: "↕"; color: #cbd5e1; margin-left: 5px; font-size: 0.7rem; }}
        th.sort-asc::after {{ content: "↑"; color: #3b82f6; }}
        th.sort-desc::after {{ content: "↓"; color: #3b82f6; }}
        
        .title-col {{ text-align: left; max-width: 280px; font-weight: 600; color: #0f172a; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
        .badge {{ font-size: 0.7rem; padding: 2px 6px; border-radius: 4px; margin-left: 5px; font-weight: 700; }}
        .sb {{ background: #fee2e2; color: #ef4444; }}
        .up {{ background: #fee2e2; color: #ef4444; }}
        .dn {{ background: #dcfce7; color: #22c55e; }}
        
        .gray td {{ color: #94a3b8 !important; opacity: 0.8; }}
        .p-low {{ color: #22c55e; font-weight: 700; }}
        .p-max {{ color: #ef4444; font-weight: 700; background: #fef2f2; padding: 2px 6px; border-radius: 4px; }}
        .profit-p {{ color: #ef4444; font-weight: 700; }}
        .profit-n {{ color: #22c55e; font-weight: 700; }}
    </style>
</head>
<body>
    <div class="header-section">
        <h1>📚 图书资产管理报表</h1>
        <div class="update-badge">
            <span style="margin-right: 6px;">🕒</span>
            刷新于: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        </div>
    </div>
    
    <div class="summary-box">
        <div class="card"><div class="card-label">真正持仓 (有购入价)</div><div class="card-val">{len(purchased_rows)} 本</div></div>
        <div class="card"><div class="card-label">总投入成本</div><div class="card-val">¥{total_investment:.2f}</div></div>
        <div class="card"><div class="card-label">购入书籍总估值</div><div class="card-val" style="color:#3b82f6">¥{total_valuation_purchased:.2f}</div></div>
        <div class="card">
            <div class="card-label">总浮动盈亏</div>
            <div class="card-val {'val-p' if floating_profit>=0 else 'val-n'}">
                {'+' if floating_profit>=0 else ''}{floating_profit:.2f}
            </div>
        </div>
        <div class="card">
            <div class="card-label">已实现利润</div>
            <div class="card-val {'val-p' if total_realized_profit>=0 else 'val-n'}">
                {'+' if total_realized_profit>=0 else ''}{total_realized_profit:.2f}
            </div>
        </div>
    </div>

    <div id="chart-container"></div>

    <div class="section">
        <div class="section-header">
            <h2>📊 当前库存 (持有中)</h2>
            <input type="text" id="search" class="search-box" placeholder="搜索书名、ISBN..." onkeyup="filterTable()">
        </div>
        <div class="table-wrapper">
            <table id="inventory-table">
                <thead>
                    <tr>
                        <th onclick="sortTable('inventory-table', 0)">ISBN</th>
                        <th class="title-col" onclick="sortTable('inventory-table', 1)">书名</th>
                        <th class="sortable" onclick="sortTable('inventory-table', 2, 'num')">购入价</th>
                        <th class="sortable" onclick="sortTable('inventory-table', 3, 'num')">最高价</th>
                        {"".join([f"<th class='sortable' onclick='sortTable(\"inventory-table\", {4+i}, \"num\")'>{d[5:] if len(d)>5 else d}</th>" for i, d in enumerate(date_headers)])}
                        <th class="sortable" onclick="sortTable('inventory-table', {4+len(date_headers)}, 'num')">估算盈亏</th>
                        <th class="sortable" onclick="sortTable('inventory-table', {5+len(date_headers)}, 'num')">7天趋势</th>
                        {"".join([f"<th class='sortable' onclick='sortTable(\"inventory-table\", {6+len(date_headers)+i})'>{ch}</th>" for i, ch in enumerate(custom_headers)])}
                    </tr>
                </thead>
                <tbody>"""
    
    for r in inventory_rows:
        lp_str = r.get(latest_date, "0")
        try: latest_p = float(lp_str) if lp_str else 0
        except: latest_p = 0
        
        max_p = float(r['历史最高价'] or 0)
        tr_cls = "class='gray'" if latest_p == 0 else ""
        
        badges = ""
        # 如果是未持有状态，增加一个“观察”标签
        if r.get('状态') == '未持有':
            badges += "<span class='badge' style='background:#f1f5f9; color:#94a3b8; border:1px solid #e2e8f0;'>观察</span>"

        # 匹配时去掉 ISBN 的单引号
        raw_isbn = r['ISBN'][1:] if r['ISBN'].startswith("'") else r['ISBN']
        current_book_info = lookup_map.get(raw_isbn) or lookup_map.get(r['书名'])
        
        if current_book_info:
            if current_book_info.get('subsidy', 0) > 0: 
                badges += f"<span class='badge sb'>已加价{format_num(current_book_info['subsidy'])}</span>"
            sc = current_book_info.get('state_change')
            if sc:
                tp = sc.get('type')
                prev_y = sc.get('previousViewAcquirePrice', 0)/100
                if tp == 'refused_to_passed': badges += "<span class='badge up'>新增收购</span>"
                elif tp == 'increase_price': badges += f"<span class='badge up'>涨{format_num(abs(latest_p - prev_y))} ↑</span>"
                elif tp == 'decrease_price': badges += f"<span class='badge dn'>降{format_num(abs(latest_p - prev_y))} ↓</span>"

        html += f"<tr {tr_cls}><td style='font-family:monospace'>{raw_isbn}</td><td class='title-col'>{r['书名']}{badges}</td>"
        html += f"<td>{('¥' + r['购入价格']) if r['购入价格'] else '-'}</td><td><span class='p-max'>¥{r['历史最高价']}</span></td>"
        
        ps = []
        for i, d in enumerate(date_headers):
            v = r.get(d, '')
            cls = ""
            if i == len(date_headers)-1 and v and float(v) > 0 and float(v) < max_p: cls = "class='p-low'"
            html += f"<td {cls}>{('¥'+v) if v else '-'}</td>"
            if v: 
                try: ps.append(float(v))
                except: pass
        
        est_val = 0
        est_html = "-"
        if r['购入价格'] and latest_p > 0:
            try:
                est_val = latest_p - float(r['购入价格'])
                est_html = f"<span class='{'profit-p' if est_val>=0 else 'profit-n'}'>{'+' if est_val>=0 else ''}{est_val:.2f}</span>"
            except: pass
        html += f"<td data-val='{est_val}'>{est_html}</td>"

        trnd_val = 0
        trnd_html = "-"
        if len(ps) >= 2:
            trnd_val = ps[-1] - ps[0]
            if trnd_val > 0: trnd_html = f"<span class='profit-p'>↑{trnd_val:.2f}</span>"
            elif trnd_val < 0: trnd_html = f"<span class='profit-n'>↓{abs(trnd_val):.2f}</span>"
            else: trnd_html = "-"
        html += f"<td data-val='{trnd_val}'>{trnd_html}</td>"
        
        # 填充自定义列数据
        for ch in custom_headers:
            html += f"<td>{r.get(ch, '-')}</td>"
        
        html += "</tr>"

    html += """</tbody></table></div></div>
    <div class="section">
        <div class="section-header"><h2>✅ 已售结项</h2></div>
        <div class="table-wrapper">
            <table>
                <thead>
                    <tr>
                        <th>ISBN</th><th class="title-col">书名</th><th>购入价格</th><th>售出价格</th><th>净利润</th>
                        {"".join([f"<th>{ch}</th>" for ch in custom_headers])}
                    </tr>
                </thead>
                <tbody>"""
    
    for r in sold_rows:
        raw_isbn = r['ISBN'][1:] if r['ISBN'].startswith("'") else r['ISBN']
        profit = "-"
        if r['购入价格'] and r['售出价格']:
            try:
                p = float(r['售出价格']) - float(r['购入价格'])
                profit = f"<span class='{'profit-p' if p>=0 else 'profit-n'}'>{'+' if p>=0 else ''}{p:.2f}</span>"
            except: pass
        html += f"<tr><td style='font-family:monospace'>{raw_isbn}</td><td class='title-col'>{r['书名']}</td>"
        html += f"<td>¥{r['购入价格']}</td><td>¥{r['售出价格']}</td><td>{profit}</td>"
        # 已售书籍也显示自定义列
        for ch in custom_headers:
            html += f"<td>{r.get(ch, '-')}</td>"
        html += "</tr>"

    html += f"""</tbody></table></div></div>
    
    <script src="https://fastly.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
    <script>
        // 1. 初始化趋势图
        const trendData = {json.dumps(trend_data)};
        const chart = echarts.init(document.getElementById('chart-container'));
        chart.setOption({{
            title: {{ text: '总浮动盈亏走势', left: 'center', textStyle: {{ fontSize: 14, color: '#64748b' }} }},
            tooltip: {{ trigger: 'axis', formatter: '{{b}}: ¥{{c}}' }},
            grid: {{ left: '3%', right: '4%', bottom: '3%', containLabel: true }},
            xAxis: {{ type: 'category', data: trendData.map(d => d.date), axisLine: {{ lineStyle: {{ color: '#cbd5e1' }} }} }},
            yAxis: {{ type: 'value', axisLabel: {{ formatter: '¥{{value}}' }}, splitLine: {{ lineStyle: {{ type: 'dashed' }} }} }},
            series: [{{
                data: trendData.map(d => d.value),
                type: 'line', smooth: true, symbol: 'circle', symbolSize: 8,
                itemStyle: {{ color: '#ef4444' }},
                areaStyle: {{ color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                    {{ offset: 0, color: 'rgba(239,68,68,0.2)' }},
                    {{ offset: 1, color: 'rgba(239,68,68,0)' }}
                ]) }}
            }}]
        }});

        // 2. 搜索过滤
        function filterTable() {{
            const query = document.getElementById('search').value.toLowerCase();
            const rows = document.querySelectorAll('#inventory-table tbody tr');
            rows.forEach(row => {{
                row.style.display = row.innerText.toLowerCase().includes(query) ? '' : 'none';
            }});
        }}

        // 3. 排序逻辑
        let sortOrder = {{}};
        function sortTable(tableId, colIdx, type) {{
            const table = document.getElementById(tableId);
            const ths = table.querySelectorAll('th');
            const tbody = table.querySelector('tbody');
            const rows = Array.from(tbody.querySelectorAll('tr'));
            
            const direction = sortOrder[colIdx] === 'asc' ? -1 : 1;
            sortOrder[colIdx] = direction === 1 ? 'asc' : 'desc';

            // 清除所有表头的排序 class
            ths.forEach(th => th.classList.remove('sort-asc', 'sort-desc'));
            // 为当前点击的表头添加 class
            ths[colIdx].classList.add(direction === 1 ? 'sort-asc' : 'sort-desc');

            rows.sort((a, b) => {{
                let v1 = a.cells[colIdx].getAttribute('data-val') || a.cells[colIdx].innerText.replace('¥', '').replace('+', '').replace('↑', '').replace('↓', '').trim();
                let v2 = b.cells[colIdx].getAttribute('data-val') || b.cells[colIdx].innerText.replace('¥', '').replace('+', '').replace('↑', '').replace('↓', '').trim();
                
                if (type === 'num') {{
                    v1 = parseFloat(v1) || 0;
                    v2 = parseFloat(v2) || 0;
                    return (v1 - v2) * direction;
                }}
                return v1.localeCompare(v2) * direction;
            }});

            rows.forEach(row => tbody.appendChild(row));
        }}

        window.onresize = () => chart.resize();
    </script>
</body>
</html>"""
    with open('report.html', 'w', encoding='utf-8') as f: f.write(html)

# ==========================================
# 主流程控制
# ==========================================

def process_raw_data(data):
    """解析多抓鱼返回的原始 JSON"""
    if 'data' not in data: return None, None
    books_data = {}
    ordered_ids = []
    for item in data['data']:
        book_id = item.get('id')
        book_info = item.get('book', {})
        if book_id and book_info.get('title'):
            ordered_ids.append(book_id)
            books_data[book_id] = {
                'title': book_info.get('title'),
                'isbn': book_info.get('isbn13', ''),
                'price': item.get('acquirePrice', 0) / 100.0,
                'subsidy': item.get('popularBookSubsidy', 0) / 100.0,
                'state_change': item.get('acquireStateChange')
            }
    return books_data, ordered_ids

if __name__ == "__main__":
    print("--- 多抓鱼数据助手 (万能整合版) ---")
    content = get_clipboard_content()
    if not content:
        print("\n❌ 错误：剪贴板为空，请先在 Chrome 复制。")
        sys.exit(1)

    books_data, ordered_ids = None, None
    capture_date = datetime.now().strftime('%Y-%m-%d')

    # 识别内容类型
    try:
        data = json.loads(content)
        print("💡 检测到响应数据 (JSON)，正在解析...")
        books_data, ordered_ids = process_raw_data(data)
    except json.JSONDecodeError:
        if content.startswith('curl'):
            print("🚀 检测到 curl 命令，尝试联网更新...")
            try:
                exec_curl = content.replace('curl ', 'curl -s ', 1) if " -s " not in content else content
                result = subprocess.check_output(exec_curl, shell=True).decode('utf-8')
                books_data, ordered_ids = process_raw_data(json.loads(result))
            except:
                print("❌ 联网同步失败。请改用 'Copy response'。")
                sys.exit(1)
        else:
            print("\n❌ 格式错误：请确认在 Chrome 中点击了 'Copy response'。")
            sys.exit(1)

    if books_data:
        print(f"✅ 成功提取 {len(books_data)} 本书籍。")
        
        # 获取变动前快照
        old_prices = {}
        if os.path.exists('inventory.csv'):
            try:
                with open('inventory.csv', 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for r in reader:
                        date_cols = [k for k in r.keys() if '-' in k and len(k.split('-'))==3]
                        if date_cols:
                            last_date = sorted(date_cols)[-1]
                            if r.get(last_date): old_prices[r['ISBN'] or r['书名']] = float(r[last_date])
            except: pass

        # 执行更新与生成
        print("💾 正在同步至 inventory.csv...")
        headers, rows = migrate_and_update_csv(books_data, capture_date)
        
        print("📊 正在生成 report.html...")
        generate_report(headers, rows, books_data, ordered_ids)
        
        # 打印变动摘要
        changes = []
        total_diff = 0
        for b_info in books_data.values():
            key = b_info['isbn'] or b_info['title']
            if key in old_prices:
                diff = b_info['price'] - old_prices[key]
                if diff != 0:
                    changes.append(f"  - {b_info['title']}: {old_prices[key]:.2f} -> {b_info['price']:.2f} ({'+' if diff>0 else ''}{diff:.2f})")
                    total_diff += diff
        
        if changes:
            print("\n📈 --- 行情变动提醒 ---")
            print("\n".join(changes))
            print(f"💰 总估值变动: {'+' if total_diff>=0 else ''}{total_diff:.2f} 元")
        
        print(f"\n🎉 同步成功！报表已刷新 (生成时间: {datetime.now().strftime('%H:%M:%S')})")
    else:
        print("\n❌ 提取失败：未找到书籍数据。")
