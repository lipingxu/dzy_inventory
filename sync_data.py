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

    # 3. 确定日期列并归一化 (YYYY-MM-DD)
    existing_dates = []
    if rows:
        cleaned_rows = []
        for r in rows:
            new_r = {}
            for k, v in r.items():
                if k not in fixed_headers and ('-' in k or '/' in k):
                    try:
                        parts = k.replace('/', '-').split('-')
                        if len(parts) == 3:
                            new_k = f"{parts[0]}-{int(parts[1]):02d}-{int(parts[2]):02d}"
                        else: new_k = k
                    except: new_k = k
                else: new_k = k
                
                if new_k in new_r and not new_r[new_k] and v:
                    new_r[new_k] = v
                elif new_k not in new_r:
                    new_r[new_k] = v
            cleaned_rows.append(new_r)
        rows = cleaned_rows
        
        all_keys = []
        for r in rows: all_keys.extend(r.keys())
        existing_dates = sorted(list(set([h for h in all_keys if h not in fixed_headers])))
    
    try:
        parts = capture_date.split('-')
        capture_date = f"{parts[0]}-{int(parts[1]):02d}-{int(parts[2]):02d}"
    except: pass

    if capture_date and capture_date not in existing_dates:
        existing_dates.append(capture_date)
    
    existing_dates.sort()
    tracked_dates = existing_dates[-7:] if len(existing_dates) > 7 else existing_dates
    new_headers = fixed_headers + tracked_dates

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
            # 如果是“已移除”状态，但今天又出现在抓包里，则恢复为“持有”
            if matched_row.get('状态') == '已移除':
                matched_row['状态'] = '持有'
            # 只有持有中的书才更新当日行情
            if matched_row.get('状态') == '持有':
                matched_row[capture_date] = price
        else:
            new_row = {h: '' for h in new_headers}
            new_row.update({
                'ISBN': isbn, '书名': title, '状态': '持有', 
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

        # 规则 B：识别“已移除” (不在今日抓包里 且 没有购入价 且 没有售出价)
        if key not in hit_keys:
            try:
                bp = float(row.get('购入价格') or 0)
                sp = float(row.get('售出价格') or 0)
                if bp == 0 and sp == 0 and row.get('状态') == '持有':
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
    date_headers = [h for h in headers if h not in ['ISBN', '书名', '状态', '购入价格', '售出价格', '历史最高价']]
    latest_date = date_headers[-1] if date_headers else None
    
    # 过滤掉“已移除”的书籍，不显示在报表中
    inventory_rows = [r for r in rows if r.get('状态') == '持有']
    sold_rows = [r for r in rows if r.get('状态') == '已售']

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
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 20px; background: #f0f2f5; color: #333; }}
        .section {{ background: #fff; padding: 20px; border-radius: 12px; margin-bottom: 30px; box-shadow: 0 2px 10px rgba(0,0,0,0.05); overflow-x: auto; }}
        h2 {{ color: #1a73e8; border-left: 5px solid #1a73e8; padding-left: 10px; margin-top: 0; }}
        table {{ width: 100%; border-collapse: collapse; min-width: 1000px; }}
        th, td {{ padding: 12px; text-align: center; border-bottom: 1px solid #eee; }}
        th {{ background: #fafafa; font-size: 0.85rem; color: #666; font-weight: 600; }}
        .title-col {{ text-align: left; max-width: 250px; font-weight: bold; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
        .badge {{ font-size: 0.7rem; padding: 2px 5px; border-radius: 4px; margin-left: 5px; font-weight: bold; vertical-align: middle; display: inline-block; }}
        .sb {{ background-color: #fff5f5; color: #e53e3e; border: 1px solid #feb2b2; }}
        .up {{ background-color: #fff5f5; color: #e53e3e; }}
        .dn {{ background-color: #f0fff4; color: #38a169; }}
        .gray {{ color: #adb5bd !important; }}
        .gray td {{ color: #adb5bd !important; opacity: 0.7; }}
        .p-low {{ color: #38a169; font-weight: bold; }}
        .p-max {{ color: #e53e3e; font-weight: bold; background: #fff5f5; padding: 2px 5px; border-radius: 4px; }}
        .profit-p {{ color: #e53e3e; font-weight: bold; }}
        .profit-n {{ color: #38a169; font-weight: bold; }}
        .summary-box {{ display: flex; gap: 20px; margin-bottom: 20px; }}
        .card {{ background: #fff; padding: 15px 25px; border-radius: 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); min-width: 150px; }}
        .card-val {{ font-size: 1.5rem; font-weight: bold; color: #1a73e8; margin-top: 5px; }}
        .update-badge {{ 
            display: inline-flex; 
            align-items: center; 
            background: #e8f0fe; 
            color: #1967d2; 
            padding: 4px 12px; 
            border-radius: 50px; 
            font-size: 0.8rem; 
            font-weight: 500;
            margin-bottom: 20px;
            border: 1px solid #d2e3fc;
        }}
    </style>
</head>
<body>
    <div style="display: flex; align-items: flex-end; justify-content: space-between; margin-bottom: 5px;">
        <h1 style="margin: 0;">📚 图书资产管理报表</h1>
        <div class="update-badge">
            <span style="margin-right: 5px;">🕒</span>
            报表刷新于: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        </div>
    </div>
    
    <div class="summary-box">
        <div class="card"><div>当前库存</div><div class="card-val">{len(inventory_rows)} 本</div></div>
        <div class="card"><div>已售结项</div><div class="card-val">{len(sold_rows)} 本</div></div>
    </div>

    <div class="section">
        <h2>📊 当前库存 (持有中)</h2>
        <table>
            <thead>
                <tr>
                    <th>ISBN</th><th class="title-col">书名</th><th>购入价</th><th>最高价</th>
                    {"".join([f"<th>{d}</th>" for d in date_headers])}
                    <th>估算盈亏</th><th>近7天趋势</th>
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
        current_book_info = lookup_map.get(r['ISBN']) or lookup_map.get(r['书名'])
        
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

        html += f"<tr {tr_cls}><td style='font-family:monospace'>{r['ISBN']}</td><td class='title-col'>{r['书名']}{badges}</td>"
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
        
        est = "-"
        if r['购入价格'] and latest_p > 0:
            try:
                diff = latest_p - float(r['购入价格'])
                est = f"<span class='{'profit-p' if diff>=0 else 'profit-n'}'>{'+' if diff>=0 else ''}{diff:.2f}</span>"
            except: pass
        html += f"<td>{est}</td>"

        trnd = "-"
        if len(ps) >= 2:
            d = ps[-1] - ps[0]
            if d > 0: trnd = f"<span class='profit-p'>↑{d:.2f}</span>"
            elif d < 0: trnd = f"<span class='profit-n'>↓{abs(d):.2f}</span>"
            else: trnd = "-"
        html += f"<td>{trnd}</td></tr>"

    html += """</tbody></table></div>
    <div class="section">
        <h2>✅ 已售结项</h2>
        <table>
            <thead>
                <tr>
                    <th>ISBN</th><th class="title-col">书名</th><th>购入价格</th><th>售出价格</th><th>净利润</th>
                </tr>
            </thead>
            <tbody>"""
    
    for r in sold_rows:
        profit = "-"
        if r['购入价格'] and r['售出价格']:
            try:
                p = float(r['售出价格']) - float(r['购入价格'])
                profit = f"<span class='{'profit-p' if p>=0 else 'profit-n'}'>{'+' if p>=0 else ''}{p:.2f}</span>"
            except: pass
        html += f"<tr><td style='font-family:monospace'>{r['ISBN']}</td><td class='title-col'>{r['书名']}</td>"
        html += f"<td>¥{r['购入价格']}</td><td>¥{r['售出价格']}</td><td>{profit}</td></tr>"

    html += f"""</tbody></table></div>
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
