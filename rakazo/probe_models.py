#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""只读探查：Bot 模型字段结构 + 模型连接列表。不做任何修改。"""
import json
from pathlib import Path
import batch_create_bots as B

auth = json.loads((Path(__file__).resolve().parent / ".rakazo_auth.json").read_text(encoding="utf-8"))
token, sid = auth["token"], auth["space_id"]
h = B.auth_headers(token, sid)


def dump(label, obj, maxlen=4000):
    s = json.dumps(obj, ensure_ascii=False, indent=2)
    print(f"\n===== {label} =====")
    print(s[:maxlen] + (" ...(truncated)" if len(s) > maxlen else ""))


# 1. space 全貌（含 bots）
st, spaces = B.rpc_call("spaces/list", {}, B.auth_headers(token, None))
print("spaces/list status:", st)
payload = spaces.get("json", {}) if isinstance(spaces, dict) else {}
current = payload.get("current", {}) if isinstance(payload, dict) else {}
bots = current.get("bots", []) if isinstance(current, dict) else []
print("current space:", current.get("id"), current.get("name"))
print("bot count:", len(bots))
print("\n--- per-bot model-related fields ---")
for b in bots:
    if not isinstance(b, dict):
        continue
    print(f"\n[{b.get('name')}] id={b.get('id')} spawnKey={b.get('spawnKey')}")
    for k, v in b.items():
        if any(t in k.lower() for t in ("model", "provider", "credential", "agent")):
            print(f"    {k} = {json.dumps(v, ensure_ascii=False)[:300]}")

# 2. 尝试各种可能的模型/凭证 RPC 端点
print("\n\n########## probing model/credential endpoints ##########")
candidates = [
    "models/list", "models/credentials/list", "credentials/list",
    "modelConnections/list", "aiModels/list", "models/getAvailable",
    "models/listAvailable", "settings/models/list", "models/available",
]
for path in candidates:
    try:
        st, resp = B.rpc_call(path, {}, h)
        body = resp.get("json", resp) if isinstance(resp, dict) else resp
        size = len(json.dumps(resp, ensure_ascii=False))
        print(f"\n--- {path}: HTTP {st}, resp size {size} ---")
        if st == 200:
            dump(f"{path} (200)", resp, 6000)
        else:
            print(json.dumps(resp, ensure_ascii=False)[:500])
    except Exception as e:
        print(f"\n--- {path}: EXC {e} ---")
