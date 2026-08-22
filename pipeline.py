# -*- coding: utf-8 -*-
"""
pipeline.py - 微信消息抓取 · 通用版轮询流水线
==============================================
用法: python pipeline.py [--once] [--loop] [--verbose]

流程: 连接微信 → 目标列表（群+联系人）随机采样 → 逐个读消息
      → 关键词过滤（可空=全抓）→ 排除词过滤（可空=不排）→ SQLite 落库（去重）

配置: config.json（targets/rules/poll/time_range_days，详见说明书）
"""
import os
import sys
import json
import time
import argparse
import datetime
import random

sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from wechat_client import WeChatClient
from filter import build_rules, match_keywords, is_excluded, is_sender_match
from store import MessageStore

LOG_DIR = os.path.join(BASE_DIR, 'logs')


def log(msg):
    """控制台输出 + 写文件日志"""
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(os.path.join(LOG_DIR, f"pipeline_{datetime.date.today().strftime('%Y%m%d')}.log"), 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except Exception:
        pass


def load_config():
    with open(os.path.join(BASE_DIR, 'config.json'), encoding='utf-8') as f:
        return json.load(f)


def get_targets(cfg):
    """合并群+联系人目标列表（去重保序）"""
    tg = cfg.get('targets', {}) or {}
    groups = tg.get('groups', []) or []
    contacts = tg.get('contacts', []) or []
    seen, out = set(), []
    for name in list(groups) + list(contacts):
        if name and name not in seen:
            seen.add(name)
            out.append(name)
    return out


def poll_once(cfg, verbose=False):
    client = WeChatClient(ads=True, load_wait=cfg.get('chat_load_wait_seconds', 2))
    store = MessageStore(os.path.join(BASE_DIR, cfg.get('db_path', 'db/messages.db')))

    print(f"[{time.strftime('%H:%M:%S')}] 连接成功，账号: {client.nickname}", flush=True)
    log(f"连接成功，账号: {client.nickname}")

    poll = cfg.get('poll', {}) or {}

    # ---- 夜间停轮（防封号）----
    ns = poll.get('night_stop', {}) or {}
    night_start = ns.get('start', 23)
    night_end = ns.get('end', 6)
    now_h = datetime.datetime.now().hour
    if now_h >= night_start or now_h < night_end:
        print(f"  [skip] 夜间停轮时段 ({night_start}:00-{night_end}:00)，本轮跳过", flush=True)
        log(f"夜间停轮时段 ({night_start}:00-{night_end}:00)，本轮跳过")
        store.close()
        return 0

    # ---- 目标列表 + 随机采样（防封号）----
    targets_all = get_targets(cfg)
    if not targets_all:
        print("  [error] targets 为空：请先在 config.json 配置要抓的群/联系人", flush=True)
        log("targets 为空：请先在 config.json 配置要抓的群/联系人")
        store.close()
        return 0
    ratio = poll.get('sample_ratio', 0.7)
    k = max(1, int(len(targets_all) * ratio))
    targets = random.sample(targets_all, k)
    print(f"  目标: 共 {len(targets_all)} 个，本轮随机采样 {len(targets)} 个（{ratio:.0%}）", flush=True)
    log(f"目标: 共 {len(targets_all)} 个，本轮随机采样 {len(targets)} 个（{ratio:.0%}）")

    # ---- 规则编译（通用：全部来自 config）----
    rules = build_rules(cfg)
    keywords = rules['keywords']
    excludes = rules['exclude_keywords']
    senders = rules['senders']
    has_kw_filter = bool(keywords)
    has_ex_filter = bool(excludes)
    has_sender_filter = bool(senders)
    if has_sender_filter:
        print(f"  发送者过滤: 仅保留 {'、'.join(senders)} 的发言", flush=True)
        log(f"发送者过滤: 仅保留 {'、'.join(senders)} 的发言")

    # 模拟人类节奏（防封号）
    delay_min = poll.get('chat_switch_delay_min', 2)
    delay_max = poll.get('chat_switch_delay_max', 6)
    max_days = cfg.get('time_range_days', 3)

    total_new = 0
    for idx, g in enumerate(targets):
        if idx > 0:
            delay = random.uniform(delay_min, delay_max)
            print(f"  ...休息 {delay:.1f}s（模拟人类节奏）", flush=True)
            time.sleep(delay)
        msgs = client.read_messages(g, max_days=max_days)
        if not msgs:
            print(f"  {g}: 0 条（未读到）", flush=True)
            log(f"{g}: 0 条（未读到）")
            continue
        new_count = 0
        reached_boundary = False
        # 增量边界：从最新（末尾）往旧遍历，遇到已入库消息即停
        for m in reversed(msgs):
            content = m['content']
            if store.exists(content, g):
                reached_boundary = True
                if verbose:
                    print(f"    [boundary] {g}: 遇到已入库消息，停止本轮（增量边界）", flush=True)
                    log(f"[boundary] {g}: 遇到已入库消息，停止本轮（增量边界）")
                break
            # 过滤：发送者（如配置）→ 关键词（如配置）→ 排除词（如配置）
            sender = m.get('sender')
            if has_sender_filter and not is_sender_match(sender, senders):
                if verbose:
                    print(f"    [skip] 非目标发送者({sender}): {content[:30]}", flush=True)
                    log(f"[skip] 非目标发送者({sender}): {content[:30]}")
                continue
            hits = match_keywords(content, keywords)
            if has_kw_filter and not hits:
                continue
            if has_ex_filter and is_excluded(content, excludes):
                if verbose:
                    print(f"    [skip] 命中排除词: {content[:40]}", flush=True)
                    log(f"[skip] 命中排除词: {content[:40]}")
                continue
            if store.save(g, content, hits, sender or ''):
                new_count += 1
                if verbose:
                    print(f"    [new] {g} | 发送者={sender or '-'} | 命中={hits} | {content[:40]}", flush=True)
        total_new += new_count
        if verbose:
            bd = '已到' if reached_boundary else '未到'
            print(f"  {g}: 读到 {len(msgs)} 条，命中入库 {new_count} 条（边界={bd}）", flush=True)
            log(f"{g}: 读到 {len(msgs)} 条，命中入库 {new_count} 条（边界={bd}）")
        else:
            print(f"  {g}: 命中入库 {new_count} 条", flush=True)
            log(f"{g}: 命中入库 {new_count} 条")

    stats = store.stats()
    print(f"[{time.strftime('%H:%M:%S')}] 本轮完成：新增 {total_new} 条，库内总计 {stats['total']} 条（命中 {stats['hits']}）", flush=True)
    log(f"本轮完成：新增 {total_new} 条，库内总计 {stats['total']} 条（命中 {stats['hits']}）")
    store.close()
    return total_new


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--once', action='store_true', help='只跑一轮（默认）')
    parser.add_argument('--loop', action='store_true', help='持续轮询模式')
    parser.add_argument('--verbose', action='store_true', help='详细输出')
    args = parser.parse_args()

    cfg = load_config()
    if not args.loop:
        poll_once(cfg, verbose=args.verbose)
        return

    poll = cfg.get('poll', {}) or {}
    interval = poll.get('interval_seconds', 180)
    jitter = poll.get('jitter_seconds', 0)
    print(f"持续轮询模式，基础间隔 {interval}s（抖动 +{jitter}s），Ctrl+C 退出", flush=True)
    while True:
        try:
            poll_once(cfg, verbose=args.verbose)
        except Exception as e:
            print(f"[{time.strftime('%H:%M:%S')}] 轮询异常: {e}", flush=True)
            import traceback
            traceback.print_exc()
        wait = interval + (random.uniform(0, jitter) if jitter else 0)
        print(f"  下次轮询约 {wait/60:.1f} 分钟后", flush=True)
        time.sleep(wait)


if __name__ == '__main__':
    main()
