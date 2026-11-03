"""
core/patrol.py — 轮巡模式调度器 v3

翻页策略（PageDown / PageUp，彻底移除滚轮）：

  ┌─ 一次完整轮巡 ────────────────────────────────────────┐
  │  1. 激活微信，获取联系人列表区域坐标                    │
  │  2. 第1个联系人 Y = 列表顶部 + 33px（半行偏移）         │
  │     每行步长固定 66px，每屏处理 15 人                   │
  │  3. 处理完一屏后：                                      │
  │       a. 鼠标点击联系人区以激活焦点                     │
  │       b. 按 PageDown 键翻到下一屏                       │
  │       c. 等待 0.4s 后再从第1行 Y 开始处理下一屏         │
  │  4. 所有预设联系人（patrol_max_contacts）处理完毕后：   │
  │       a. 鼠标点击联系人区激活焦点                       │
  │       b. 连按 pageup_count 次 PageUp 回到顶部           │
  │       c. 重置计数，开始新一轮                           │
  └───────────────────────────────────────────────────────┘

可配置项（wx_ai_config.json）：
  patrol_contact_interval  每个联系人处理后等待秒数（默认 8）
  patrol_max_contacts      每轮最多处理人数（默认 1000）
  patrol_pageup_count      轮末回顶连按 PageUp 次数（默认 20，备用）
  greet_path               问候语 JSON 文件路径（默认 greet.json）

注：回顶优先用 Ctrl+Home（一键到顶），pageup_count 作为兜底保险。
"""

import json
import random
import re
import time

from core.capture import grab
from core.ocr     import OCR
from core.sender  import send_text, random_delay
from core.deps    import HAS_AG, pyautogui


# ── 布局常量（不可在 UI 配置，属于微信布局固定值）──────────
ROW_STEP        = 66   # 联系人行高（像素），微信 PC 版固定
ROWS_PER_SCREEN = 15   # 每屏处理行数（与 PageDown 翻页量对应）


# ── 默认开场问候（greet.json 加载失败时的保底）────────────
_FALLBACK_GREETS = [
    "在吗～好久没聊了，最近怎么样呀 😊",
    "嗨，突然想起你，来打个招呼～",
    "最近忙嘛？好久没动静了",
    "今天怎么样呀，有没有发生什么有趣的事～",
    "突然想起你了，来聊两句嘛～",
]


def _load_greets(path: str = "greet.json") -> list[str]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        result = [item["text"] for item in data
                  if isinstance(item, dict) and item.get("text")]
        return result if result else _FALLBACK_GREETS
    except Exception:
        return list(_FALLBACK_GREETS)


class PatrolBot:
    """
    轮巡调度器：固定坐标步进 + PageDown 翻页 + PageUp 回顶。
    与 Bot 共用相同的路由逻辑（AI / 照片 / 见面 / 开场问候）。
    """

    def __init__(self, bot_instance):
        self._bot   = bot_instance
        self._greets: list[str]       = []
        self._last_greet: dict        = {}   # {contact: last_sent_greeting}
        self._greeted_this_round: set = set()
        self._visited_count: int      = 0
        self._greeted_count:  int     = 0

    # ════════════════════════════════════════════════════════
    # 公共入口
    # ════════════════════════════════════════════════════════
    def patrol_tick(self):
        """
        一次完整的轮巡（会一直运行到 max_contacts 处理完毕，
        然后按 PageUp 回顶，再重新开始——外部 _loop 只需不断调用此方法）。
        """
        bot = self._bot
        bot.wx.refresh()
        if not bot.wx.found:
            if not bot.setup():
                return

        bot.wx.activate()
        time.sleep(0.5)

        # ── 获取列表区域坐标（整个轮巡期间不变）────────────
        lb = bot.wx.list_bbox()
        lx1, ly1, lx2, ly2 = lb
        if lx1 < 0 or ly1 < 0 or (lx2 - lx1) < 30 or (ly2 - ly1) < 80:
            bot.log(f"轮巡：窗口坐标异常 bbox={lb}", "dim")
            return

        # 列表区点击中心 X（整轮固定）
        list_cx = (lx1 + lx2) // 2
        # 列表区激活用 Y（取列表中间位置，避免误触联系人）
        # 第 1 个联系人的 Y 坐标（列表顶部 + 半行偏移）
        first_row_y = ly1 + ROW_STEP // 2
        # 激活焦点用的安全 Y：列表上方标题栏（ly1-10）
        list_focus_y = ly1   # 传给 _press_key_in_list / _return_to_top

        max_contacts  = bot.cfg.get("patrol_max_contacts",  1000)
        pageup_count  = bot.cfg.get("patrol_pageup_count",  20)

        bot.log(
            f"🔄 轮巡启动 | 列表CX={list_cx} 首行Y={first_row_y} "
            f"步长={ROW_STEP}px 每屏{ROWS_PER_SCREEN}人 共{max_contacts}人",
            "green",
        )

        self._greeted_this_round = set()
        self._visited_count = 0
        self._greeted_count = 0

        total_done = 0
        screen_idx = 0

        # ════════════════════════════════════════════════════
        # 主循环：按屏处理
        # ════════════════════════════════════════════════════
        while total_done < max_contacts and bot._app_running():
            remaining         = max_contacts - total_done
            rows_this_screen  = min(ROWS_PER_SCREEN, remaining)

            bot.log(
                f"  📋 第{screen_idx + 1}屏 | 处理 {rows_this_screen} 个联系人"
                f"（已完成 {total_done}/{max_contacts}）",
                "blue",
            )

            # ── 处理本屏每一行 ───────────────────────────────
            for row_idx in range(rows_this_screen):
                click_y    = first_row_y + row_idx * ROW_STEP
                global_idx = total_done + row_idx + 1

                # 超出列表可见区底部 → 本屏提前结束
                if click_y > ly2 - ROW_STEP // 4:
                    bot.log(
                        f"  ⚠ Y={click_y} 超出列表底部边界，本屏提前结束",
                        "dim",
                    )
                    # 把"超出"的行数算入 total_done，避免无限循环
                    total_done = total_done + row_idx
                    rows_this_screen = row_idx   # 修正本屏实际处理数
                    break

                if not bot._app_running():
                    bot.log("  ⏹ 停止信号：轮巡中断", "yellow")
                    return
                self._handle_contact(
                    global_idx, max_contacts,
                    list_cx, click_y,
                )
            else:
                # for 正常结束（未 break）
                total_done += rows_this_screen

            # ── 检查是否已完成全部 ───────────────────────────
            if total_done >= max_contacts:
                break

            # ── 翻页：PageDown ──────────────────────────────
            screen_idx += 1
            # 本屏最后一个联系人的 Y（用于两次点击激活列表焦点）
            last_y_this_screen = first_row_y + (rows_this_screen - 1) * ROW_STEP
            bot.log(
                f"  ⌨ PageDown → 第{screen_idx + 1}屏（激活Y={last_y_this_screen}）",
                "dim",
            )
            if not bot._app_running():
                bot.log("  ⏹ 停止信号：翻页前中断", "yellow")
                return
            self._press_key_in_list(list_cx, last_y_this_screen, "pagedown")
            time.sleep(0.6)   # 等微信列表滚动动画

        # ════════════════════════════════════════════════════
        # 全部处理完毕 → PageUp 回顶
        # ════════════════════════════════════════════════════
        bot.log(
            f"🔄 本轮轮巡完成：访问 {self._visited_count} 人，"
            f"发问候 {self._greeted_count} 人",
            "green",
        )
        bot.q.put(("patrol_stat", self._visited_count, self._greeted_count))

        bot.log(
            f"  ⌨ 按 PageUp × {pageup_count} 回到列表顶部...",
            "dim",
        )
        # 传最后处理的那个联系人 Y，用于激活列表焦点
        last_y_global = first_row_y + ((total_done - 1) % ROWS_PER_SCREEN) * ROW_STEP
        self._return_to_top(list_cx, last_y_global, pageup_count)

    # ════════════════════════════════════════════════════════
    # 键盘操作辅助
    # ════════════════════════════════════════════════════════
    def _press_key_in_list(self, cx: int, last_row_y: int, key: str):
        """
        激活联系人列表焦点，再按 PageDown。
        策略：先点第15个联系人坐标 → 等2s → 再点一次 → 再按键。
        两次点击确保微信列表区获得焦点。
        last_row_y: 本屏最后一个联系人（第15行）的 Y 坐标。
        """
        if not HAS_AG:
            return
        bot = self._bot
        bot.wx.activate()
        time.sleep(0.2)
        # 第1次点击：点第15个联系人
        bot.log(f"     🖱 激活列表焦点：第1次点击 ({cx}, {last_row_y})", "dim")
        pyautogui.moveTo(cx, last_row_y, duration=0.10)
        pyautogui.click()
        # 等待2秒，每0.3s检查停止信号
        for _ in range(7):
            if not self._bot._app_running():
                return
            time.sleep(0.3)
        # 第2次点击：再点一次，确保焦点落在列表区
        bot.log(f"     🖱 激活列表焦点：第2次点击 ({cx}, {last_row_y})", "dim")
        pyautogui.moveTo(cx, last_row_y, duration=0.08)
        pyautogui.click()
        time.sleep(0.3)
        # 按键
        bot.log(f"     ⌨ 按 {key.upper()}", "dim")
        pyautogui.press(key)

    def _return_to_top(self, cx: int, last_row_y: int, pageup_count: int):
        """
        回到联系人列表顶部。
        策略：先点最后一个联系人坐标 → 等2s → 再点一次激活列表焦点
              → 连按 pageup_count 次 PageUp。
        last_row_y: 本轮最后处理的那个联系人 Y 坐标（用于激活列表焦点）。
        """
        if not HAS_AG:
            return
        bot = self._bot
        bot.wx.activate()
        time.sleep(0.2)
        # 第1次点击激活列表
        bot.log(f"  🖱 回顶激活：第1次点击 ({cx}, {last_row_y})", "dim")
        pyautogui.moveTo(cx, last_row_y, duration=0.10)
        pyautogui.click()
        for _ in range(7):
            if not self._bot._app_running():
                return
            time.sleep(0.3)
        # 第2次点击确保焦点
        bot.log(f"  🖱 回顶激活：第2次点击 ({cx}, {last_row_y})", "dim")
        pyautogui.moveTo(cx, last_row_y, duration=0.08)
        pyautogui.click()
        time.sleep(0.3)
        # 连按 PageUp
        bot.log(f"  ⌨ 连按 PageUp × {pageup_count} ...", "dim")
        for _ in range(pageup_count):
            pyautogui.press("pageup")
            time.sleep(0.12)
        bot.log(f"  ✅ 已回到列表顶部（PageUp × {pageup_count}）", "green")
        time.sleep(0.5)

    # ════════════════════════════════════════════════════════
    # 处理单个联系人
    # ════════════════════════════════════════════════════════
    def _handle_contact(
        self,
        global_idx: int,
        total: int,
        click_x: int,
        click_y: int,
    ):
        bot = self._bot

        bot.log(
            f"  轮巡[{global_idx}/{total}] 点击 ({click_x}, {click_y})",
            "yellow",
        )

        if not HAS_AG:
            bot.log("缺少 pyautogui，无法操作", "red")
            return

        # 激活微信并点击联系人行
        bot.wx.activate()
        time.sleep(0.15)
        pyautogui.moveTo(click_x, click_y, duration=0.10)
        pyautogui.click()
        time.sleep(0.9)   # 等聊天区刷新

        # 从标题栏读联系人名
        contact = bot._read_contact(click_y)
        bot.log(f"     联系人: 【{contact}】", "blue")
        bot.q.put(("contact", contact))

        # 黑名单过滤（优先级高于白名单）
        if bot.cfg.get("blacklist", "").strip():
            if bot._in_blacklist(contact):
                bot.log(f"     ⛔ 在黑名单，跳过", "dim")
                return
        # 白名单过滤
        if bot.cfg.get("whitelist", "").strip():
            if not bot._in_whitelist(contact):
                bot.log(f"     ⛔ 不在白名单，跳过", "dim")
                return

        # OCR 读取对方最新消息
        lines = bot._read_messages()

        self._visited_count += 1
        if lines:
            self._dispatch_with_messages(contact, lines)
        else:
            greeted_before = len(self._greeted_this_round)
            self._send_greeting(contact)
            if len(self._greeted_this_round) > greeted_before:
                self._greeted_count += 1

        # 每人间隔等待（每0.3s检查一次停止信号）
        patrol_iv = bot.cfg.get("patrol_contact_interval", 8)
        bot.log(f"     ⏳ 等待 {patrol_iv}s ...", "dim")
        for _ in range(max(1, int(patrol_iv / 0.3))):
            if not bot._app_running():
                return
            time.sleep(0.3)

    # ════════════════════════════════════════════════════════
    # 消息分派（复用 Bot 路由）
    # ════════════════════════════════════════════════════════
    def _dispatch_with_messages(self, contact: str, lines: list[str]):
        bot = self._bot

        recent    = lines[-10:]  # 最近 10 行，尽可能保留完整段落
        last_line = lines[-1]

        # 去重
        if last_line == bot._last_msg.get(contact, ""):
            bot.log(f"     已处理过此消息，跳过: {last_line}", "dim")
            return

        bot._last_msg[contact] = last_line

        context_lines = recent[:-1]
        if len(last_line) < 8 and len(recent) > 1:
            user_msg = "".join(recent)
        else:
            user_msg = last_line

        bot.log(f"     📨 最新消息: {last_line}", "yellow")
        if context_lines:
            bot.log(f"     📎 前情: {context_lines}", "dim")

        # OCR 增强：纠错后再路由
        if bot.cfg.get("ocr_enhance", False):
            user_msg = bot._ocr_enhance(user_msg)

        from core.bot import PHOTO_KW, _has_kw, _has_meetup_intent

        if _has_kw(last_line, PHOTO_KW):
            bot.log("     🖼 触发：照片请求", "purple")
            bot._route_photo(contact, user_msg, context_lines)
            return

        if _has_meetup_intent(last_line):
            bot.log("     🍽️ 触发：见面请求 → 委婉拒绝", "purple")
            bot._route_meetup(contact, user_msg, context_lines)
            return

        bot._route_ai(contact, user_msg, context_lines)

    # ════════════════════════════════════════════════════════
    # 发开场问候
    # ════════════════════════════════════════════════════════
    def _send_greeting(self, contact: str):
        bot = self._bot

        if contact in self._greeted_this_round:
            bot.log(f"     本轮已向【{contact}】发过问候，跳过", "dim")
            return

        greets = self._get_greets()
        last   = self._last_greet.get(contact, "")
        pool   = [g for g in greets if g != last] or greets

        greeting = random.choice(pool)
        self._last_greet[contact] = greeting
        self._greeted_this_round.add(contact)

        bot.log(f"     💬 无新消息，发开场问候: {greeting}", "green")
        bot.q.put(("chat", contact, "（无新消息，发问候）", greeting))

        if bot.cfg.get("auto_send", True):
            random_delay(2, 5)
            send_text(bot.wx, greeting, bot.log)
        else:
            bot.log("     📋 自动发送未开启，问候已生成但未发出", "yellow")

    # ════════════════════════════════════════════════════════
    # 工具
    # ════════════════════════════════════════════════════════
    def _get_greets(self) -> list[str]:
        if not self._greets:
            greet_path = self._bot.cfg.get("greet_path", "greet.json")
            self._greets = _load_greets(greet_path)
            self._bot.log(
                f"     📖 加载问候语 {len(self._greets)} 条: {greet_path}",
                "dim",
            )
        return self._greets

    def reload_greets(self):
        """强制重新加载问候语（UI 保存配置后调用）"""
        self._greets = []
