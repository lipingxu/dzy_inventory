#!/usr/bin/env python3
"""
从 inventory_auto.csv 和 manual_overrides.csv 同时删除指定书籍。

用法示例：
  python3 delete_book.py --isbn 9787020188284
  python3 delete_book.py --title "棋王 树王 孩子王"
  python3 delete_book.py --isbn 9787020188284 --title "棋王 树王 孩子王"
"""

import argparse
import csv
import sys
from pathlib import Path

CSV_FILES = ["inventory_auto.csv", "manual_overrides.csv"]


def normalize_isbn(value: str) -> str:
    isbn = (value or "").strip()
    if isbn.startswith("'"):
        isbn = isbn[1:]
    return isbn.strip()


def should_remove(row: dict, target_isbn: str, target_title: str) -> bool:
    row_isbn = normalize_isbn(row.get("ISBN", ""))
    row_title = (row.get("书名") or "").strip()
    if target_isbn and row_isbn == target_isbn:
        return True
    if target_title and row_title == target_title:
        return True
    return False


def remove_from_csv(path: Path, target_isbn: str, target_title: str) -> int:
    if not path.exists():
        return 0

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        headers = list(reader.fieldnames or [])
        rows = list(reader)

    kept_rows = []
    removed = 0
    for row in rows:
        if should_remove(row, target_isbn, target_title):
            removed += 1
            continue
        kept_rows.append(row)

    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(kept_rows)
    return removed


def main() -> int:
    parser = argparse.ArgumentParser(description="从两个 CSV 中删除指定书籍")
    parser.add_argument("--isbn", default="", help="按 ISBN 删除")
    parser.add_argument("--title", default="", help="按书名删除（精确匹配）")
    args = parser.parse_args()

    target_isbn = normalize_isbn(args.isbn)
    target_title = (args.title or "").strip()
    if not target_isbn and not target_title:
        print("❌ 请至少提供 --isbn 或 --title 之一")
        return 1

    repo_root = Path(__file__).resolve().parent
    total_removed = 0
    for name in CSV_FILES:
        path = repo_root / name
        removed = remove_from_csv(path, target_isbn, target_title)
        total_removed += removed
        print(f"{name}: 删除 {removed} 行")

    if total_removed == 0:
        print("⚠️ 未找到匹配项，请检查 ISBN/书名是否正确。")
    else:
        print(f"✅ 完成，共删除 {total_removed} 行。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
