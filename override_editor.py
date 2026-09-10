#!/usr/bin/env python3
"""
manual_overrides.csv 本地编辑器

功能：
1. 在本地浏览器中编辑 manual_overrides.csv
2. 保存到本地 CSV
3. 可选地提交并推送 manual_overrides.csv
4. 触发 GitHub Actions 的 Scheduled Price Sync 工作流

启动：
  python3 override_editor.py

认证：
  默认使用 `gh auth login` 保存的 GitHub CLI 登录凭据触发 GitHub Actions。
  若未登录 GitHub CLI，也可设置 GITHUB_TOKEN / GH_TOKEN。

可选环境变量：
  GITHUB_TOKEN / GH_TOKEN        GitHub CLI 不可用时的令牌回退
  GITHUB_WORKFLOW_FILE           默认 scheduled-price-sync.yml
  GITHUB_REF                     默认当前分支，回退 main
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from inventory_core import _format_isbn_for_csv, _write_csv_atomic

REPO_ROOT = Path(__file__).resolve().parent
MANUAL_CSV_PATH = REPO_ROOT / "manual_overrides.csv"
HTML_PATH = REPO_ROOT / "override_editor.html"
DEFAULT_HEADERS = ["记录ID", "ISBN", "书名", "状态", "购入价格", "售出价格", "售出时间", "处理标签", "备注"]
DEFAULT_WORKFLOW_FILE = "scheduled-price-sync.yml"
DEFAULT_COMMIT_MESSAGE = "chore: update manual overrides via local editor"
WORKFLOW_TRIGGER_RETRIES = 3
WORKFLOW_TRIGGER_TIMEOUT_SECONDS = 20


def _is_retryable_network_error(reason: object) -> bool:
    if isinstance(reason, ssl.SSLEOFError):
        return True
    return isinstance(reason, TimeoutError)


def _json_response(handler: BaseHTTPRequestHandler, payload: dict, status: int = 200) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _text_response(handler: BaseHTTPRequestHandler, body: str, content_type: str = "text/html; charset=utf-8") -> None:
    data = body.encode("utf-8")
    handler.send_response(HTTPStatus.OK)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def _read_request_json(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length", "0"))
    raw = handler.rfile.read(length) if length > 0 else b"{}"
    return json.loads(raw.decode("utf-8"))


def _load_manual_csv() -> tuple[list[str], list[dict[str, str]]]:
    if not MANUAL_CSV_PATH.exists():
        return list(DEFAULT_HEADERS), []
    with MANUAL_CSV_PATH.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        headers = [h.strip() for h in (reader.fieldnames or DEFAULT_HEADERS)]
        rows = []
        for row in reader:
            rows.append({header: (row.get(header) or "") for header in headers})
    return headers, rows


def _normalize_row(headers: list[str], row: dict) -> dict[str, str]:
    normalized = {}
    for header in headers:
        value = row.get(header, "")
        if value is None:
            value = ""
        if not isinstance(value, str):
            value = str(value)
        normalized[header] = value.strip()
    normalized["ISBN"] = _format_isbn_for_csv(normalized.get("ISBN", ""))
    return normalized


def _save_manual_csv(headers: list[str], rows: list[dict]) -> None:
    clean_headers = [h.strip() for h in headers if h and h.strip()]
    if not clean_headers:
        clean_headers = list(DEFAULT_HEADERS)
    normalized_rows = [_normalize_row(clean_headers, row) for row in rows]
    _write_csv_atomic(str(MANUAL_CSV_PATH), clean_headers, normalized_rows)


def _run_git(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args],
        check=False,
        capture_output=True,
        text=True,
    )


def _get_branch_name() -> str:
    branch = _run_git(["branch", "--show-current"]).stdout.strip()
    return branch or "main"


def _get_origin_repo() -> tuple[str, str]:
    remote = _run_git(["config", "--get", "remote.origin.url"]).stdout.strip()
    if not remote:
        raise RuntimeError("未找到 git remote.origin.url")

    trimmed = remote[:-4] if remote.endswith(".git") else remote
    if trimmed.startswith("git@github.com:"):
        owner_repo = trimmed.split("git@github.com:", 1)[1]
    elif "github.com/" in trimmed:
        owner_repo = trimmed.split("github.com/", 1)[1]
    else:
        raise RuntimeError(f"无法解析 GitHub 仓库地址: {remote}")

    parts = owner_repo.split("/", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise RuntimeError(f"无法解析 GitHub 仓库 owner/repo: {remote}")
    return parts[0], parts[1]


def _get_github_token() -> str:
    """Read the current GitHub CLI token without exposing it to the editor UI."""
    environment = os.environ.copy()
    environment.pop("GITHUB_TOKEN", None)
    environment.pop("GH_TOKEN", None)
    result = subprocess.run(
        ["gh", "auth", "token"],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()

    return os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""


def _get_editor_config() -> dict:
    owner, repo = _get_origin_repo()
    token = _get_github_token()
    workflow_file = os.environ.get("GITHUB_WORKFLOW_FILE", DEFAULT_WORKFLOW_FILE)
    branch = os.environ.get("GITHUB_REF", _get_branch_name())
    return {
        "owner": owner,
        "repo": repo,
        "workflow_file": workflow_file,
        "branch": branch,
        "token_configured": bool(token),
    }


def _get_staged_paths() -> list[str]:
    result = _run_git(["diff", "--cached", "--name-only"])
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "读取 staged 文件失败")
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _fetch_origin(branch: str) -> None:
    fetch_result = _run_git(["fetch", "origin", branch])
    if fetch_result.returncode != 0:
        raise RuntimeError(fetch_result.stderr.strip() or fetch_result.stdout.strip() or "git fetch 失败")


def _get_ahead_behind(branch: str) -> tuple[int, int]:
    result = _run_git(["rev-list", "--left-right", "--count", f"HEAD...origin/{branch}"])
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "读取本地/远端同步状态失败")
    parts = result.stdout.strip().split()
    if len(parts) != 2:
        raise RuntimeError(f"无法解析本地/远端同步状态: {result.stdout.strip()}")
    return int(parts[0]), int(parts[1])


def _ensure_synced_with_origin(branch: str) -> None:
    _fetch_origin(branch)
    ahead, behind = _get_ahead_behind(branch)
    if ahead or behind:
        raise RuntimeError(
            f"本地 {branch} 与 origin/{branch} 未同步（ahead {ahead}, behind {behind}）。"
            "请先确认提交已成功推送，并处理远端新增提交后再触发 GitHub Actions。"
        )


def _get_unpushed_paths(branch: str) -> list[str]:
    result = _run_git(["diff", "--name-only", f"origin/{branch}..HEAD"])
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "读取未推送文件失败")
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _push_pending_manual_commits(branch: str) -> dict | None:
    _fetch_origin(branch)
    ahead, behind = _get_ahead_behind(branch)
    if ahead == 0:
        if behind:
            raise RuntimeError(
                f"manual_overrides.csv 没有新的可提交变更，但远端 origin/{branch} 有 {behind} 个新提交。"
                "请先拉取远端更新后刷新页面。"
            )
        return None

    unpushed_paths = _get_unpushed_paths(branch)
    unexpected = [path for path in unpushed_paths if path != "manual_overrides.csv"]
    if unexpected:
        raise RuntimeError(
            "存在非 manual_overrides.csv 的本地未推送提交，已停止自动推送："
            f"{', '.join(unexpected)}"
        )

    if behind:
        pull_result = _run_git(["pull", "--rebase", "origin", branch])
        if pull_result.returncode != 0:
            raise RuntimeError(pull_result.stderr.strip() or pull_result.stdout.strip() or "git pull --rebase 失败")

    push_result = _run_git(["push", "origin", branch])
    if push_result.returncode != 0:
        raise RuntimeError(push_result.stderr.strip() or push_result.stdout.strip() or "git push 失败")

    _ensure_synced_with_origin(branch)
    commit_sha = _run_git(["rev-parse", "HEAD"]).stdout.strip()
    return {"message": "manual_overrides.csv 没有新的可提交变更；已重试推送本地未推送的 override 提交。", "commit": commit_sha}


def _commit_and_push_manual(commit_message: str) -> dict:
    add_result = _run_git(["add", "manual_overrides.csv"])
    if add_result.returncode != 0:
        raise RuntimeError(add_result.stderr.strip() or "git add 失败")

    staged_paths = _get_staged_paths()
    unexpected = [path for path in staged_paths if path != "manual_overrides.csv"]
    if unexpected:
        raise RuntimeError(f"存在其他已暂存文件，已停止自动提交：{', '.join(unexpected)}")

    diff_result = _run_git(["diff", "--cached", "--quiet", "--", "manual_overrides.csv"])
    if diff_result.returncode == 0:
        retry_result = _push_pending_manual_commits(_get_branch_name())
        return retry_result or {"message": "manual_overrides.csv 没有新的可提交变更，且没有本地未推送提交。"}
    if diff_result.returncode not in (0, 1):
        raise RuntimeError(diff_result.stderr.strip() or "检查缓存差异失败")

    commit_result = _run_git(["commit", "-m", commit_message, "--", "manual_overrides.csv"])
    if commit_result.returncode != 0:
        raise RuntimeError(commit_result.stderr.strip() or commit_result.stdout.strip() or "git commit 失败")

    branch = _get_branch_name()
    pull_result = _run_git(["pull", "--rebase", "origin", branch])
    if pull_result.returncode != 0:
        raise RuntimeError(pull_result.stderr.strip() or pull_result.stdout.strip() or "git pull --rebase 失败")

    push_result = _run_git(["push", "origin", branch])
    if push_result.returncode != 0:
        raise RuntimeError(push_result.stderr.strip() or push_result.stdout.strip() or "git push 失败")

    _ensure_synced_with_origin(branch)
    commit_sha = _run_git(["rev-parse", "HEAD"]).stdout.strip()
    return {"message": "已提交并推送 manual_overrides.csv，且本地/远端已同步。", "commit": commit_sha}


def _trigger_github_workflow() -> dict:
    config = _get_editor_config()
    _ensure_synced_with_origin(config["branch"])
    token = _get_github_token()
    if not token:
        raise RuntimeError("未找到 GitHub CLI 登录或 GITHUB_TOKEN/GH_TOKEN，无法触发 GitHub Actions")

    url = (
        f"https://api.github.com/repos/{config['owner']}/{config['repo']}"
        f"/actions/workflows/{config['workflow_file']}/dispatches"
    )
    payload = json.dumps({"ref": config["branch"]}).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
    )
    for attempt in range(1, WORKFLOW_TRIGGER_RETRIES + 1):
        try:
            with urllib.request.urlopen(request, timeout=WORKFLOW_TRIGGER_TIMEOUT_SECONDS) as response:
                if response.status not in (HTTPStatus.NO_CONTENT, HTTPStatus.CREATED, HTTPStatus.OK):
                    raise RuntimeError(f"触发工作流失败，HTTP {response.status}")
                break
        except urllib.error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="ignore")
            retryable_status = exc.code in (
                HTTPStatus.TOO_MANY_REQUESTS,
                HTTPStatus.BAD_GATEWAY,
                HTTPStatus.SERVICE_UNAVAILABLE,
                HTTPStatus.GATEWAY_TIMEOUT,
            )
            if retryable_status and attempt < WORKFLOW_TRIGGER_RETRIES:
                time.sleep(attempt)
                continue
            raise RuntimeError(f"触发工作流失败，HTTP {exc.code}: {details}") from exc
        except urllib.error.URLError as exc:
            if attempt < WORKFLOW_TRIGGER_RETRIES and _is_retryable_network_error(exc.reason):
                time.sleep(attempt)
                continue
            raise RuntimeError(f"触发工作流失败：{exc.reason}") from exc

    return {"message": f"已触发 GitHub Actions：{config['workflow_file']} @ {config['branch']}"}


class OverrideEditorHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            _text_response(self, HTML_PATH.read_text(encoding="utf-8"))
            return

        if self.path == "/api/data":
            headers, rows = _load_manual_csv()
            _json_response(
                self,
                {
                    "headers": headers,
                    "rows": rows,
                    "config": _get_editor_config(),
                },
            )
            return

        _json_response(self, {"error": "Not Found"}, status=404)

    def do_POST(self) -> None:
        try:
            payload = _read_request_json(self)
            if self.path == "/api/save":
                headers = payload.get("headers") or DEFAULT_HEADERS
                rows = payload.get("rows") or []
                _save_manual_csv(headers, rows)
                _json_response(self, {"message": "已保存到 manual_overrides.csv。"})
                return

            if self.path == "/api/commit-push":
                commit_message = (payload.get("message") or DEFAULT_COMMIT_MESSAGE).strip()
                result = _commit_and_push_manual(commit_message)
                _json_response(self, result)
                return

            if self.path == "/api/trigger-sync":
                result = _trigger_github_workflow()
                _json_response(self, result)
                return

            if self.path == "/api/save-publish-sync":
                headers = payload.get("headers") or DEFAULT_HEADERS
                rows = payload.get("rows") or []
                commit_message = (payload.get("message") or DEFAULT_COMMIT_MESSAGE).strip()
                _save_manual_csv(headers, rows)
                commit_result = _commit_and_push_manual(commit_message)
                trigger_result = _trigger_github_workflow()
                _json_response(
                    self,
                    {
                        "message": "保存、推送并触发同步完成。",
                        "commit": commit_result.get("commit"),
                        "details": [commit_result["message"], trigger_result["message"]],
                    },
                )
                return

            _json_response(self, {"error": "Not Found"}, status=404)
        except Exception as exc:  # surface explicit error to UI
            _json_response(self, {"error": str(exc)}, status=400)

    def log_message(self, format: str, *args) -> None:
        return


def main() -> int:
    parser = argparse.ArgumentParser(description="启动 manual_overrides.csv 本地编辑器")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址，默认 127.0.0.1")
    parser.add_argument("--port", type=int, default=8765, help="监听端口，默认 8765")
    parser.add_argument("--no-browser", action="store_true", help="启动后不自动打开浏览器")
    args = parser.parse_args()

    if not HTML_PATH.exists():
        print(f"❌ 缺少页面文件: {HTML_PATH}")
        return 1

    server = ThreadingHTTPServer((args.host, args.port), OverrideEditorHandler)
    url = f"http://{args.host}:{args.port}"
    print(f"✅ 本地编辑器已启动: {url}")
    print("   可编辑 manual_overrides.csv，并可提交推送/触发 GitHub Actions。")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 已停止本地编辑器。")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
