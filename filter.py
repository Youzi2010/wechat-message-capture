# -*- coding: utf-8 -*-
"""
filter.py - 通用过滤引擎（微信消息抓取 Skill 通用版）
=======================================================
设计原则：不内置任何业务词。所有规则从 config.json 读取：
- keywords：关键词（命中任一才抓；未配置/空 = 不过滤，全部抓取）
- exclude_keywords：排除词（命中任一即丢弃；未配置/空 = 不排除）
- require_phone：汇总是否必须带手机号（默认 false）

与 wechat-recruiter 招聘版的区别：去掉了建筑白名单/材料厂家/广告类目/找活
等业务规则，改为通用 keywords + exclude_keywords 两级过滤。
"""
import sys

sys.stdout.reconfigure(encoding='utf-8')

# 通用默认：空 = 不过滤（业务词必须由用户配置）
DEFAULT_KEYWORDS = []
DEFAULT_EXCLUDE = []
DEFAULT_REQUIRE_PHONE = False
DEFAULT_SENDERS = []  # 按发送者过滤（群内昵称列表）；空 = 所有人

# 中国大陆手机号（宽松：允许数字间有空格/点，如 199 2491 9708）
PHONE_RE = __import__('re').compile(r'1[3-9]\d{9}')


def build_rules(cfg=None):
    """从 config.json 编译过滤规则（通用版）
    未配置/缺失 → 空规则（不误伤、不过滤）
    """
    r = (cfg or {}).get('rules', {}) or {}
    return {
        'keywords': r.get('keywords') or DEFAULT_KEYWORDS,
        'exclude_keywords': r.get('exclude_keywords') or DEFAULT_EXCLUDE,
        'require_phone': r.get('require_phone', DEFAULT_REQUIRE_PHONE),
        'senders': r.get('senders') or DEFAULT_SENDERS,  # 群内昵称列表，空=所有人
    }


def match_keywords(text, keywords=None):
    """返回命中的关键词列表（空列表 = 未命中；keywords 为空 = 全部命中）"""
    if not text:
        return []
    keywords = keywords or DEFAULT_KEYWORDS
    if not keywords:
        return ['*']  # 未配置关键词 = 全抓
    return [kw for kw in keywords if kw and kw in text]


def is_excluded(text, excludes=None):
    """是否命中排除词（True = 丢弃）"""
    if not text:
        return False
    excludes = excludes or DEFAULT_EXCLUDE
    if not excludes:
        return False
    return any(kw and kw in text for kw in excludes)


def is_sender_match(sender, senders=None):
    """发送者是否匹配（senders 为空 = 不限制，全部通过）
    sender=None（UIA 回退读不到发送者）时：配置了 senders 则拒绝（保守），未配置则通过
    """
    senders = senders or DEFAULT_SENDERS
    if not senders:
        return True
    if not sender:
        return False
    return any(s and s == sender for s in senders)


def has_phone(text):
    """是否包含 11 位手机号（宽松匹配：去非数字后查 1[3-9] 开头）"""
    if not text:
        return False
    digits = __import__('re').sub(r'\D', '', text)
    return PHONE_RE.search(digits) is not None


def is_recruitment(text, rules=None):
    """通用判定：命中关键词 且 未命中排除词（rules 缺失 → 全放行）"""
    if not text:
        return False
    if rules is None:
        rules = build_rules(None)
    if not match_keywords(text, rules['keywords']):
        return False
    if is_excluded(text, rules['exclude_keywords']):
        return False
    return True


if __name__ == '__main__':
    print("=== filter.py 通用版自测 ===")
    tests = [
        # (文本, 配置, 期望是否保留)
        ("招铝模工人日结300 电话13800138000", {'keywords': ['铝模'], 'exclude_keywords': []}, True),
        ("出售二手铝模 电话13800138000", {'keywords': ['铝模'], 'exclude_keywords': ['出售', '二手']}, False),
        ("今天天气不错", {'keywords': ['铝模'], 'exclude_keywords': []}, False),
        ("任何消息都抓", {'keywords': [], 'exclude_keywords': []}, True),
        ("广告 加微信xxx", {'keywords': [], 'exclude_keywords': ['广告']}, False),
    ]
    for text, rule_cfg, want in tests:
        rules = build_rules({'rules': rule_cfg})
        got = is_recruitment(text, rules)
        mark = "OK " if got == want else "FAIL"
        print(f"[{mark}] 保留={got}(期望{want}) 命中={match_keywords(text, rules['keywords'])} | {text[:28]}")
