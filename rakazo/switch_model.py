#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
切换全部 Bot 的默认模型：sensenova-6.8-flash-lite (264k) -> sensenova-6.8-flash (1M)

- 幂等：已是目标模型的跳过；重复运行无副作用。
- 只改 modelProvider / modelId 两个字段，不动 instructions / 人设 / routine。
- 默认处理 space 内所有 Bot（含 Chief 补配）；--only-team 只处理 12 个团队成员。

用法：
  python switch_model.py --dry-run     # 预览将要变更的 Bot，不修改
  python switch_model.py               # 执行切换
  python switch_model.py --verify      # 只读：打印当前所有 Bot 的模型配置
"""
import argparse
import json
from pathlib import Path

import batch_create_bots as m

TARGET_PROVIDER = "openai-compatible"
TARGET_MODEL = "sensenova-6.8-flash"
OLD_MODEL = "sensenova-6.8-flash-lite"


def get_bots(h):
    _st, resp = m.rpc_call("bots/list", {}, h)
    if _st != 200:
        raise RuntimeError(f"bots/list 失败 HTTP {_st}: {resp}")
    return m.unwrap(resp) or []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="只预览，不修改")
    ap.add_argument("--verify", action="store_true", help="只读打印当前模型配置")
    ap.add_argument("--only-team", action="store_true", help="只处理 12 个团队成员，跳过 Chief")
    ap.add_argument("--model", default=TARGET_MODEL, help=f"目标模型 id（默认 {TARGET_MODEL}）")
    args = ap.parse_args()

    auth = json.loads((Path(__file__).resolve().parent / ".rakazo_auth.json").read_text(encoding="utf-8"))
    m.BASE_URL = "http://127.0.0.1:5173"
    h = m.auth_headers(auth["token"], auth["space_id"])
    bots = get_bots(h)
    print(f"space 内共 {len(bots)} 个 Bot，目标模型 = {args.model} (provider={TARGET_PROVIDER})\n")

    if args.verify:
        for b in bots:
            print(f"  {b.get('name'):20s} | provider={str(b.get('modelProvider')):18s} | modelId={b.get('modelId')}")
        return

    changed, skipped = 0, 0
    for b in bots:
        name, bid = b.get("name"), b.get("id")
        cur_p, cur_m = b.get("modelProvider"), b.get("modelId")
        if args.only_team and b.get("spawnKey") == "onboarding:first":
            print(f"  [跳过-Chief] {name} (--only-team)")
            skipped += 1
            continue
        if cur_p == TARGET_PROVIDER and cur_m == args.model:
            print(f"  [已是目标] {name} (modelId={cur_m})")
            skipped += 1
            continue
        tag = "补配" if not cur_m else f"{cur_m} -> {args.model}"
        print(f"  [{('预览' if args.dry_run else '切换')}] {name}: {tag}")
        if args.dry_run:
            changed += 1
            continue
        payload = {
            "botId": bid,
            "modelProvider": TARGET_PROVIDER,
            "modelId": args.model,
        }
        st, r = m.rpc_call("bots/update", payload, h)
        try:
            m.unwrap(r)
            if st == 200:
                print(f"      ✓ 成功 (HTTP {st})")
                changed += 1
            else:
                print(f"      ✗ 失败 HTTP {st}: {json.dumps(r, ensure_ascii=False)[:300]}")
        except Exception as e:
            print(f"      ✗ 解析失败 HTTP {st}: {e} | {json.dumps(r, ensure_ascii=False)[:300]}")

    print(f"\n汇总: {'预览' if args.dry_run else '变更'} {changed}, 跳过 {skipped}")

    if not args.dry_run:
        print("\n--- 回读校验 ---")
        for b in get_bots(h):
            flag = "OK" if (b.get("modelProvider") == TARGET_PROVIDER and b.get("modelId") == args.model) else "!!"
            print(f"  [{flag}] {b.get('name'):20s} | {b.get('modelProvider')} | {b.get('modelId')}")


if __name__ == "__main__":
    main()
