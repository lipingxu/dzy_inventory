"""
inventory_core.py — 图书资产管理系统共享核心逻辑

由 auto_sync_data.py 等入口脚本导入，避免重复维护相同代码。
"""

import csv
import json
import logging
import os
import shutil
import subprocess
import sys
from datetime import datetime

logging.basicConfig(format="%(levelname)s: %(message)s", level=logging.WARNING)
logger = logging.getLogger(__name__)

FIXED_HEADERS = ['ISBN', '书名', '状态', '购入价格', '售出价格', '历史最高价']
BACKUP_DIR = "backups"
MAX_BACKUPS = 30


# ==========================================
# 工具函数
# ==========================================

def format_num(val):
    """将数字格式化为无多余小数点的字符串"""
    if val == int(val):
        return str(int(val))
    return f"{val:g}"


def get_clipboard_content():
    """获取 macOS 剪贴板内容"""
    try:
        return subprocess.check_output(['pbpaste']).decode('utf-8').strip()
    except Exception as e:
        logger.warning("读取剪贴板失败: %s", e)
        return None


def _is_date_column(key):
    """严格判断列名是否为 YYYY-MM-DD 格式的日期列"""
    try:
        datetime.strptime(key, '%Y-%m-%d')
        return True
    except ValueError:
        return False


# ==========================================
# 数据处理与数据库 (CSV) 逻辑
# ==========================================

def _backup_csv(csv_path):
    """同步前备份 CSV，最多保留 MAX_BACKUPS 份"""
    if not os.path.exists(csv_path):
        return
    os.makedirs(BACKUP_DIR, exist_ok=True)
    stem = os.path.splitext(os.path.basename(csv_path))[0]
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = os.path.join(BACKUP_DIR, f"{stem}-{timestamp}.csv")
    shutil.copy2(csv_path, backup_path)

    # 清理超出上限的旧备份（按文件名排序，删最旧的）
    pattern = f"{stem}-"
    all_backups = sorted(
        [f for f in os.listdir(BACKUP_DIR) if f.startswith(pattern) and f.endswith('.csv')]
    )
    for old in all_backups[:-MAX_BACKUPS]:
        try:
            os.remove(os.path.join(BACKUP_DIR, old))
        except Exception as e:
            logger.warning("删除旧备份失败: %s", e)


def _write_csv_atomic(csv_path, headers, rows):
    """原子写入 CSV：先写临时文件，成功后再替换，防止崩溃损坏数据"""
    tmp_path = csv_path + ".tmp"
    with open(tmp_path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(tmp_path, csv_path)


def _normalize_isbn(value):
    """统一 ISBN 比较口径，去空白并移除 Excel 保护前缀单引号。"""
    isbn = (value or '').strip()
    if isbn.startswith("'"):
        isbn = isbn[1:]
    return isbn.strip()


def _format_isbn_for_csv(value):
    """写回 CSV 时给 ISBN 加文本保护前缀，避免 Excel 科学计数法。"""
    isbn = _normalize_isbn(value)
    return f"'{isbn}" if isbn else ''


def _row_identity(row):
    """构建行匹配键：优先 ISBN，缺失时回退书名。"""
    isbn = _normalize_isbn(row.get('ISBN'))
    if isbn:
        return f"isbn:{isbn}"
    title = (row.get('书名') or '').strip()
    if title:
        return f"title:{title}"
    return None


def load_manual_overrides(overrides_path='manual_overrides.csv'):
    """读取手工覆盖文件，返回表头和数据行。"""
    manual_headers = []
    manual_rows = []
    if not os.path.exists(overrides_path):
        return manual_headers, manual_rows
    try:
        with open(overrides_path, 'r', encoding='utf-8-sig', newline='') as f:
            reader = csv.DictReader(f)
            if reader.fieldnames:
                manual_headers = [name.strip() for name in reader.fieldnames]
            manual_rows = list(reader)
    except Exception as e:
        logger.warning("读取手工覆盖文件失败: %s", e)
    return manual_headers, manual_rows


def sync_manual_overrides(headers, rows, overrides_path='manual_overrides.csv'):
    """同步手工覆盖文件：初始化、补新书、并保留人工字段。"""
    base_headers = ['ISBN', '书名', '购入价格', '售出价格', '备注']

    existing_headers, existing_rows = load_manual_overrides(overrides_path)
    extra_headers = [h for h in existing_headers if h not in base_headers]
    manual_headers = base_headers + extra_headers

    source_rows = []
    for row in rows:
        identity = _row_identity(row)
        if not identity:
            continue
        source_rows.append((identity, row))

    existing_map = {}
    for row in existing_rows:
        identity = _row_identity(row)
        if identity:
            existing_map[identity] = row

    manual_rows = []
    seen_keys = set()
    for identity, source in source_rows:
        seen_keys.add(identity)
        existing = existing_map.get(identity)

        out = {h: '' for h in manual_headers}
        out['ISBN'] = _format_isbn_for_csv(source.get('ISBN'))
        out['书名'] = (source.get('书名') or '').strip()

        if existing:
            for h in manual_headers:
                if h in ('ISBN', '书名'):
                    continue
                existing_value = (existing.get(h) or '').strip()
                if existing_value:
                    out[h] = existing_value
                    continue

                source_value = (source.get(h) or '').strip()
                if source_value:
                    out[h] = source_value
        else:
            out['购入价格'] = (source.get('购入价格') or '').strip()
            out['售出价格'] = (source.get('售出价格') or '').strip()
            out['备注'] = (source.get('备注') or '').strip()
            for h in extra_headers:
                out[h] = (source.get(h) or '').strip()

        manual_rows.append(out)

    # 保留 manual 里有但当前主表没有的记录（防误删历史手工记录）
    for identity, existing in existing_map.items():
        if identity in seen_keys:
            continue
        out = {h: '' for h in manual_headers}
        for h in manual_headers:
            out[h] = (existing.get(h) or '').strip()
        out['ISBN'] = _format_isbn_for_csv(existing.get('ISBN'))
        manual_rows.append(out)

    _write_csv_atomic(overrides_path, manual_headers, manual_rows)
    return manual_headers, manual_rows


def merge_manual_overrides(headers, rows, manual_headers, manual_rows):
    """将手工覆盖文件合并到自动生成的行中。"""
    if not manual_rows:
        return headers, rows

    extra_headers = []
    for manual_row in manual_rows:
        for key in manual_headers:
            if key == 'ISBN' or key in headers or key in extra_headers:
                continue
            raw_value = manual_row.get(key, '')
            value = raw_value.strip() if isinstance(raw_value, str) else str(raw_value).strip() if raw_value is not None else ''
            if value:
                extra_headers.append(key)

    merged_headers = headers + extra_headers

    override_map = {}
    for manual_row in manual_rows:
        identity = _row_identity(manual_row)
        if identity:
            override_map[identity] = manual_row

    merged_rows = []
    for row in rows:
        merged_row = dict(row)
        identity = _row_identity(merged_row)
        override = override_map.get(identity) if identity else None
        if override:
            for key, raw_value in override.items():
                if key == 'ISBN':
                    continue
                value = raw_value.strip() if isinstance(raw_value, str) else str(raw_value).strip() if raw_value is not None else ''
                if not value:
                    continue
                merged_row[key] = value

            buy_price = (merged_row.get('购入价格') or '').strip()
            sell_price = (merged_row.get('售出价格') or '').strip()
            if sell_price:
                merged_row['状态'] = '已售'
            elif buy_price and merged_row.get('状态') != '已售':
                merged_row['状态'] = '持有'

        merged_rows.append(merged_row)

    return merged_headers, merged_rows


def write_inventory_with_overrides(headers, rows, csv_path='inventory_auto.csv'):
    """将合并后的主表数据原子写回 CSV，确保手工字段持久化到主表。"""
    normalized_rows = []
    for row in rows:
        out = {h: row.get(h, '') for h in headers}
        out['ISBN'] = _format_isbn_for_csv(out.get('ISBN'))
        normalized_rows.append(out)
    _write_csv_atomic(csv_path, headers, normalized_rows)


def migrate_and_update_csv(books_data, capture_date, csv_path='inventory.csv'):
    """更新 CSV，执行状态转换与草稿清理逻辑，写入前自动备份并原子写入"""

    # 1. 迁移旧数据逻辑 (兼容最初的 history.csv)
    if not os.path.exists(csv_path) and os.path.exists('history.csv'):
        with open('history.csv', 'r', encoding='utf-8-sig', newline='') as f:
            reader = csv.DictReader(f)
            old_rows = list(reader)
            for r in old_rows:
                r['状态'] = r.get('状态', '持有')
                r['售出价格'] = r.get('售出价格', '')
        temp_headers = FIXED_HEADERS + [h for h in old_rows[0].keys() if h not in FIXED_HEADERS] if old_rows else FIXED_HEADERS
        _write_csv_atomic(csv_path, temp_headers, old_rows)

    # 2. 读取当前仓库数据
    rows = []
    if os.path.exists(csv_path):
        with open(csv_path, 'r', encoding='utf-8-sig', newline='') as f:
            reader = csv.DictReader(f)
            if reader.fieldnames:
                reader.fieldnames = [name.strip() for name in reader.fieldnames]
            rows = list(reader)

    # 3. 确定日期列、自定义列并归一化
    existing_dates = []
    custom_headers = []
    if rows:
        all_keys = set()
        for r in rows:
            all_keys.update(r.keys())

        for k in all_keys:
            if k in FIXED_HEADERS:
                continue
            if _is_date_column(k.replace('/', '-').replace('/', '-')):
                existing_dates.append(k)
            else:
                custom_headers.append(k)

        # 日期归一化（统一为 YYYY-MM-DD）
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
                    except Exception as e:
                        logger.warning("日期列归一化失败 '%s': %s", k, e)
                        new_k = k
                else:
                    new_k = k
                new_r[new_k] = v
            cleaned_rows.append(new_r)
        rows = cleaned_rows

        # 重新整理归一化后的日期列
        all_keys_new = set()
        for r in rows:
            all_keys_new.update(r.keys())
        existing_dates = sorted([k for k in all_keys_new if k not in FIXED_HEADERS and k not in custom_headers])

    try:
        parts = capture_date.split('-')
        capture_date = f"{parts[0]}-{int(parts[1]):02d}-{int(parts[2]):02d}"
    except Exception as e:
        logger.warning("capture_date 归一化失败: %s", e)

    if capture_date and capture_date not in existing_dates:
        existing_dates.append(capture_date)

    existing_dates.sort()
    tracked_dates = existing_dates[-7:] if len(existing_dates) > 7 else existing_dates
    new_headers = FIXED_HEADERS + sorted(custom_headers) + tracked_dates

    # 4. 匹配并更新
    isbn_map = {r['ISBN'].strip(): r for r in rows if r.get('ISBN') and r.get('ISBN').strip()}
    title_map = {r['书名'].strip(): r for r in rows if r.get('书名') and r.get('书名').strip()}

    hit_keys = set()
    for book_id, info in books_data.items():
        isbn = info['isbn'].strip() if info['isbn'] else ""
        title = info['title'].strip()
        price = info['price']

        # 严格优先 ISBN 匹配；只有当本书没有 ISBN 时才回退按书名匹配，
        # 避免同名不同版本（如两本《三国演义》）被错误合并到同一行。
        if isbn:
            matched_row = isbn_map.get(isbn)
        else:
            matched_row = title_map.get(title)
        key = (isbn or title).strip()
        hit_keys.add(key)

        if matched_row:
            if isbn:
                matched_row['ISBN'] = isbn
            if not (matched_row.get('书名') or '').strip():
                matched_row['书名'] = title
            if matched_row.get('状态') == '已移除':
                matched_row['状态'] = '未持有'
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
        if not key or key in seen_keys:
            continue
        seen_keys.add(key)

        # 规则 A：自动转"已售"
        try:
            if float(row.get('售出价格') or 0) > 0:
                row['状态'] = '已售'
        except Exception as e:
            logger.warning("售出价格解析失败 '%s': %s", row.get('书名'), e)

        # 核心逻辑：区分"持有"与"未持有"
        if row['状态'] not in ['已售', '已移除']:
            bp_raw = row.get('购入价格', '').strip()
            row['状态'] = '持有' if bp_raw != '' else '未持有'

        # 规则 B：识别"已移除"
        if key not in hit_keys:
            bp_raw = row.get('购入价格', '').strip()
            sp_raw = row.get('售出价格', '').strip()
            if bp_raw == '' and sp_raw == '' and row.get('状态') in ['持有', '未持有']:
                row['状态'] = '已移除'

        # 维护历史最高价
        old_max = float(row.get('历史最高价') or 0)
        current_prices = []
        for k, v in row.items():
            if k not in FIXED_HEADERS and v:
                try:
                    current_prices.append(float(v))
                except ValueError:
                    pass
        new_max = max(old_max, max(current_prices) if current_prices else 0)

        out_row = {h: row.get(h, '') for h in new_headers}
        out_row['历史最高价'] = f"{new_max:.2f}"

        if out_row.get('ISBN') and not out_row['ISBN'].startswith("'"):
            out_row['ISBN'] = f"'{out_row['ISBN']}"

        for d in tracked_dates:
            if out_row.get(d):
                try:
                    out_row[d] = f"{float(out_row[d]):.2f}"
                except ValueError:
                    pass
        final_data.append(out_row)

    # 6. 备份 + 原子写入
    _backup_csv(csv_path)
    _write_csv_atomic(csv_path, new_headers, final_data)

    return new_headers, final_data


def load_old_prices(csv_path):
    """读取 CSV 中最近一次日期列的价格快照，用于计算变动差值"""
    old_prices = {}
    if not os.path.exists(csv_path):
        return old_prices
    try:
        with open(csv_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for r in reader:
                date_cols = [k for k in r.keys() if _is_date_column(k)]
                if date_cols:
                    last_date = sorted(date_cols)[-1]
                    if r.get(last_date):
                        try:
                            old_prices[r.get('ISBN', '') or r.get('书名', '')] = float(r[last_date])
                        except ValueError:
                            pass
    except Exception as e:
        logger.warning("读取价格快照失败: %s", e)
    return old_prices


def print_change_summary(books_data, old_prices):
    """打印行情变动摘要"""
    changes = []
    total_diff = 0
    for b_info in books_data.values():
        key = b_info['isbn'] or b_info['title']
        if key in old_prices:
            diff = b_info['price'] - old_prices[key]
            if diff != 0:
                changes.append(
                    f"  - {b_info['title']}: {old_prices[key]:.2f} -> {b_info['price']:.2f} "
                    f"({'+' if diff > 0 else ''}{diff:.2f})"
                )
                total_diff += diff
    if changes:
        print("\n📈 --- 行情变动提醒 ---")
        print("\n".join(changes))
        print(f"💰 总估值变动: {'+' if total_diff >= 0 else ''}{total_diff:.2f} 元")


# ==========================================
# 报表生成逻辑 (HTML)
# ==========================================

def generate_report(headers, rows, books_data, report_path='report.html', ordered_ids=None):
    fixed_fields = FIXED_HEADERS
    date_headers = [h for h in headers if _is_date_column(h)]
    custom_headers = [h for h in headers if h not in fixed_fields and h not in date_headers]

    last_checked_text = ""
    try:
        if os.path.exists('last_checked.txt'):
            with open('last_checked.txt', 'r', encoding='utf-8') as _f:
                last_checked_text = _f.read().strip()
    except Exception as e:
        logger.warning("读取 last_checked.txt 失败: %s", e)

    latest_date = date_headers[-1] if date_headers else None

    inventory_rows = [r for r in rows if r.get('状态') in ['持有', '未持有']]
    sold_rows = [r for r in rows if r.get('状态') == '已售']
    removed_rows = [r for r in rows if r.get('状态') == '已移除']

    # 1. 计算核心指标
    purchased_rows = [r for r in inventory_rows if r.get('状态') == '持有']
    ever_purchased_rows = [r for r in rows if (r.get('购入价格') or '').strip() != '']
    observing_rows = [r for r in inventory_rows if r.get('状态') == '未持有']

    current_holding_cost = 0
    total_valuation_purchased = 0
    for r in purchased_rows:
        try:
            cost = float(r.get('购入价格') or 0)
            latest_price = float(r.get(latest_date) or 0) if latest_date else 0
            current_holding_cost += cost
            total_valuation_purchased += latest_price
        except (ValueError, TypeError):
            pass

    floating_profit = total_valuation_purchased - current_holding_cost

    total_buy_amount = 0
    for r in ever_purchased_rows:
        try:
            total_buy_amount += float(r.get('购入价格') or 0)
        except (ValueError, TypeError):
            pass

    total_sell_amount = 0
    for r in sold_rows:
        try:
            total_sell_amount += float(r.get('售出价格') or 0)
        except (ValueError, TypeError):
            pass

    total_realized_profit = 0
    for r in sold_rows:
        try:
            total_realized_profit += float(r.get('售出价格') or 0) - float(r.get('购入价格') or 0)
        except (ValueError, TypeError):
            pass

    # 2. 盈亏趋势图数据
    trend_data = []
    for d in date_headers:
        day_profit = 0
        for r in purchased_rows:
            try:
                cost = float(r.get('购入价格') or 0)
                price = float(r.get(d) or 0)
                day_profit += price - cost
            except (ValueError, TypeError):
                pass
        d_short = d[5:] if len(d) > 5 else d
        trend_data.append({"date": d_short, "value": round(day_profit, 2)})

    # 3. 建立快速查找映射
    lookup_map = {}
    for b in books_data.values():
        if b.get('isbn'):
            lookup_map[b['isbn']] = b
        if b.get('title'):
            lookup_map[b['title']] = b

    if ordered_ids:
        order_map = {}
        for idx, bid in enumerate(ordered_ids):
            b_info = books_data.get(bid, {})
            if b_info.get('isbn'):
                order_map[b_info['isbn']] = idx
            if b_info.get('title'):
                order_map[b_info['title']] = idx
        inventory_rows.sort(
            key=lambda x: order_map.get(x['ISBN']) if x['ISBN'] in order_map else order_map.get(x['书名'], 999999)
        )

    processing_rows = [
        r for r in inventory_rows
        if r.get('状态') == '持有' and (r.get('处理标签') or '').strip() in ['待售', '已看']
    ]
    observing_panel_rows = [r for r in inventory_rows if r.get('状态') == '未持有']
    table_col_count = 6 + len(date_headers) + len(custom_headers)

    def _table_headers_html(table_id):
        headers_html = [
            f"<th onclick=\"sortTable('{table_id}', 0)\">ISBN</th>",
            f"<th class='title-col' onclick=\"sortTable('{table_id}', 1)\">书名</th>",
            f"<th class='sortable' onclick=\"sortTable('{table_id}', 2, 'num')\">购入价</th>",
            f"<th class='sortable' onclick=\"sortTable('{table_id}', 3, 'num')\">最高价</th>",
        ]
        for i, d in enumerate(date_headers):
            d_text = d[5:] if len(d) > 5 else d
            headers_html.append(
                f"<th class='sortable' onclick=\"sortTable('{table_id}', {4+i}, 'num')\">{d_text}</th>"
            )
        headers_html.append(
            f"<th class='sortable' onclick=\"sortTable('{table_id}', {4+len(date_headers)}, 'num')\">估算盈亏</th>"
        )
        headers_html.append(
            f"<th class='sortable' onclick=\"sortTable('{table_id}', {5+len(date_headers)}, 'num')\">7天趋势</th>"
        )
        for i, ch in enumerate(custom_headers):
            headers_html.append(
                f"<th class='sortable' onclick=\"sortTable('{table_id}', {6+len(date_headers)+i})\">{ch}</th>"
            )
        return "".join(headers_html)

    def _build_inventory_rows_html(target_rows):
        html_rows = []
        for r in target_rows:
            lp_str = r.get(latest_date, "0")
            try:
                latest_p = float(lp_str) if lp_str else 0
            except (ValueError, TypeError):
                latest_p = 0

            max_p = float(r['历史最高价'] or 0)
            if latest_p == 0:
                tr_cls = "class='gray'"
            elif latest_p > 0 and abs(latest_p - max_p) < 0.01:
                tr_cls = "class='at-peak'"
            else:
                tr_cls = ""

            badges = ""
            at_peak = latest_p > 0 and abs(latest_p - max_p) < 0.01
            if at_peak:
                badges += "<span class='badge badge-peak'>\U0001f525</span>"
            if r.get('状态') == '未持有':
                badges += "<span class='badge' style='background:#f1f5f9; color:#94a3b8; border:1px solid #e2e8f0;'>观察</span>"

            raw_isbn = r['ISBN'][1:] if r['ISBN'].startswith("'") else r['ISBN']
            current_book_info = lookup_map.get(raw_isbn) or lookup_map.get(r['书名'])
            if current_book_info:
                if current_book_info.get('subsidy', 0) > 0:
                    badges += f"<span class='badge sb'>已加价{format_num(current_book_info['subsidy'])}</span>"
                sc = current_book_info.get('state_change')
                if sc:
                    tp = sc.get('type')
                    prev_y = sc.get('previousViewAcquirePrice', 0) / 100
                    if tp == 'refused_to_passed':
                        badges += "<span class='badge up'>新增收购</span>"
                    elif tp == 'increase_price':
                        badges += f"<span class='badge up'>涨{format_num(abs(latest_p - prev_y))} ↑</span>"
                    elif tp == 'decrease_price':
                        badges += f"<span class='badge dn'>降{format_num(abs(latest_p - prev_y))} ↓</span>"

            row_html = f"<tr {tr_cls}><td style='font-family:monospace'>{raw_isbn}</td><td class='title-col'>{r['书名']}{badges}</td>"
            max_cls = 'p-peak' if at_peak else 'p-max'
            row_html += f"<td>{('¥' + r['购入价格']) if r['购入价格'] else '-'}</td><td><span class='{max_cls}'>¥{r['历史最高价']}</span></td>"

            ps = []
            for i, d in enumerate(date_headers):
                v = r.get(d, '')
                cls = ""
                if i == len(date_headers) - 1 and v and float(v) > 0 and float(v) < max_p:
                    cls = "class='p-low'"
                row_html += f"<td {cls}>{('¥' + v) if v else '-'}</td>"
                if v:
                    try:
                        ps.append(float(v))
                    except ValueError:
                        pass

            est_val = 0
            est_html = "-"
            if r['购入价格'] and latest_p > 0:
                try:
                    est_val = latest_p - float(r['购入价格'])
                    est_html = f"<span class='{'profit-p' if est_val>=0 else 'profit-n'}'>{'+' if est_val>=0 else ''}{est_val:.2f}</span>"
                except (ValueError, TypeError):
                    pass
            row_html += f"<td data-val='{est_val}'>{est_html}</td>"

            trnd_val = 0
            trnd_html = "-"
            if len(ps) >= 2:
                trnd_val = ps[-1] - ps[0]
                if trnd_val > 0:
                    trnd_html = f"<span class='profit-p'>↑{trnd_val:.2f}</span>"
                elif trnd_val < 0:
                    trnd_html = f"<span class='profit-n'>↓{abs(trnd_val):.2f}</span>"
            row_html += f"<td data-val='{trnd_val}'>{trnd_html}</td>"

            for ch in custom_headers:
                row_html += f"<td>{r.get(ch, '-')}</td>"

            row_html += "</tr>"
            html_rows.append(row_html)
        return "".join(html_rows)

    inventory_table_headers = _table_headers_html('inventory-table')
    processing_table_headers = _table_headers_html('processing-table')
    observing_table_headers = _table_headers_html('observing-table')

    inventory_rows_html = _build_inventory_rows_html(inventory_rows)
    processing_rows_html = _build_inventory_rows_html(processing_rows)
    observing_rows_html = _build_inventory_rows_html(observing_panel_rows)

    if not processing_rows_html:
        processing_rows_html = f"<tr><td colspan='{table_col_count}' class='empty-hint'>暂无“待售 / 已看”的持有书籍（可在 manual_overrides.csv 的“处理标签”列填写：待售、已看）。</td></tr>"
    if not observing_rows_html:
        observing_rows_html = f"<tr><td colspan='{table_col_count}' class='empty-hint'>暂无观察中的书籍。</td></tr>"

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
        .details-card {{ background: #fff; border-radius: 12px; margin-bottom: 25px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); border: 1px solid #e2e8f0; overflow: hidden; }}
        .details-card summary {{ list-style: none; cursor: pointer; padding: 16px 18px; display: flex; align-items: center; justify-content: space-between; font-weight: 700; color: #1e293b; }}
        .details-card summary::-webkit-details-marker {{ display: none; }}
        .details-card summary:hover {{ background: #f8fafc; }}
        .details-hint {{ font-size: 0.85rem; font-weight: 500; color: #64748b; }}
        .details-card summary::after {{ content: "展开"; font-size: 0.85rem; color: #3b82f6; font-weight: 600; }}
        .details-card[open] summary::after {{ content: "收起"; }}
        .details-body {{ padding: 0 18px 18px; border-top: 1px solid #f1f5f9; }}
        .details-note {{ margin: 14px 0 0; color: #64748b; font-size: 0.85rem; }}
        .empty-hint {{ text-align: center; color: #94a3b8; font-size: 0.9rem; padding: 20px 10px; }}

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
        tr.at-peak td {{ background: #fffbeb !important; }}
        .badge-peak {{ background: #f59e0b; color: #fff; }}
        .p-peak {{ color: #b45309; font-weight: 800; background: #fef3c7; padding: 2px 6px; border-radius: 4px; }}
    </style>
</head>
<body>
    <div class="header-section">
        <h1>📚 图书资产管理报表</h1>
        <div class="update-badge">
            <span style="margin-right: 6px;">🕒</span>
            刷新于: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            {f'<span style="margin-left:10px; color:#94a3b8;">| 最后检查: {last_checked_text}</span>' if last_checked_text else ''}
        </div>
    </div>
    
    <div class="summary-box">
        <div class="card"><div class="card-label">累计购入金额</div><div class="card-val">¥{total_buy_amount:.2f}</div></div>
        <div class="card"><div class="card-label">累计卖出金额</div><div class="card-val" style="color:#3b82f6">¥{total_sell_amount:.2f}</div></div>
        <div class="card"><div class="card-label">当前持仓估值</div><div class="card-val" style="color:#3b82f6">¥{total_valuation_purchased:.2f}</div></div>
        <div class="card">
            <div class="card-label">持仓盈亏</div>
            <div class="card-val {'val-p' if floating_profit>=0 else 'val-n'}">
                {'+' if floating_profit>=0 else ''}{floating_profit:.2f}
            </div>
        </div>
        <div class="card">
            <div class="card-label">实际盈亏（已实现）</div>
            <div class="card-val {'val-p' if total_realized_profit>=0 else 'val-n'}">
                {'+' if total_realized_profit>=0 else ''}{total_realized_profit:.2f}
            </div>
        </div>
    </div>

    <details class="details-card">
        <summary>
            <span>📦 购入 / 售出统计</span>
            <span class="details-hint">查看累计购入、当前持有、已售出等数量</span>
        </summary>
        <div class="details-body">
            <div class="summary-box" style="margin: 18px 0 0;">
                <div class="card"><div class="card-label">累计购入</div><div class="card-val">{len(ever_purchased_rows)} 本</div></div>
                <div class="card"><div class="card-label">当前持有</div><div class="card-val">{len(purchased_rows)} 本</div></div>
                <div class="card"><div class="card-label">已售出</div><div class="card-val">{len(sold_rows)} 本</div></div>
                <div class="card"><div class="card-label">观察中</div><div class="card-val">{len(observing_rows)} 本</div></div>
                <div class="card"><div class="card-label">已移除</div><div class="card-val">{len(removed_rows)} 本</div></div>
            </div>
            <p class="details-note">说明：累计购入按“购入价格已填写”统计；当前持有为已购入且未售出；观察中为仅跟踪价格、未填写购入价的书。</p>
        </div>
    </details>

    <details class="details-card">
        <summary>
            <span>🛎️ 持有待处理（待售 / 已看）</span>
            <span class="details-hint">仅显示当前持有且已标注处理标签的书</span>
        </summary>
        <div class="details-body">
            <div class="table-wrapper" style="margin-top:18px;">
                <table id="processing-table">
                    <thead>
                        <tr>{processing_table_headers}</tr>
                    </thead>
                    <tbody>{processing_rows_html}</tbody>
                </table>
            </div>
        </div>
    </details>

    <details class="details-card">
        <summary>
            <span>👀 观察清单（未持有）</span>
            <span class="details-hint">仅显示观察中的书籍，可按字段排序</span>
        </summary>
        <div class="details-body">
            <div class="table-wrapper" style="margin-top:18px;">
                <table id="observing-table">
                    <thead>
                        <tr>{observing_table_headers}</tr>
                    </thead>
                    <tbody>{observing_rows_html}</tbody>
                </table>
            </div>
        </div>
    </details>

    <div id="chart-container"></div>

    <div class="section">
        <div class="section-header">
            <h2>📊 当前库存 (持有中)</h2>
            <input type="text" id="search" class="search-box" placeholder="搜索书名、ISBN..." onkeyup="filterTable()">
        </div>
        <div class="table-wrapper">
            <table id="inventory-table">
                <thead>
                    <tr>{inventory_table_headers}</tr>
                </thead>
                <tbody>{inventory_rows_html}</tbody></table></div></div>
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
            except (ValueError, TypeError):
                pass
        html += f"<tr><td style='font-family:monospace'>{raw_isbn}</td><td class='title-col'>{r['书名']}</td>"
        html += f"<td>¥{r['购入价格']}</td><td>¥{r['售出价格']}</td><td>{profit}</td>"
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

            ths.forEach(th => th.classList.remove('sort-asc', 'sort-desc'));
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

    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(html)


# ==========================================
# API 解析
# ==========================================

def process_raw_data(data):
    """解析多抓鱼返回的原始 JSON"""
    if 'data' not in data:
        return None, None
    books_data = {}
    ordered_ids = []
    for item in data['data']:
        book_id = item.get('id')
        book_info = item.get('book', {})
        if book_id and book_info.get('title'):
            ordered_ids.append(book_id)
            title = book_info.get('title')
            subtitle = (book_info.get('subtitle') or '').strip()
            display_title = f"{title}（{subtitle}）" if subtitle else title
            books_data[book_id] = {
                'title': display_title,
                'isbn': book_info.get('isbn13', ''),
                'price': item.get('acquirePrice', 0) / 100.0,
                'subsidy': item.get('popularBookSubsidy', 0) / 100.0,
                'state_change': item.get('acquireStateChange')
            }
    return books_data, ordered_ids
