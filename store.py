# -*- coding: utf-8 -*-
"""
store.py - SQLite 消息落库 + 去重
"""
import os
import sys
import sqlite3
import hashlib
import datetime

sys.stdout.reconfigure(encoding='utf-8')


def _now():
    return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')


class MessageStore:
    def __init__(self, db_path):
        self.db_path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_name TEXT NOT NULL,
                content TEXT NOT NULL,
                msg_hash TEXT NOT NULL UNIQUE,
                hit_keywords TEXT DEFAULT '',
                is_hit INTEGER DEFAULT 1,
                sender_nick TEXT DEFAULT '',
                sender_wxid TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now','localtime'))
            )
        """)
        # 兼容旧表：补列
        try:
            self.conn.execute("ALTER TABLE messages ADD COLUMN sender_nick TEXT DEFAULT ''")
            self.conn.commit()
        except Exception:
            pass
        try:
            self.conn.execute("ALTER TABLE messages ADD COLUMN sender_wxid TEXT DEFAULT ''")
            self.conn.commit()
        except Exception:
            pass
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_group_time
            ON messages(group_name, created_at)
        """)
        self.conn.commit()

    @staticmethod
    def _hash(content, group_name):
        return hashlib.sha1(f"{group_name}|{content}".encode('utf-8')).hexdigest()

    def save(self, group_name, content, hit_keywords, sender=''):
        """保存消息，返回 True=新入库 / False=重复；sender 为发送者昵称（群内昵称或 self）"""
        h = self._hash(content, group_name)
        try:
            self.conn.execute(
                "INSERT INTO messages (group_name, content, msg_hash, hit_keywords, sender_nick) VALUES (?,?,?,?,?)",
                (group_name, content, h, ','.join(hit_keywords), sender or ''),
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def exists(self, content, group_name):
        """是否已入库（内容+群去重）"""
        h = self._hash(content, group_name)
        cur = self.conn.execute("SELECT 1 FROM messages WHERE msg_hash=?", (h,))
        return cur.fetchone() is not None

    def get_today_hits(self, date=None):
        """获取指定日期（默认今天）命中的消息，按群+时间排序"""
        date = date or datetime.date.today().strftime('%Y-%m-%d')
        cur = self.conn.execute(
            """SELECT group_name, content, hit_keywords, created_at, sender_nick, sender_wxid
               FROM messages WHERE is_hit=1 AND created_at LIKE ?
               ORDER BY group_name, created_at""",
            (date + '%',),
        )
        rows = cur.fetchall()
        return [
            {'group': r[0], 'content': r[1], 'keywords': r[2], 'time': r[3], 'nick': r[4] or '', 'wxid': r[5] or ''}
            for r in rows
        ]

    def get_recent_hits(self, days=3, end_date=None):
        """获取最近 N 天（含当天）入库的命中消息（2026-08-17 用户规则：3 天内）
        end_date 默认今天，窗口 = [end_date - days + 1, end_date]
        """
        end_date = end_date or datetime.date.today().strftime('%Y-%m-%d')
        start = (datetime.datetime.strptime(end_date, '%Y-%m-%d').date()
                 - datetime.timedelta(days=days - 1)).strftime('%Y-%m-%d')
        cur = self.conn.execute(
            """SELECT group_name, content, hit_keywords, created_at, sender_nick, sender_wxid
               FROM messages WHERE is_hit=1 AND date(created_at) >= ? AND date(created_at) <= ?
               ORDER BY group_name, created_at""",
            (start, end_date),
        )
        rows = cur.fetchall()
        return [
            {'group': r[0], 'content': r[1], 'keywords': r[2], 'time': r[3], 'nick': r[4] or '', 'wxid': r[5] or ''}
            for r in rows
        ]

    def stats(self):
        cur = self.conn.execute("SELECT COUNT(*), SUM(is_hit) FROM messages")
        total, hits = cur.fetchone()
        return {'total': total or 0, 'hits': hits or 0}

    def close(self):
        self.conn.close()


if __name__ == '__main__':
    s = MessageStore('db/test.db')
    print("新入库:", s.save('测试群', '招铝模工人日结300', ['铝模', '日结']))
    print("重复:", s.save('测试群', '招铝模工人日结300', ['铝模', '日结']))
    print("统计:", s.stats())
    print("今日命中:", len(s.get_today_hits()))
    s.close()
    os.remove('db/test.db')
