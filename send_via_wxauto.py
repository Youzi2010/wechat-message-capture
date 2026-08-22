# -*- coding: utf-8 -*-
"""
send_via_wxauto.py - wxauto 直发微信消息（通用版）
====================================================
用法:
  python send_via_wxauto.py --who 文件传输助手 --msg "你好"
  python send_via_wxauto.py --msg "测试"            # 默认发给 config.summary.send_to

依赖: 微信 4.1.7.30 电脑版已登录 + wxauto4（hermes venv）
"""
import os
import sys
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding='utf-8')

from wechat_client import WeChatClient

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def default_who():
    """默认接收人：config.summary.send_to，找不到则文件传输助手"""
    try:
        with open(os.path.join(BASE_DIR, 'config.json'), encoding='utf-8') as f:
            cfg = json.load(f)
        who = (cfg.get('summary', {}) or {}).get('send_to', '')
        return who or '文件传输助手'
    except Exception:
        return '文件传输助手'


def main():
    parser = argparse.ArgumentParser(description='wxauto 直发微信消息')
    parser.add_argument('--who', default=None, help='接收人（通讯录名称），默认取 config.summary.send_to')
    parser.add_argument('--msg', help='消息内容（与 --file 二选一）')
    parser.add_argument('--file', help='从文件读取消息内容（UTF-8）')
    args = parser.parse_args()

    who = args.who or default_who()
    msg = args.msg
    if args.file:
        with open(args.file, encoding='utf-8') as f:
            msg = f.read().strip()
    if not msg:
        print('错误：--msg 与 --file 至少提供一个', flush=True)
        sys.exit(2)

    c = WeChatClient(ads=True)
    print(f'登录账号: {c.nickname}', flush=True)
    print(f'发送给: {who}（内容 {len(msg)} 字）', flush=True)
    r = c.send(who, msg)
    print(f'发送结果: {r}', flush=True)
    ok = isinstance(r, dict) and str(r.get('status', '')).find('成功') >= 0
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
