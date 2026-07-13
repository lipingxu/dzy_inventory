"""
auto_sync_data.py — 自动化模式入口

优先从命令行参数指定的 JSON 文件读取多抓鱼数据，
回退到剪贴板，更新 inventory_auto.csv 并生成 report_auto.html。
由 auto_fetch.py 自动调用。
"""

import json
import subprocess
import sys
import os
from datetime import datetime

from inventory_core import (
    get_clipboard_content,
    load_old_prices,
    migrate_and_update_csv,
    merge_manual_overrides,
    sync_manual_overrides,
    write_inventory_with_overrides,
    generate_report,
    print_change_summary,
    process_raw_data,
)

CSV_PATH = 'inventory_auto.csv'
REPORT_PATH = 'report_auto.html'

if __name__ == "__main__":
    print("--- 多抓鱼数据助手 (自动化版本) ---")

    content = None
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
            print(f"📄 从文件加载数据: {file_path}")

    if not content:
        content = get_clipboard_content()
        if content:
            print("📋 从剪贴板加载数据...")

    if not content:
        print("\n❌ 错误：未提供数据文件且剪贴板为空。")
        sys.exit(1)

    books_data, ordered_ids = None, None
    capture_date = datetime.now().strftime('%Y-%m-%d')

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
            except Exception as e:
                print(f"❌ 联网同步失败: {e}")
                sys.exit(1)
        else:
            print("\n❌ 格式错误：无法解析数据内容。")
            sys.exit(1)

    if books_data:
        print(f"✅ 成功提取 {len(books_data)} 本书籍。")
        old_prices = load_old_prices(CSV_PATH)

        print(f"💾 正在同步至 {CSV_PATH}...")
        headers, rows = migrate_and_update_csv(books_data, capture_date, csv_path=CSV_PATH)

        manual_headers, manual_rows = sync_manual_overrides(headers, rows, 'manual_overrides.csv')
        if manual_rows:
            print("📝 正在合并 manual_overrides.csv ...")
            headers, rows = merge_manual_overrides(headers, rows, manual_headers, manual_rows)
            write_inventory_with_overrides(headers, rows, csv_path=CSV_PATH)

        print(f"📊 正在生成 {REPORT_PATH}...")
        generate_report(headers, rows, books_data, report_path=REPORT_PATH, ordered_ids=ordered_ids)

        print_change_summary(books_data, old_prices)
        print(f"\n🎉 同步成功！报表已刷新 (生成时间: {datetime.now().strftime('%H:%M:%S')})")
    else:
        print("\n❌ 提取失败：未找到书籍数据。")
