# -*- coding: utf-8 -*-
"""
diag_sender.py - 诊断：wxauto 能否读到消息发送者（昵称）
==========================================================
用途：验证按"发送者过滤"功能的可行性（抓某群里特定人的发言）
用法: python diag_sender.py "群名"
输出：每条消息的 [发送者] 内容（打印前 N 条）
"""
import os
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
from wechat_client import WeChatClient


def main():
    group = sys.argv[1] if len(sys.argv) > 1 else '示例群'
    c = WeChatClient(ads=True)
    print(f"登录账号: {c.nickname}", flush=True)
    print(f"打开群: {group}", flush=True)
    if not c.open_chat(group):
        print(f"[FAIL] 打不开群「{group}」，请确认群名与电脑微信搜索框输入完全一致", flush=True)
        sys.exit(1)
    time.sleep(2)
    # 直接调 GetAllMessage 看消息对象结构
    try:
        objs = c.wx.GetAllMessage()
        print(f"GetAllMessage 返回 {len(objs)} 条", flush=True)
        shown = 0
        for o in objs:
            content = (getattr(o, 'content', '') or '').strip()
            if not content:
                continue
            sender = getattr(o, 'sender', None)
            nickname = getattr(o, 'nickname', None)
            is_self = getattr(o, 'is_self', None)
            print(f"  [sender={sender!r} nickname={nickname!r} is_self={is_self!r}] {content[:50]}", flush=True)
            shown += 1
            if shown >= 10:
                break
        if shown == 0:
            print("  (无消息，或全部为空内容)", flush=True)
    except Exception as e:
        print(f"[FAIL] GetAllMessage 异常: {e}", flush=True)
        # 回退：看看 read_messages 能拿到什么
        msgs = c.read_messages(group, max_days=2)
        print(f"read_messages 回退: {len(msgs)} 条", flush=True)
        for m in msgs[:10]:
            print(f"  {m['content'][:50]}", flush=True)


if __name__ == '__main__':
    main()
