"""
sync_data.py — 手动模式入口

从剪贴板读取多抓鱼数据（JSON 响应或 curl 命令），
更新 inventory.csv 并生成 report.html。
"""

import json
import subprocess
import sys
from datetime import datetime

from inventory_core import (
    get_clipboard_content,
    load_old_prices,
    migrate_and_update_csv,
    generate_report,
    print_change_summary,
    process_raw_data,
)

CSV_PATH = 'inventory.csv'
REPORT_PATH = 'report.html'

if __name__ == "__main__":
    print("--- 多抓鱼数据助手 (万能整合版) ---")
    content = get_clipboard_content()
    if not content:
        print("\n❌ 错误：剪贴板为空，请先在 Chrome 复制。")
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
                print(f"❌ 联网同步失败: {e}。请改用 'Copy response'。")
                sys.exit(1)
        else:
            print("\n❌ 格式错误：请确认在 Chrome 中点击了 'Copy response'。")
            sys.exit(1)

    if books_data:
        print(f"✅ 成功提取 {len(books_data)} 本书籍。")
        old_prices = load_old_prices(CSV_PATH)

        print(f"💾 正在同步至 {CSV_PATH}...")
        headers, rows = migrate_and_update_csv(books_data, capture_date, csv_path=CSV_PATH)

        print(f"📊 正在生成 {REPORT_PATH}...")
        generate_report(headers, rows, books_data, report_path=REPORT_PATH, ordered_ids=ordered_ids)

        print_change_summary(books_data, old_prices)
        print(f"\n🎉 同步成功！报表已刷新 (生成时间: {datetime.now().strftime('%H:%M:%S')})")
    else:
        print("\n❌ 提取失败：未找到书籍数据。")
