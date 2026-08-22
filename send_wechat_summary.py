# -*- coding: utf-8 -*-
"""
send_wechat_summary.py - 汇总一键「生成 + 分段 + wxauto 直发」确定性流程（通用版）
===================================================================================
用法:
  python send_wechat_summary.py [--date YYYY-MM-DD] [--who 文件传输助手]

流程:
  1. gen_wechat_summary.py --date <date>   （生成原文版汇总，规则从 config 读取）
  2. split_wechat_summary.py <date>        （按 ≤1800 字分段 → db/msg_part_N.txt）
  3. send_via_wxauto.py --file ... 逐段直发（段间间隔 4 秒）

退出码:
  0 = 全部成功（或「窗口内无消息」已通知）
  1 = 生成/分段失败
  2 = 部分/全部发送失败
"""
import os
import sys
import time
import glob
import argparse
import datetime
import subprocess

sys.stdout.reconfigure(encoding='utf-8')
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.join(BASE_DIR, 'db')
DEFAULT_WHO = '文件传输助手'
SEND_GAP_SECONDS = 4


def run(cmd):
    """运行子命令并透传输出；返回退出码"""
    print('>', ' '.join(cmd), flush=True)
    try:
        r = subprocess.run(cmd, cwd=BASE_DIR, capture_output=True, text=True,
                           encoding='utf-8', errors='replace', timeout=900)
    except subprocess.TimeoutExpired:
        print('!! 命令超时', flush=True)
        return 1
    if r.stdout and r.stdout.strip():
        print(r.stdout.strip(), flush=True)
    if r.stderr and r.stderr.strip():
        print(r.stderr.strip(), flush=True)
    return r.returncode


def clean_parts():
    for p in glob.glob(os.path.join(DB_DIR, 'msg_part_*.txt')):
        try:
            os.remove(p)
        except OSError:
            pass


def main():
    ap = argparse.ArgumentParser(description='汇总一键生成+分段+wxauto直发')
    ap.add_argument('--date', default=None, help='截止日期 yyyy-MM-dd，默认今天')
    ap.add_argument('--who', default=None, help='接收人（微信昵称），默认取 config.summary.send_to')
    args = ap.parse_args()

    date = args.date or datetime.date.today().strftime('%Y-%m-%d')
    who = args.who
    if not who:
        try:
            import json
            with open(os.path.join(BASE_DIR, 'config.json'), encoding='utf-8') as f:
                who = ((json.load(f).get('summary', {}) or {}).get('send_to', '') or DEFAULT_WHO)
        except Exception:
            who = DEFAULT_WHO
    py = sys.executable

    # ---- 1. 生成汇总 ----
    rc = run([py, os.path.join(BASE_DIR, 'gen_wechat_summary.py'), '--date', date])
    if rc != 0:
        print('FAIL: 生成汇总失败', flush=True)
        sys.exit(1)

    summary_path = os.path.join(DB_DIR, f'wechat_summary_{date}.txt')
    if not os.path.exists(summary_path) or not open(summary_path, encoding='utf-8').read().strip():
        print('窗口内无消息', flush=True)
        rc = run([py, os.path.join(BASE_DIR, 'send_via_wxauto.py'),
                  '--who', who, '--msg', f'{date} 窗口内无抓取到消息'])
        sys.exit(0 if rc == 0 else 2)

    # ---- 2. 分段 ----
    clean_parts()
    rc = run([py, os.path.join(BASE_DIR, 'split_wechat_summary.py'), date])
    if rc != 0:
        print('FAIL: 分段失败', flush=True)
        sys.exit(1)

    parts = sorted(
        glob.glob(os.path.join(DB_DIR, 'msg_part_*.txt')),
        key=lambda p: int(os.path.basename(p).split('_')[-1].split('.')[0]),
    )
    if not parts:
        print('FAIL: 未生成任何分段', flush=True)
        sys.exit(1)

    # ---- 3. 逐段直发 ----
    ok = 0
    total = len(parts)
    for i, part in enumerate(parts, 1):
        print(f'--- 发送第 {i}/{total} 段: {os.path.basename(part)} ---', flush=True)
        rc = run([py, os.path.join(BASE_DIR, 'send_via_wxauto.py'),
                  '--who', who, '--file', part])
        if rc == 0:
            ok += 1
        else:
            print(f'FAIL: 第 {i} 段发送失败', flush=True)
        if i < total:
            time.sleep(SEND_GAP_SECONDS)

    print(f'发送结果: {ok}/{total} 段成功', flush=True)
    sys.exit(0 if ok == total else 2)


if __name__ == '__main__':
    main()
