# -*- coding: utf-8 -*-
"""
wechat_client.py - wxauto4 封装 + 自定义 UIA 消息读取
=========================================================
背景：wxauto4 41.1.2 在微信 4.1.7.30 上，GetAllMessage() 有兼容 bug
（返回 0 条）。解决方案：直接用 UIA 控件树读取消息列表
（AutomationId=chat_message_list 的 RecyclerListView，ChatItemView.Name 即消息内容）。

依赖：wxauto4（hermes venv 已装）、微信 4.1.7.30 已登录
"""
import sys
import time
import re
import datetime

sys.stdout.reconfigure(encoding='utf-8')

# 纯时间标签，如 "20:52"、"08:49"（微信消息列表里的时间分隔行）
_TIME_LABEL_RE = re.compile(r'^\d{1,2}:\d{2}$')


def find_autoid(ctrl, autoid, depth=0, max_depth=15):
    """递归查找指定 AutomationId 的控件"""
    try:
        if ctrl.AutomationId == autoid:
            return ctrl
        if depth >= max_depth:
            return None
        for c in ctrl.GetChildren():
            r = find_autoid(c, autoid, depth + 1, max_depth)
            if r:
                return r
    except Exception:
        pass
    return None


class WeChatClient:
    def __init__(self, ads=False, load_wait=2.0):
        from wxauto4 import WeChat
        self.wx = WeChat(ads=ads)
        self.load_wait = load_wait

    @property
    def nickname(self):
        return getattr(self.wx, 'nickname', '?')

    def get_sessions(self):
        """返回 [{name, preview, time}] 会话列表

        优先 wx.GetSession()；大号场景群全在『折叠的聊天』里，
        GetSession 返回 0 → 回退 UIA 枚举 session_list（含滚轮滚动收集）
        """
        out = []
        try:
            sessions = self.wx.GetSession()
            for s in sessions:
                out.append({
                    'name': getattr(s, 'name', ''),
                    'preview': str(s) if s else '',
                    'time': getattr(s, 'time', None),
                })
            if out:
                return out
            print("  [info] GetSession 返回空，改用 UIA 枚举折叠聊天列表", flush=True)
        except Exception as e:
            print(f"  [warn] GetSession 失败: {e}，改用 UIA 枚举", flush=True)
        try:
            names = self._enum_session_list_uia()
            for n in names:
                out.append({'name': n, 'preview': '', 'time': None})
        except Exception as e:
            print(f"  [warn] UIA 枚举会话列表失败: {e}", flush=True)
        return out

    def _enum_session_list_uia(self, max_scroll=60):
        """UIA 枚举『折叠的聊天』session_list：回顶 → 滚动到底 → 收集全部群名"""
        from wxauto4 import uia

        def find_autoid(ctrl, autoid, depth=0, max_depth=15):
            try:
                if ctrl.AutomationId == autoid:
                    return ctrl
                if depth >= max_depth:
                    return None
                for c in ctrl.GetChildren():
                    r = find_autoid(c, autoid, depth + 1, max_depth)
                    if r:
                        return r
            except Exception:
                pass
            return None

        def find_class(ctrl, cls, results, depth=0, max_depth=20):
            try:
                if ctrl.ClassName == cls:
                    results.append(ctrl)
                if depth >= max_depth:
                    return
                for c in ctrl.GetChildren():
                    find_class(c, cls, results, depth + 1, max_depth)
            except Exception:
                pass

        root = uia.GetRootControl()
        main_win = None
        for w in root.GetChildren():
            if "微信" in (w.Name or ""):
                main_win = w
                break
        if main_win is None:
            return []
        table = find_autoid(main_win, 'session_list')
        if table is None:
            lists = []
            find_class(main_win, 'mmui::ChatSessionList', lists)
            table = lists[0] if lists else None
        if table is None:
            return []

        try:
            rect = table.BoundingRectangle
            cx = (rect.left + rect.right) // 2
            cy = (rect.top + rect.bottom) // 2
            uia.SetCursorPos(cx, cy)
            time.sleep(0.3)
        except Exception:
            pass

        # 回顶
        for i in range(60):
            uia.WheelUp(3, 0.05, 0.25)
            time.sleep(0.3)

        seen = set()
        order = []

        def add():
            cells = []
            find_class(table, 'mmui::ChatSessionCell', cells)
            for c in cells:
                try:
                    aid = c.AutomationId or ""
                    name = c.Name or ""
                except Exception:
                    continue
                if aid and aid not in seen:
                    seen.add(aid)
                    order.append(name.split('\n')[0])

        add()
        no_new = 0
        for _ in range(max_scroll):
            before = len(seen)
            uia.WheelDown(2, 0.05, 0.4)
            time.sleep(0.5)
            add()
            if len(seen) == before:
                no_new += 1
                if no_new >= 3:
                    break
            else:
                no_new = 0
        return order

    def open_chat(self, name, retries=2):
        """打开会话，返回是否成功"""
        for i in range(retries + 1):
            try:
                self.wx.ChatWith(name)
                time.sleep(self.load_wait)
                return True
            except Exception as e:
                print(f"  [warn] ChatWith({name}) 第{i+1}次失败: {e}", flush=True)
                time.sleep(1)
        return False

    def read_messages(self, group_name, retries=3, max_days=3):
        """
        读取群最新可见消息
        优先 GetAllMessage（能拿到消息对象，含 sender 发送者）；失败时回退 UIA 纯文本（sender=None）
        返回: [{"content": str, "obj": Message|None, "sender": str|None}, ...]

        max_days: 只返回最近 N 天内的消息（默认 3）
        时间判定：靠 system 时间标签行（time='YYYY-MM-DD HH:MM:SS'）分段，
        标签后的消息归入该日期；无标签可参考的消息保守保留（新消息）。
        """
        if not self.open_chat(group_name):
            return []
        # 验证当前会话确实是目标群（防切换缓存读到上一个会话的消息）
        for attempt in range(3):
            try:
                info = self.wx.ChatInfo()
                cur_name = (info or {}).get('chat_name', '') if isinstance(info, dict) else ''
                if cur_name and cur_name != group_name:
                    print(f"  [warn] 会话切换异常: 期望[{group_name}] 当前[{cur_name}]，重新切换", flush=True)
                    self.open_chat(group_name)
                    continue
                break
            except Exception:
                break
        # 方式一：GetAllMessage（带对象，含发送者）
        try:
            objs = self.wx.GetAllMessage()
            if objs:
                items = []
                # 当前消息所属日期（由最近的时间标签决定），None=未知（视为新消息保留）
                cur_date = None
                for o in objs:
                    try:
                        content = (o.content or '').strip()
                    except Exception:
                        content = ''
                    if not content:
                        continue
                    ts = getattr(o, 'time', None)
                    # system 时间标签（time='YYYY-MM-DD HH:MM:SS'）→ 更新 cur_date，不输出
                    if ts and re.match(r'^\d{4}-\d{2}-\d{2}', str(ts)):
                        cur_date = str(ts)[:10]
                        continue
                    # 纯时间标签行（如 "20:52"）：跳过
                    if _TIME_LABEL_RE.match(content):
                        continue
                    # 普通消息：若 cur_date 已知且超期 → 跳过
                    if cur_date and self._is_expired(cur_date, max_days):
                        continue
                    # 发送者：GetAllMessage 对象带 sender 字段（群内昵称，自己发的为 'self'）
                    sender = getattr(o, 'sender', None)
                    if sender is None:
                        sender = getattr(o, 'nickname', None)
                    items.append({'content': content, 'obj': o, 'sender': sender})
                if items:
                    return items
        except Exception as e:
            print(f"  [warn] {group_name} GetAllMessage 失败: {e}", flush=True)
        # 方式二：UIA 纯文本（无对象，无法获取发送者，sender=None）
        for attempt in range(retries):
            try:
                cb = self.wx.ChatBox.control
                mlist = find_autoid(cb, 'chat_message_list')
                if mlist is None:
                    print(f"  [warn] {group_name} 未找到 chat_message_list (第{attempt+1}次)", flush=True)
                    time.sleep(2)
                    continue
                kids = mlist.GetChildren()
                texts = []
                for k in kids:
                    name = (k.Name or '').strip()
                    if not name:
                        continue
                    if _TIME_LABEL_RE.match(name):
                        continue  # 跳过时间标签行
                    texts.append({'content': name, 'obj': None, 'sender': None})
                return texts
            except Exception as e:
                print(f"  [warn] {group_name} 读消息失败: {e}", flush=True)
                time.sleep(2)
        return []

    @staticmethod
    def _is_expired(date_str, max_days=3):
        """date_str(YYYY-MM-DD) 是否已超过 max_days 天前（True=太旧，跳过）"""
        try:
            d = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
            return (datetime.date.today() - d).days > max_days
        except Exception:
            return False

    def get_sender_wxid(self, msg, wait=2.5):
        """
        点击消息头像弹资料卡，读取发送者微信号
        返回 wxid 或 None；仅对方是小号好友时微信才显示微信号，非好友返回 None
        """
        from wxauto4 import uia
        try:
            msg.click_head()
        except Exception as e:
            print(f"  [warn] click_head 失败: {e}", flush=True)
            return None
        time.sleep(wait)
        wxid = None
        try:
            root = uia.GetRootControl()
            profile = None
            for w in root.GetChildren():
                try:
                    if 'Profile' in (w.ClassName or ''):
                        profile = w
                        break
                except Exception:
                    pass
            if profile is None:
                return None
            # 微信号：找 Name=='微信号：' 的标签，取同组兄弟节点（ContactProfileTextView）
            stack = [profile]
            while stack:
                node = stack.pop()
                try:
                    if node.Name == '微信号：':
                        try:
                            for sib in node.GetParent().GetChildren():
                                if sib.AutomationId and sib.AutomationId.endswith('ContactProfileTextView'):
                                    wxid = sib.Name
                                    break
                        except Exception:
                            pass
                        break
                    stack.extend(node.GetChildren())
                except Exception:
                    pass
            return wxid
        except Exception as e:
            print(f"  [warn] 读资料卡失败: {e}", flush=True)
            return None
        finally:
            # 关闭资料卡（防残留影响下一轮）
            try:
                uia.SendKeys('{Esc}')
                time.sleep(1)
            except Exception:
                pass

    def send(self, who, msg):
        """发送消息，返回响应 dict"""
        return self.wx.SendMsg(msg, who=who)

    def chat_info(self, name):
        """获取会话信息（群名/成员数等）"""
        try:
            self.wx.ChatWith(name)
            time.sleep(1)
            return self.wx.ChatInfo()
        except Exception as e:
            print(f"  [warn] ChatInfo({name}) 失败: {e}", flush=True)
            return None


if __name__ == '__main__':
    print("=== WeChatClient 自测 ===")
    c = WeChatClient()
    print("登录账号:", c.nickname)
    sessions = c.get_sessions()
    print(f"会话数: {len(sessions)}")
    for s in sessions[:5]:
        print(f"  {s['name']}")
    for g in ['铝模（粟）交流班组', '木&铝模交流群']:
        msgs = c.read_messages(g)
        print(f"\n{g}: {len(msgs)} 条消息")
        for m in msgs[:5]:
            print(f"  - {m[:80]}")
