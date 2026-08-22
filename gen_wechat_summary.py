# -*- coding: utf-8 -*-
"""
gen_wechat_summary.py - 生成微信直发版汇总（通用版）
======================================================
规则（通用，全部来自 config.json）：
1. 内容按原文完整输出，不简化
2. 命中排除词的消息剔除
3. require_phone=true 时：剔除无电话号码的消息（宽松匹配支持空格：199 2491 9708）
4. 跨群归一化去重（忽略【前缀】/标点/空白差异）
输出：db/wechat_summary_YYYY-MM-DD.txt
"""
import os
import sys
import re
import datetime
import argparse

sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
from store import MessageStore
from filter import build_rules, is_excluded, has_phone
import json


def norm_key(text):
    """归一化去重 key：删【】包裹段（如【包吃包住】）+ 删标点/空白"""
    t = re.sub(r'【[^】]*】', '', text)
    t = re.sub(r'[\s，。,.、！!？?：:；;\"\'（）()\[\]]', '', t)
    return t.strip()


def load_config():
    with open(os.path.join(BASE_DIR, 'config.json'), encoding='utf-8') as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--date', default=None, help='截止日期 yyyy-MM-dd，默认今天')
    parser.add_argument('--days', type=int, default=None, help='时间窗口天数（默认取 config.time_range_days，即 3）')
    args = parser.parse_args()

    cfg = load_config()
    rules = build_rules(cfg)
    date = args.date or datetime.date.today().strftime('%Y-%m-%d')
    days = args.days or cfg.get('time_range_days', 3)
    store = MessageStore(os.path.join(BASE_DIR, cfg.get('db_path', 'db/messages.db')))
    rows = store.get_recent_hits(days=days, end_date=date)
    store.close()

    # 跨群归一化去重
    seen = {}
    for r in rows:
        key = norm_key(r['content'])
        if not key:
            continue
        if key not in seen:
            seen[key] = {'content': r['content'], 'time': r['time'], 'groups': [r['group']]}
        else:
            if r['group'] not in seen[key]['groups']:
                seen[key]['groups'].append(r['group'])

    # 过滤：排除词 → 无电话（如开启）
    kept = []
    dropped_excluded = 0
    dropped_no_phone = 0
    for it in seen.values():
        if is_excluded(it['content'], rules['exclude_keywords']):
            dropped_excluded += 1
            continue
        if rules.get('require_phone') and not has_phone(it['content']):
            dropped_no_phone += 1
            continue
        kept.append(it)

    # 按时间排序
    kept.sort(key=lambda x: x['time'])

    lines = []
    tag = "（排除词已过滤" + ("，需带电话" if rules.get('require_phone') else "") + "）"
    lines.append(f"【消息汇总 {date}（近{days}天）】共 {len(kept)} 条{tag}")
    lines.append("")
    for i, it in enumerate(kept, 1):
        lines.append(f"{i}. {it['content'].strip()}")
        lines.append("")

    text = '\n'.join(lines)
    out = os.path.join(BASE_DIR, 'db', f'wechat_summary_{date}.txt')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, 'w', encoding='utf-8') as f:
        f.write(text)

    print(f'窗口内入库: {len(rows)}')
    print(f'去重后: {len(seen)}')
    print(f'剔除排除词: {dropped_excluded}')
    print(f'剔除无电话: {dropped_no_phone}')
    print(f'有效保留: {len(kept)}')
    print(f'总字数: {len(text)}')
    print(f'已保存: {out}')


if __name__ == '__main__':
    main()
