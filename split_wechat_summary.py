# -*- coding: utf-8 -*-
"""
把 wechat_summary_YYYY-MM-DD.txt 按字数分块，生成 msg_part_N.txt
（微信单条消息建议 ≤1800 字）
"""
import os
import sys
import datetime

sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.join(BASE_DIR, 'db')

MAX_CHARS = 1800

def main():
    date = sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().strftime('%Y-%m-%d')
    src = os.path.join(DB_DIR, f'wechat_summary_{date}.txt')
    with open(src, encoding='utf-8') as f:
        text = f.read()

    # 按行切块（保留完整条目），每块不超过 MAX_CHARS
    blocks = []
    cur = []
    cur_len = 0
    for line in text.splitlines(keepends=True):
        if cur_len + len(line) > MAX_CHARS and cur:
            blocks.append(''.join(cur))
            cur = []
            cur_len = 0
        cur.append(line)
        cur_len += len(line)
    if cur:
        blocks.append(''.join(cur))

    paths = []
    for i, b in enumerate(blocks, 1):
        p = os.path.join(DB_DIR, f'msg_part_{i}.txt')
        with open(p, 'w', encoding='utf-8') as f:
            f.write(b)
        paths.append((p, len(b)))
        print(f'msg_part_{i}.txt: {len(b)} 字')

    print(f'共 {len(blocks)} 段')
    return paths

if __name__ == '__main__':
    main()
