# -*- coding: utf-8 -*-
"""
check_db.py - 查库调试（通用版：路径从 config.json 读取）
用法: python check_db.py [--days N]
"""
import os
import sys
import json
import argparse

sys.stdout.reconfigure(encoding='utf-8')
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
from store import MessageStore


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--days', type=int, default=None, help='最近 N 天（默认 config.time_range_days）')
    args = ap.parse_args()
    with open(os.path.join(BASE_DIR, 'config.json'), encoding='utf-8') as f:
        cfg = json.load(f)
    days = args.days or cfg.get('time_range_days', 3)
    s = MessageStore(os.path.join(BASE_DIR, cfg.get('db_path', 'db/messages.db')))
    rows = s.get_recent_hits(days=days)
    stats = s.stats()
    print(f"库内总计 {stats['total']} 条（命中 {stats['hits']}）| 最近 {days} 天命中 {len(rows)} 条:")
    for r in rows:
        print(f"  [{r['time']}] {r['group']} | 关键词: {r['keywords']}")
        print(f"      {r['content'][:120]}")
    s.close()


if __name__ == '__main__':
    main()
