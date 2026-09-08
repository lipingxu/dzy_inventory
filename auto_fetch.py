import sys
import os
import subprocess
import time
import json
from playwright.sync_api import sync_playwright

# 配置
BASE_URL = "https://www.duozhuayu.com/sell"
CHROME_DATA_DIR = os.path.join(os.getcwd(), "chrome_data")
TARGET_FILE = "latest_data.json"
SYNC_SCRIPT = "auto_sync_data.py"

def run_automation():
    with sync_playwright() as p:
        print(f"🚀 启动浏览器 (数据目录: {CHROME_DATA_DIR})...")
        # 使用持久化上下文以保留登录状态
        context = p.chromium.launch_persistent_context(
            CHROME_DATA_DIR,
            headless=False, # 设置为 False 以便用户在需要时手动登录/扫码
            args=["--start-maximized"]
        )
        
        page = context.new_page()
        
        captured_data = None

        def handle_response(response):
            nonlocal captured_data
            if "inquiry-books" in response.url:
                print(f"📥 截获到目标数据: {response.url}")
                try:
                    captured_data = response.json()
                except Exception as e:
                    print(f"❌ 解析 JSON 失败: {e}")

        # 监听所有响应
        page.on("response", handle_response)

        print(f"🌐 正在访问: {BASE_URL}")
        page.goto(BASE_URL)

        print("⏳ 等待数据加载 (请确保已登录，如未登录请在浏览器中完成扫码)...")
        
        # 循环等待直到截获到数据
        timeout = 300 # 5分钟超时
        start_time = time.time()
        while captured_data is None:
            if time.time() - start_time > timeout:
                print("❌ 等待超时，未捕获到 inquiry-books 数据。")
                break
            page.wait_for_timeout(1000)
            
            # 检查是否还在卖书页面，如果被重定向到登录页，提醒用户
            if "login" in page.url:
                print("🔑 检测到需要登录，请在打开的浏览器中完成登录...")

        if captured_data:
            # 保存数据到临时文件
            with open(TARGET_FILE, "w", encoding="utf-8") as f:
                json.dump(captured_data, f, ensure_ascii=False, indent=2)
            print(f"💾 数据已保存至 {TARGET_FILE}")
            
            # 关闭浏览器
            context.close()
            
            # 自动执行同步脚本
            print(f"⚙️ 正在调用 {SYNC_SCRIPT}...")
            subprocess.run([sys.executable, SYNC_SCRIPT, TARGET_FILE])

            # 自动打开生成的报表 (macOS 专用命令)
            REPORT_FILE = "report_auto.html"
            if os.path.exists(REPORT_FILE):
                print(f"📖 正在打开报表: {REPORT_FILE}")
                subprocess.run(["open", REPORT_FILE])
        else:
            context.close()

if __name__ == "__main__":
    # 确保依赖已安装的简单提醒
    try:
        import playwright
    except ImportError:
        print("❌ 未找到 playwright 库。请运行: pip install playwright && playwright install")
        sys.exit(1)
        
    run_automation()
