#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置「中心调度」协作模式（统一入口 + 项目经理派活 + 定时同步）

把中文组（司南团队）和英文组（Max 团队）从链式直连改造为：
  用户只 @ 入口（司南 / Max）沟通需求 → 入口出 PRD 交项目经理（节拍 / Tracker Tina）
  → 项目经理拆单、逐个 @ 角色派活 → 执行角色只向项目经理汇报
  → 用户只做「开头确认方向」和「最终批准」两件事
  → 项目经理每 2 小时在群里同步进度（routine 定时任务）

功能（可单独执行）：
  --inject    给本地人设 md 注入「中心调度」协议段落（幂等）
  --apply     把最终 instructions 写回线上 12 个 Bot，并绑定 SenseNova 模型（幂等）
  --routine   给两组项目经理建每 2 小时进度同步 routine（幂等）
  --dry-run   只打印将要注入/提交的内容，不修改任何东西
  不带参数     依次执行 inject → apply → routine

复用 batch_create_bots.py 的登录态与 RPC 封装，共享 .rakazo_auth.json。
"""

import argparse
import json
import sys
from pathlib import Path

import batch_create_bots as m

ROOT = Path(__file__).resolve().parent.parent
MODEL_PROVIDER = "openai-compatible"
MODEL_ID = "sensenova-6.8-flash"
MARKER = "## 工作模式（最高优先级）：中心调度"

# 每组：bot 名 -> (人设文件相对 rakazo-team* 目录, 中心调度协议正文)
CN = {
    "司南 Compass": ("01-司南-Compass-产品经理.md", """## 工作模式（最高优先级）：中心调度

本团队采用「统一入口 + 项目经理调度」模式，以下规则优先于其他一切协作约定：
- **你是团队唯一的需求入口**：用户只在群里 @司南 沟通需求，不再逐个 @ 其他人。有人绕过你直接给用户派活或越级接单时，你提醒回到正规流程。
- 用户确认需求方向后，你输出 PRD，然后 `@节拍` 交接，由节拍拆解工单、派活。你不再自己往下派活，也不直接 @ 灵犀/基石/破壁/燎原。
- 你只对需求方向与 PRD 质量负责，不替项目经理派工，不替其他角色做执行。
- 用户全程只做两件事：开头确认需求方向、最后合并前点批准。除此之外不要向用户索要决策或 @ 用户。"""),
    "灵犀 Intuition": ("02-灵犀-Intuition-设计师.md", """## 工作模式（最高优先级）：中心调度

本团队采用「统一入口 + 项目经理调度」模式，以下规则优先于其他一切协作约定：
- 你只接收 `@节拍` 派发的设计工单；不直接接收用户或其他角色的越级需求，收到则转给节拍。
- 完成后向 `@节拍` 汇报交付物，由节拍统一在群里同步进度；不直接 @ 用户邀功或请示。
- 不自行派活给其他角色，不跳过节拍直接找基石/破壁。
- 用户只在开头确认方向、最终点批准，日常不要 @ 用户。"""),
    "基石 Cornerstone": ("03-基石-Cornerstone-全栈开发.md", """## 工作模式（最高优先级）：中心调度

本团队采用「统一入口 + 项目经理调度」模式，以下规则优先于其他一切协作约定：
- 你只接收 `@节拍` 派发的开发工单（含关联的司南 PRD 与灵犀设计）；不接跳过派单的裸需求，收到则转给节拍。
- 完成后向 `@节拍` 汇报代码交付与验证结果，由节拍交破壁测试、并在群里同步进度；不直接 @ 用户，也不自行宣称上线。
- 修复 bug 时只接收 `@节拍` 转来的破壁测试结论，改完仍报节拍复验。
- 用户只在开头确认方向、最终合并前点批准，日常不要 @ 用户。"""),
    "破壁 Breaker": ("04-破壁-Breaker-测试工程师.md", """## 工作模式（最高优先级）：中心调度

本团队采用「统一入口 + 项目经理调度」模式，以下规则优先于其他一切协作约定：
- 你只接收 `@节拍` 派发的测试工单（含基石的交付说明）；不测未派单的东西。
- 质量结论（通过 / 打回）一律向 `@节拍` 汇报，由节拍决定是否推进或升级给用户；你不直接 @ 用户，更不越级找燎原宣传。
- 打回时经 `@节拍` 转给基石修复，复验后仍报节拍。
- 用户只在开头确认方向、最终合并前点批准，日常不要 @ 用户。"""),
    "节拍 Metronome": ("05-节拍-Metronome-项目经理.md", """## 工作模式（最高优先级）：中心调度

你是本团队唯一的调度中枢，以下规则优先于其他一切协作约定：
- 统一接收 `@司南` 的 PRD，拆解成颗粒化工单，再逐个 @ 对应角色派活（谁做什么由你安排）。用户已不再逐个 @ 角色，派活是你的职责。
- 各角色完成后向你汇报，由你汇总、决定推进下一棒；遇到阻塞或返工及时升级给用户。
- **你要定时在群里同步各角色的工作进度**（系统已为你配置每 2 小时的定时任务自动汇报）；被 `@节拍 现在到哪了` 时也要立即给出当前棒次、各角色状态、卡点与下一棒。
- 你只调度与跟踪，不亲自写 PRD/设计/代码/测试，不替用户做最终批准，也不自行启动燎原的推广。
- 用户全程只做两件事：开头确认需求方向、最终合并前点批准。"""),
    "燎原 Wildfire": ("06-燎原-Wildfire-市场增长.md", """## 工作模式（最高优先级）：中心调度

本团队采用「统一入口 + 项目经理调度」模式，以下规则优先于其他一切协作约定：
- 你只在用户明确批准上线后才启动推广；未获批准不出稿，即使被 @ 也先确认是否已获批准。
- 你只接收 `@节拍` 派发的推广工单，完成后向 `@节拍` 汇报；不直接从破壁/基石接未验收、未批准的东西来宣传。
- 不自行派活，不直接 @ 用户邀功。
- 用户只在开头确认方向、最终点批准，日常不要 @ 用户。"""),
}

EN = {
    "Max": ("01-Max-产品经理.md", """## 工作模式（最高优先级）：中心调度

本团队采用「统一入口 + 项目经理调度」模式，以下规则优先于其他一切协作约定：
- **你是团队唯一的需求入口**：用户只在群里 @Max 沟通需求，不再逐个 @ 其他人。有人绕过你直接给用户派活或越级接单时，你提醒回到正规流程。
- 用户确认需求方向后，你输出 PRD，然后 `@Tracker Tina` 交接，由 Tina 拆解工单、派活。你不再自己往下派活，也不直接 @ Pixel Penny/Codey/Buggsy/Hype Hazel。
- 你只对需求方向与 PRD 质量负责，不替项目经理派工，不替其他角色做执行。
- 用户全程只做两件事：开头确认需求方向、最后合并前点批准。除此之外不要向用户索要决策或 @ 用户。"""),
    "Pixel Penny": ("02-Pixel Penny-设计师.md", """## 工作模式（最高优先级）：中心调度

本团队采用「统一入口 + 项目经理调度」模式，以下规则优先于其他一切协作约定：
- 你只接收 `@Tracker Tina` 派发的设计工单；不直接接收用户或其他角色的越级需求，收到则转给 Tina。
- 完成后向 `@Tracker Tina` 汇报交付物，由 Tina 统一在群里同步进度；不直接 @ 用户邀功或请示。
- 不自行派活给其他角色，不跳过 Tina 直接找 Codey/Buggsy。
- 用户只在开头确认方向、最终点批准，日常不要 @ 用户。"""),
    "Codey": ("03-Codey-全栈开发.md", """## 工作模式（最高优先级）：中心调度

本团队采用「统一入口 + 项目经理调度」模式，以下规则优先于其他一切协作约定：
- 你只接收 `@Tracker Tina` 派发的开发工单（含关联的 Max PRD 与 Pixel Penny 设计）；不接跳过派单的裸需求，收到则转给 Tina。
- 完成后向 `@Tracker Tina` 汇报代码交付与验证结果，由 Tina 交 Buggsy 测试、并在群里同步进度；不直接 @ 用户，也不自行宣称上线。
- 修复 bug 时只接收 `@Tracker Tina` 转来的 Buggsy 测试结论，改完仍报 Tina 复验。
- 用户只在开头确认方向、最终合并前点批准，日常不要 @ 用户。"""),
    "Buggsy": ("04-Buggsy-测试工程师.md", """## 工作模式（最高优先级）：中心调度

本团队采用「统一入口 + 项目经理调度」模式，以下规则优先于其他一切协作约定：
- 你只接收 `@Tracker Tina` 派发的测试工单（含 Codey 的交付说明）；不测未派单的东西。
- 质量结论（通过 / 打回）一律向 `@Tracker Tina` 汇报，由 Tina 决定是否推进或升级给用户；你不直接 @ 用户，更不越级找 Hype Hazel 宣传。
- 打回时经 `@Tracker Tina` 转给 Codey 修复，复验后仍报 Tina。
- 用户只在开头确认方向、最终合并前点批准，日常不要 @ 用户。"""),
    "Tracker Tina": ("05-Tracker Tina-项目经理.md", """## 工作模式（最高优先级）：中心调度

你是本团队唯一的调度中枢，以下规则优先于其他一切协作约定：
- 统一接收 `@Max` 的 PRD，拆解成颗粒化工单，再逐个 @ 对应角色派活（谁做什么由你安排）。用户已不再逐个 @ 角色，派活是你的职责。
- 各角色完成后向你汇报，由你汇总、决定推进下一棒；遇到阻塞或返工及时升级给用户。
- **你要定时在群里同步各角色的工作进度**（系统已为你配置每 2 小时的定时任务自动汇报）；被 `@Tracker Tina 现在到哪了` 时也要立即给出当前棒次、各角色状态、卡点与下一棒。
- 你只调度与跟踪，不亲自写 PRD/设计/代码/测试，不替用户做最终批准，也不自行启动 Hype Hazel 的推广。
- 用户全程只做两件事：开头确认需求方向、最终合并前点批准。"""),
    "Hype Hazel": ("06-Hype Hazel-市场增长.md", """## 工作模式（最高优先级）：中心调度

本团队采用「统一入口 + 项目经理调度」模式，以下规则优先于其他一切协作约定：
- 你只在用户明确批准上线后才启动推广；未获批准不出稿，即使被 @ 也先确认是否已获批准。
- 你只接收 `@Tracker Tina` 派发的推广工单，完成后向 `@Tracker Tina` 汇报；不直接从 Buggsy/Codey 接未验收、未批准的东西来宣传。
- 不自行派活，不直接 @ 用户邀功。
- 用户只在开头确认方向、最终点批准，日常不要 @ 用户。"""),
}

TEAMS = [
    ("cn", ROOT / "rakazo-team", CN, "节拍 Metronome", "Rakazo 中文组-进度同步"),
    ("en", ROOT / "rakazo-team-en", EN, "Tracker Tina", "Rakazo English Team-Progress Sync"),
]


def inject_local(team_dir, config, dry=False):
    """给人设 md 注入中心调度段落（幂等）。返回最终全文 dict: bot名 -> text。"""
    result = {}
    for bot, (fname, block) in config.items():
        path = team_dir / fname
        if not path.exists():
            print(f"  [跳过] 找不到 {fname}")
            continue
        text = path.read_text(encoding="utf-8")
        if MARKER in text:
            print(f"  [已注入] {fname}")
        else:
            # 插到正文第一节「## 」之前（人设标题与引用行之后）
            idx = text.find("\n## ")
            if idx == -1:
                new_text = text.rstrip() + "\n\n" + block + "\n"
            else:
                new_text = text[:idx + 1] + "\n" + block + "\n" + text[idx + 1:]
            if dry:
                print(f"  [将注入] {fname}")
                new_text = text  # dry-run 不真正改
            else:
                path.write_text(new_text, encoding="utf-8")
                print(f"  [注入成功] {fname}")
        result[bot] = path.read_text(encoding="utf-8")[:20000]
    return result


def apply_online(config, texts, dry=False):
    """把全文 instructions 写回线上 Bot 并绑定模型。"""
    auth = m.load_cached_auth()
    if not auth:
        print("  无 token 缓存，请先运行 batch_create_bots.py 登录。")
        return
    m.BASE_URL = "http://127.0.0.1:5173"
    h = m.auth_headers(auth["token"], auth["space_id"])
    _st, resp = m.rpc_call("bots/list", {}, h)
    bots = m.unwrap(resp) or []
    by_name = {b.get("name"): b for b in bots}
    for bot_name, text in texts.items():
        b = by_name.get(bot_name)
        if not b:
            print(f"  [跳过] 线上无 Bot: {bot_name}")
            continue
        payload = {
            "botId": b["id"],
            "instructions": text,
            "modelProvider": MODEL_PROVIDER,
            "modelId": MODEL_ID,
        }
        if dry:
            print(f"  [将更新] {bot_name} (id={b['id']}, instructions {len(text)} 字符)")
            continue
        st, r = m.rpc_call("bots/update", payload, h)
        try:
            m.unwrap(r)
            print(f"  [更新成功] {bot_name} (id={b['id']})")
        except RuntimeError as e:
            print(f"  [失败] {bot_name}: {e} (HTTP {st})")


def sync_routine(manager_bot, routine_name, dry=False):
    """给项目经理建每 2 小时进度同步 routine（幂等）。"""
    auth = m.load_cached_auth()
    m.BASE_URL = "http://127.0.0.1:5173"
    h = m.auth_headers(auth["token"], auth["space_id"])
    _st, resp = m.rpc_call("bots/list", {}, h)
    bots = m.unwrap(resp) or []
    b = next((x for x in bots if x.get("name") == manager_bot), None)
    if not b:
        print(f"  [跳过] 线上无项目经理 Bot: {manager_bot}")
        return
    bot_id = b["id"]
    _st, rl = m.rpc_call("routines/list", {"botId": bot_id}, h)
    existing = m.unwrap(rl) if _st == 200 else []
    # 幂等：同名 routine 已存在则跳过；并清理历史重复项（保留第一个）
    matched = [r for r in (existing or []) if r.get("name") == routine_name]
    if matched:
        print(f"  [已存在] routine「{routine_name}」(共 {len(matched)} 个)")
        for dup in matched[1:]:
            if not dry:
                m.rpc_call("routines/remove", {"routineId": dup["id"]}, h)
                print(f"  [清理重复] {dup['id']}")
        return
    prompt = (
        "请在群里同步当前团队的工作进度：按棒次说明各角色（需求/设计/开发/测试/推广）"
        "的当前状态、已完成项、进行中项、阻塞点与下一棒接手人。若一切按计划，简明扼要；"
        "若有卡点或返工，明确指出并建议是否升级给用户。不要替用户做批准决定。"
    )
    payload = {
        "botId": bot_id,
        "name": routine_name,
        "prompt": prompt,
        "crons": ["0 */2 * * *"],
        "timezone": "Asia/Shanghai",
        "active": True,
        "inChat": True,
        "notify": True,
        "modelProvider": MODEL_PROVIDER,
        "modelId": MODEL_ID,
    }
    if dry:
        print(f"  [将建] routine「{routine_name}」for {manager_bot} (botId={bot_id}) crons={payload['crons']}")
        return
    st, r = m.rpc_call("routines/create", payload, h)
    try:
        created = m.unwrap(r)
        print(f"  [建成功] routine「{routine_name}」(id={created.get('id')}, active={created.get('active')})")
    except RuntimeError as e:
        print(f"  [失败] routine「{routine_name}」: {e} (HTTP {st})")


def main():
    ap = argparse.ArgumentParser(description="配置中心调度协作模式")
    ap.add_argument("--inject", action="store_true", help="注入本地人设段落")
    ap.add_argument("--apply", action="store_true", help="更新线上 Bot 人设与模型")
    ap.add_argument("--routine", action="store_true", help="建定时同步 routine")
    ap.add_argument("--dry-run", action="store_true", help="只打印不修改")
    args = ap.parse_args()
    do_all = not (args.inject or args.apply or args.routine)

    for code, team_dir, config, manager_bot, routine_name in TEAMS:
        print(f"\n===== 团队 {code.upper()} ({team_dir.name}) =====")
        texts = {}
        if do_all or args.inject:
            print("-- 注入本地人设 --")
            texts = inject_local(team_dir, config, dry=args.dry_run)
        if do_all or args.apply:
            print("-- 更新线上 Bot --")
            if not texts:
                # 确保线上拿到的是「注入后」的最终全文；inject 幂等，安全可重复
                texts = inject_local(team_dir, config, dry=args.dry_run)
            apply_online(config, texts, dry=args.dry_run)
        if do_all or args.routine:
            print("-- 定时同步 routine --")
            sync_routine(manager_bot, routine_name, dry=args.dry_run)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)
