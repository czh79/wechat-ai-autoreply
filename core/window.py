"""
core/window.py — 微信窗口定位 & 各区域 bbox 计算

微信布局说明（关键规律）：
  左侧图标栏、会话列表宽度是【固定像素】，不随窗口拉伸。
  聊天区右边界跟随窗口右边，Y方向随窗口高度等比缩放。

  固定宽度（绝对像素，任何窗口尺寸下不变）：
    图标导航栏：0 ~ 54px
    会话列表：54 ~ 234px（宽180px）

  动态区域（跟随窗口尺寸）：
    聊天区：x=234 ~ 窗口右边，Y方向等比缩放
"""
import time
from core.deps import (IS_WINDOWS, HAS_GW, HAS_W32,
                        gw, win32gui, win32con, win32api)


class WeChatWindow:
    REF_H = 799           # 参考高度（仅用于Y方向缩放）

    # 左侧固定宽度（绝对像素，不缩放）
    ICON_BAR_W  = 54      # 图标导航栏宽
    LIST_END_X  = 234     # 会话列表右边界（= 聊天区左边界）

    # Y方向参考坐标（参考高799px，实际按比例缩放）
    REF_LIST_TOP    = 55  # 列表区顶部（搜索框下方）
    REF_LIST_BOT    = 789 # 列表区底部
    REF_TITLE_TOP   = 16
    REF_TITLE_BOT   = 68
    REF_CHAT_TOP    = 68
    REF_CHAT_BOT    = 718
    REF_INPUT_Y     = 755 # 输入框中央Y

    def __init__(self):
        self._hwnd = None
        self._win  = None
        self._rect = None

    # ── 查找 ─────────────────────────────────────────────
    def find(self) -> bool:
        if IS_WINDOWS and HAS_W32:
            return self._find_win32()
        if HAS_GW:
            return self._find_gw()
        return False

    def _find_win32(self) -> bool:
        _IGNORE = ("AI 自动回复", "微信 AI 助手", "监控中心")
        found = []

        def cb(hwnd, _):
            if not win32gui.IsWindowVisible(hwnd):
                return
            title = (win32gui.GetWindowText(hwnd) or "").strip()
            cls   = win32gui.GetClassName(hwnd)
            if any(k in title for k in _IGNORE):
                return
            if not ("微信" in title or "WeChat" in title
                    or cls == "WeChatMainWndForPC"):
                return
            rect = win32gui.GetWindowRect(hwnd)
            w, h = rect[2]-rect[0], rect[3]-rect[1]
            if w < 500 or h < 400:
                return
            place = win32gui.GetWindowPlacement(hwnd)
            if place[1] == win32con.SW_SHOWMAXIMIZED:
                try:
                    brd = win32api.GetSystemMetrics(win32con.SM_CXSIZEFRAME)
                except Exception:
                    brd = 8
                rect = (rect[0]+brd, rect[1]+brd, rect[2]-brd, rect[3]-brd)
            score = (1_000_000 if cls == "WeChatMainWndForPC" else 0) + w * h
            found.append((score, hwnd, rect))

        win32gui.EnumWindows(cb, None)
        if not found:
            return False
        found.sort(key=lambda x: x[0], reverse=True)
        _, self._hwnd, self._rect = found[0]
        return True

    def _find_gw(self) -> bool:
        _IGNORE = ("AI 自动回复", "微信 AI 助手", "监控中心")
        for keyword in ("微信", "WeChat"):
            wins = gw.getWindowsWithTitle(keyword)
            cands = []
            for w in wins:
                t = getattr(w, "title", "") or ""
                if any(k in t for k in _IGNORE):
                    continue
                if (w.right - w.left) < 500 or (w.bottom - w.top) < 400:
                    continue
                cands.append(w)
            if cands:
                best = max(cands, key=lambda x: (x.right-x.left)*(x.bottom-x.top))
                self._win  = best
                self._rect = (best.left, best.top, best.right, best.bottom)
                return True
        return False

    # ── 刷新坐标 ─────────────────────────────────────────
    def refresh(self):
        if IS_WINDOWS and HAS_W32 and self._hwnd:
            try:
                place = win32gui.GetWindowPlacement(self._hwnd)
                r = win32gui.GetWindowRect(self._hwnd)
                if place[1] == win32con.SW_SHOWMAXIMIZED:
                    try:
                        brd = win32api.GetSystemMetrics(win32con.SM_CXSIZEFRAME)
                    except Exception:
                        brd = 8
                    self._rect = (r[0]+brd, r[1]+brd, r[2]-brd, r[3]-brd)
                else:
                    self._rect = r
            except Exception:
                pass
        elif self._win:
            try:
                w = self._win
                self._rect = (w.left, w.top, w.right, w.bottom)
            except Exception:
                pass

    # ── 激活 ─────────────────────────────────────────────
    def activate(self) -> bool:
        try:
            if self._win:
                if getattr(self._win, "isMinimized", False):
                    self._win.restore()
                self._win.activate()
                time.sleep(0.3)
                return True
        except Exception:
            pass
        if IS_WINDOWS and HAS_W32 and self._hwnd:
            try:
                if win32gui.IsIconic(self._hwnd):
                    win32gui.ShowWindow(self._hwnd, win32con.SW_RESTORE)
                win32gui.SetForegroundWindow(self._hwnd)
                time.sleep(0.35)
                return True
            except Exception:
                pass
        return False

    # ── 属性 ─────────────────────────────────────────────
    @property
    def rect(self):
        return self._rect

    @property
    def found(self) -> bool:
        return self._rect is not None

    # ── 内部工具 ─────────────────────────────────────────
    def _dims(self):
        """返回 (left, top, width, height)"""
        if not self._rect:
            return 0, 0, 0, 0
        l, t, r, b = self._rect
        return l, t, r - l, b - t

    def _sy(self, ref_y: int) -> int:
        """Y方向等比缩放（仅Y用，X用固定值）"""
        _, _, _, H = self._dims()
        if H == 0:
            return ref_y
        return int(H * ref_y / self.REF_H)

    # ── bbox 计算（全部修正）────────────────────────────
    def list_bbox(self) -> tuple:
        """
        会话列表截图区域。
        X：固定像素（列表宽度不随窗口变化）
        Y：从搜索框底部到窗口底部（等比缩放）
        """
        l, t, _, H = self._dims()
        return (
            l + self.ICON_BAR_W,                   # 固定 54px
            t + self._sy(self.REF_LIST_TOP),        # ≈搜索框下方
            l + self.LIST_END_X,                    # 固定 234px
            t + self._sy(self.REF_LIST_BOT),        # ≈窗口底部
        )

    def title_bbox(self) -> tuple:
        """聊天顶部标题栏（联系人名）"""
        l, t, W, H = self._dims()
        return (
            l + self.LIST_END_X,                    # 固定左边界
            t + self._sy(self.REF_TITLE_TOP),
            l + W - 200,                            # 右侧留200px给按钮
            t + self._sy(self.REF_TITLE_BOT),
        )

    def chat_bbox(self) -> tuple:
        """聊天内容全区 - 强力右移左边界"""
        l, t, W, H = self._dims()
        chat_left = l + self.LIST_END_X + 70          # 固定 +32px（不再依赖 _sy）
        return (
            chat_left,
            t + self._sy(self.REF_CHAT_TOP),
            l + W - 12,
            t + self._sy(self.REF_CHAT_BOT),
        )

    def chat_last_bbox(self) -> tuple:
        """聊天区底部 - 同步强力右移"""
        l, t, W, H = self._dims()
        chat_bot = t + self._sy(self.REF_CHAT_BOT)
        chat_top = t + self._sy(self.REF_CHAT_TOP)
        top = max(chat_top, chat_bot - self._sy(300))
        return (
            l + self.LIST_END_X + 70,
            top,
            l + W - 12,
            chat_bot - self._sy(8),
        )

    def chat_left_bbox(self) -> tuple:
        """对方气泡区（左半侧全高）- 只截左侧消息，排除右侧自己发送的气泡"""
        l, t, W, H = self._dims()
        chat_left  = l + self.LIST_END_X + 70
        chat_right = l + W - 12
        chat_width = chat_right - chat_left
        return (
            chat_left,
            t + self._sy(self.REF_CHAT_TOP),
            chat_left + int(chat_width * 0.48),  # 只取左侧48%宽度
            t + self._sy(self.REF_CHAT_BOT),
        )

    def chat_left_last_bbox(self) -> tuple:
        """对方气泡区底部（降级用）- 只截左侧最近消息区域"""
        l, t, W, H = self._dims()
        chat_left  = l + self.LIST_END_X + 70
        chat_right = l + W - 12
        chat_width = chat_right - chat_left
        chat_bot   = t + self._sy(self.REF_CHAT_BOT)
        chat_top   = t + self._sy(self.REF_CHAT_TOP)
        top = max(chat_top, chat_bot - self._sy(300))
        return (
            chat_left,
            top,
            chat_left + int(chat_width * 0.48),  # 同样只取左侧48%
            chat_bot - self._sy(8),
        )

    def input_click_pos(self) -> tuple:
        """输入框中央点击坐标"""
        l, t, W, H = self._dims()
        x = l + self.LIST_END_X + (W - self.LIST_END_X) // 2
        y = t + self._sy(self.REF_INPUT_Y)
        return (x, y)

    def list_row_bbox(self, screen_center_y: int) -> tuple:
        """最终版 - 垂直强力校准，解决红点偏移导致错行问题"""
        l, t, _, H = self._dims()
        
        # 单行高度（微信列表实际行高）
        row_h = max(54, self._sy(72))
        
        # 关键修复：红点通常在头像右侧，文字行中心比红点略高 → 向上偏移
        center_y = screen_center_y - self._sy(6)   # 向上微调6px（最重要）
        
        top = max(t + self._sy(self.REF_LIST_TOP) + self._sy(4),
                  center_y - row_h // 2 + self._sy(2))
        bot = min(t + self._sy(self.REF_LIST_BOT),
                  center_y + row_h // 2 - self._sy(6))

        # 左右平衡（长名称 + 避开干扰）
        left_pad  = self._sy(26)   # 避开头像
        right_pad = self._sy(28)   # 保留足够宽度给长名称

        bbox = (
            l + self.ICON_BAR_W + left_pad,
            top,
            l + self.LIST_END_X - right_pad,
            bot
        )

        return bbox
