#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rakazo 批量建 Bot 脚本 —— 英文研发团队（Max / Penny / Codey / Buggsy / Tina / Hazel）

与 batch_create_bots.py（中文组）完全独立：
  - 人设目录：rakazo-team-en/
  - Bot 名英文名，@mention 直接用
  - spawnKey 前缀 rakazo-en-，与中文组 rakazo-team- 隔离，互不覆盖
  - 共用同一 token 缓存 .rakazo_auth.json（同一账号 / 同一 space）

功能：
  1. 复用缓存 token（或首次登录）登录本地 Rakazo
  2. 读取 rakazo-team-en/ 下 6 份人设 markdown
  3. 通过 oRPC 批量创建 Bot（spawnKey 幂等，重复运行不产生重复 Bot）
  4. 可选：建一个群把 6 个 Bot 拉进去

用法：
  python batch_create_bots_en.py                 # 创建 6 个 Bot（幂等）
  python batch_create_bots_en.py --group         # 额外建群
  python batch_create_bots_en.py --dry-run       # 只打印 payload，不创建
  python batch_create_bots_en.py --list          # 列出当前 space 已有 Bot
  python batch_create_bots_en.py --login         # 强制重新登录刷新 token
  python batch_create_bots_en.py --base-url URL  # 自定义 Rakazo 地址
"""

import argparse
import getpass
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE_URL = "http://127.0.0.1:5173"
TEAM_DIR = Path(__file__).resolve().parent.parent / "rakazo-team-en"
TOKEN_CACHE = Path(__file__).resolve().parent / ".rakazo_auth.json"

# 人设文件名（按团队顺序）
ROLE_FILES = [
    "01-Max-产品经理.md",
    "02-Pixel Penny-设计师.md",
    "03-Codey-全栈开发.md",
    "04-Buggsy-测试工程师.md",
    "05-Tracker Tina-项目经理.md",
    "06-Hype Hazel-市场增长.md",
]

# Bot 显示名（Rakazo 里 @mention 用的英文名）
BOT_NAMES = ["Max", "Pixel Penny", "Codey", "Buggsy", "Tracker Tina", "Hype Hazel"]

# 与中文组隔离的 spawnKey 前缀
SPAWN_PREFIX = "rakazo-en-"
GROUP_NAME = "English R&D Team"


def http_json(method, url, headers=None, body=None, timeout=30):
    """发 HTTP 请求，返回 (status, parsed_json, response_headers)。"""
    data = None
    hdrs = {"Content-Type": "application/json"}
    if headers:
        hdrs.update(headers)
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            status = resp.status
            resp_headers = dict(resp.headers.items())
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        status = e.code
        resp_headers = dict(e.headers.items()) if e.headers else {}
    except urllib.error.URLError as e:
        raise RuntimeError(f"无法连接 {url}: {e.reason}") from e
    try:
        parsed = json.loads(raw) if raw else None
    except json.JSONDecodeError:
        parsed = {"_raw": raw}
    return status, parsed, resp_headers


def parse_persona(path):
    """解析人设文件：返回 (name, description, instructions)。"""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    # 标题行：# Max —— 产品经理 / # Pixel Penny —— 设计师
    m = re.match(r"^#\s*(.+?)\s*[—–-]+\s*(.+)$", lines[0])
    if m:
        en, role = m.group(1).strip(), m.group(2).strip()
    else:
        en, role = path.stem, "AI Assistant"
    desc = ""
    for line in lines[1:6]:
        if line.strip().startswith(">"):
            desc = line.strip().lstrip("> ").strip()
            break
    if not desc:
        desc = f"{en} —— {role}"
    return en, desc[:200], text[:20000]


def load_cached_auth():
    if not TOKEN_CACHE.exists():
        return None
    try:
        data = json.loads(TOKEN_CACHE.read_text(encoding="utf-8"))
        if data.get("base_url") == BASE_URL and data.get("token"):
            return data
    except Exception:
        pass
    return None


def save_auth(token, space_id, email):
    TOKEN_CACHE.write_text(
        json.dumps({"base_url": BASE_URL, "token": token,
                    "space_id": space_id, "email": email}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    try:
        TOKEN_CACHE.chmod(0o600)
    except Exception:
        pass


def extract_token(resp, resp_headers):
    """从登录响应提取签名 token，兼容 body / session / header / cookie。"""
    if isinstance(resp, dict):
        for key in ("token", "authToken", "accessToken"):
            v = resp.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()
        sess = resp.get("session")
        if isinstance(sess, dict):
            v = sess.get("token")
            if isinstance(v, str) and v.strip():
                return v.strip()
    lower_headers = {str(k).lower(): v for k, v in (resp_headers or {}).items()}
    for h in ("set-auth-token", "x-auth-token", "auth-token"):
        v = lower_headers.get(h)
        if isinstance(v, str) and v.strip():
            return v.strip()
    cookie_header = ""
    for k, v in lower_headers.items():
        if k in ("set-cookie", "set-cookie2"):
            cookie_header += (";" if cookie_header else "") + str(v)
    m = re.search(r"better-auth\.session_token=([^;,\s]+)", cookie_header, re.I)
    if m:
        try:
            import urllib.parse
            return urllib.parse.unquote(m.group(1))
        except Exception:
            return m.group(1)
    return None


def login(email, password):
    status, resp, resp_headers = http_json(
        "POST", f"{BASE_URL}/api/auth/sign-in/email",
        body={"email": email, "password": password},
    )
    if status != 200 or not isinstance(resp, dict):
        raise RuntimeError(f"登录失败 (HTTP {status}): {resp}")
    token = extract_token(resp, resp_headers)
    if not token:
        detail = {
            "body_fields": list(resp.keys()),
            "header_fields": sorted(str(k).lower() for k in (resp_headers or {})),
        }
        raise RuntimeError("登录响应没找到 token。诊断: " + json.dumps(detail, ensure_ascii=False))
    masked = token[:8] + "..." + (token[-4:] if len(token) > 12 else "")
    print(f"  取得 token: {masked}（长度 {len(token)}，含签名={'.' in token}）")
    headers = auth_headers(token, None)
    st, spaces = rpc_call("spaces/list", {}, headers)
    if st != 200:
        raise RuntimeError(f"登录后读取 space 失败 (HTTP {st}): {spaces}")
    space_id = extract_space_id(spaces)
    if not space_id:
        raise RuntimeError("无法获取 space id，请确认账号已初始化 Space")
    return token, space_id


def extract_space_id(spaces_resp):
    try:
        payload = spaces_resp.get("json", {})
        if isinstance(payload, list):
            for s in payload:
                if isinstance(s, dict) and s.get("id"):
                    return s["id"]
        if isinstance(payload, dict):
            current = payload.get("current")
            if isinstance(current, dict) and current.get("id"):
                return current["id"]
            if payload.get("defaultSpaceId"):
                return payload["defaultSpaceId"]
            for key in ("spaces", "items", "data"):
                arr = payload.get(key)
                if isinstance(arr, list) and arr and isinstance(arr[0], dict):
                    return arr[0].get("id")
            if payload.get("id"):
                return payload["id"]
    except Exception:
        pass
    return None


def auth_headers(token, space_id):
    h = {"Authorization": f"Bearer {token}"}
    if space_id:
        h["x-rakazo-space-id"] = space_id
    return h


def rpc_call(path, payload, headers, timeout=60):
    url = f"{BASE_URL}/rpc/{path}"
    status, parsed, _ = http_json("POST", url, headers=headers, body={"json": payload}, timeout=timeout)
    return status, parsed


def unwrap(resp):
    if not isinstance(resp, dict):
        return resp
    body = resp.get("json", resp)
    if isinstance(body, dict) and "code" in body and "defined" in body:
        raise RuntimeError(f"RPC 错误 [{body.get('code')}]: {body.get('message')}")
    return body


def get_bots(headers):
    _st, resp = rpc_call("bots/list", {}, headers)
    return unwrap(resp) or []


def ensure_auth(force_login=False):
    cached = None if force_login else load_cached_auth()
    if cached:
        return cached["token"], cached["space_id"], cached.get("email", "")
    print("首次运行需要登录 Rakazo。")
    email = input("邮箱（默认 fire001@163.com）: ").strip() or "fire001@163.com"
    password = getpass.getpass("密码（输入不回显）: ")
    token, space_id = login(email, password)
    save_auth(token, space_id, email)
    print(f"登录成功，space = {space_id}，token 已缓存到 {TOKEN_CACHE.name}")
    return token, space_id, email


def main():
    global BASE_URL
    ap = argparse.ArgumentParser(description="批量创建 Rakazo Bot（英文研发团队 6 人）")
    ap.add_argument("--base-url", default=BASE_URL, help="Rakazo 地址")
    ap.add_argument("--login", action="store_true", help="强制重新登录")
    ap.add_argument("--group", action="store_true", help="创建群并把 6 个 Bot 拉进去")
    ap.add_argument("--dry-run", action="store_true", help="只打印 payload，不执行")
    ap.add_argument("--list", action="store_true", help="列出已有 Bot")
    args = ap.parse_args()
    BASE_URL = args.base_url.rstrip("/")

    if args.dry_run:
        for i, (fname, botname) in enumerate(zip(ROLE_FILES, BOT_NAMES), start=1):
            path = TEAM_DIR / fname
            if not path.exists():
                print(f"[跳过] 找不到 {fname}")
                continue
            name, desc, instructions = parse_persona(path)
            payload = {
                "name": botname, "description": desc, "instructions": instructions,
                "fleetManagement": True, "spawnKey": f"{SPAWN_PREFIX}{i:02d}",
            }
            print(f"\n=== {botname} ===")
            print(json.dumps({**payload, "instructions": instructions[:120] + "..."},
                             ensure_ascii=False, indent=2))
            print(f"instructions 长度: {len(instructions)} 字符")
        return

    token, space_id, email = ensure_auth(force_login=args.login)
    headers = auth_headers(token, space_id)

    if args.list:
        bots = get_bots(headers)
        print(f"当前 space 有 {len(bots)} 个 Bot:")
        for b in bots:
            print(f"  - {b.get('name')} (id={b.get('id')})")
        return

    existing = get_bots(headers)
    existing_names = {b.get("name") for b in existing}
    print(f"当前已有 {len(existing)} 个 Bot: {', '.join(sorted(str(n) for n in existing_names)) or '(空)'}")

    created_ids = []
    for i, (fname, botname) in enumerate(zip(ROLE_FILES, BOT_NAMES), start=1):
        path = TEAM_DIR / fname
        if not path.exists():
            print(f"[跳过] 找不到 {fname}")
            continue
        name, desc, instructions = parse_persona(path)
        spawn_key = f"{SPAWN_PREFIX}{i:02d}"
        payload = {
            "name": botname,
            "description": desc,
            "instructions": instructions,
            "fleetManagement": True,
            "spawnKey": spawn_key,
        }
        existing_bot = next((b for b in existing if b.get("name") == botname), None)
        if existing_bot:
            print(f"[已存在] {botname} (id={existing_bot.get('id')})，跳过")
            created_ids.append(existing_bot.get("id"))
            continue
        status, resp = rpc_call("bots/create", payload, headers)
        try:
            bot = unwrap(resp)
            bot_id = bot.get("id")
            created_ids.append(bot_id)
            print(f"[创建成功] {botname} (id={bot_id})")
        except RuntimeError as e:
            print(f"[失败] {botname}: {e} (HTTP {status})")

    print(f"\n完成：{len([i for i in created_ids if i])} 个 Bot 就绪。")

    if args.group:
        valid_ids = [i for i in created_ids if i]
        if len(valid_ids) < 2:
            print("可用 Bot 少于 2 个，跳过建群。")
            return
        _gst, gresp = rpc_call("groups/list", {}, headers)
        groups = unwrap(gresp) or []
        if any(g.get("name") == GROUP_NAME for g in groups):
            print(f"[已存在] 群「{GROUP_NAME}」已存在，跳过。")
            return
        status, resp = rpc_call("groups/create", {"name": GROUP_NAME, "botIds": valid_ids}, headers)
        try:
            group = unwrap(resp)
            print(f"[建群成功] {GROUP_NAME} (id={group.get('id')})，成员 {len(valid_ids)} 个 Bot")
        except RuntimeError as e:
            print(f"[建群失败] {e} (HTTP {status})")

    print("\n下一步：打开 Web UI，给每个 Bot 连接 sensenova 模型（OpenAI-compatible）。")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n已取消。")
        sys.exit(130)
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)
