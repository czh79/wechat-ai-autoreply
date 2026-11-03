"""
core/bot.py — 核心调度器

支持两种模式：

  【红点模式】tick()
    激活微信 → 截取会话列表 → OpenCV 检测红点
    for each 红点:
      点击会话 → OCR 联系人名 → OCR 最近3条消息
      去重 → AI/照片/见面 路由 → 发送

  【轮巡模式】patrol_tick()
    激活微信 → 扫描联系人列表行（从上到下）
    for each 联系人行:
      点击 → OCR 最新消息
      有消息 → AI/照片/见面 路由 → 发送
      无消息 → 随机发一条 greet.json 开场问候
"""
import os
import re
import time
import random
import queue

from core.window  import WeChatWindow
from core.capture import grab, save_debug
from core.badge   import BadgeCV
from core.ocr     import OCR
from core.context import Context
from core.ai      import AI
from core.sender  import (send_text, send_photo, get_random_photo,
                           random_delay)
from core.deps    import HAS_AG, HAS_CV2, HAS_NP, pyautogui


# ── 关键词配置 ────────────────────────────────────────────
PHOTO_KW  = ["看看你", "发张照片", "要照片", "照片", "自拍",
              "发张图", "看看照片", "发个照片", "来张图", "拍一张",
              "看你", "给我看看", "发图"]
MEETUP_KW = [
    # 见面类
    "见面", "见一面", "见个面", "见见", "见你", "来见",
    "约吗", "约不约", "约一下", "约个", "约好", "约了吗",
    "出来", "出来玩", "出来坐", "出来聊", "出来一下", "出来吃",
    "见面聊", "见面吧", "见面啊", "见面哦",
    # 吃饭类（含量词变体）
    "吃饭", "吃个饭", "吃顿饭", "一起吃", "约饭", "聚餐",
    "吃点东西", "搓一顿", "吃饭吗", "请你吃", "请吃饭",
    # 喝茶/喝酒/喝咖啡类
    "喝茶", "喝个茶", "喝杯茶", "喝咖啡", "喝杯咖啡",
    "喝酒", "喝一杯", "喝杯酒", "小酌", "喝点东西", "喝个咖啡",
    # 约会/活动类
    "约会", "一起玩", "一起去", "一起逛", "带你去",
    "陪我", "陪你", "看电影", "逛街", "出去走走", "散散步",
]

# 委婉拒绝话术（自然、不生硬、有余地）
REJECT_POOL = [
    "哈哈最近真的好忙哦，等我缓过来再说吧~ 😅",
    "啊这个嘛……最近状态不太好，不太想出门呢 🙈",
    "最近有点事情缠身，暂时不方便哦，改天吧~",
    "哎呀不巧，这段时间排得满满的，下次哈 😄",
    "最近懒懒的，不想动诶，改天再约嘛~ 🌸",
    "哈哈先不了啦，最近比较宅，等我状态好了再说 😜",
    "这个嘛……容我想想哈，最近时间不太自由 😅",
    "最近身体有点不舒服，不方便出门，下次哦~ 🥺",
    "好是好，但最近真的没时间，你懂的~ 😂",
    "哈哈改天嘛，最近有些事要处理，走不开呢 🌷",
]

# 要照片时的矜持回复（第1次触发时用）
PHOTO_SHY_1 = [
    "哎呀，哪有那么容易嘛 😳 先发个红包表达一下诚意呀~",
    "想看照片？先发红包再说哦，哈哈 😜",
    "哼，照片可不是随便给的，先发个红包让我考虑考虑 🙈",
    "发照片？先诚意一下嘛，红包走起~ 😏",
    "哈哈你想的美，先发个红包看看诚意再说 💰",
]

# 第2次还要照片时的继续调侃
PHOTO_SHY_2 = [
    "诶还没收到红包呢，要矜持的哦 😂",
    "哼，红包还没到账呢，照片先等等啦~",
    "哈哈别急别急，红包来了照片立刻发 😎",
    "嗯？红包呢？没有红包哪有照片嘛 🙈",
    "还惦记着照片哈，先把红包发过来再说~ 😜",
]


def _has_kw(text: str, kws: list) -> bool:
    t = text.lower()
    return any(k in t for k in kws)

def _has_meetup_intent(text: str) -> bool:
    return False   # ← 加这一行，屏蔽见面推脱
    """
    判断文本是否含见面邀约意图。
    规则：
      1. 必须命中至少一个 MEETUP_KW
      2. 命中词前 6 个字内不能有独立否定词
         （排除「要不要」「好不好」之类的反问语气）
    """
    _NEG = re.compile(r"(?<![要好行想去来])(不想|不要|不去|不出|没空|没时间|算了|拒绝|不约|不见|不用)")

    t = text.lower()
    for kw in MEETUP_KW:
        idx = t.find(kw)
        if idx == -1:
            continue
        prefix = t[max(0, idx - 6): idx]
        if _NEG.search(prefix):
            continue
        return True
    return False


class Bot:
    # 兜底回复列表，避免重复
    _FALLBACK_REPLIES = [
        "嗯嗯～",
        "好呀～",
        "知道啦",
        "哈哈",
        "好的",
        "了解～",
        "收到～",
        "明白啦",
    ]

    def __init__(self, cfg: dict, ctx: Context, q: queue.Queue):
        self.cfg = cfg
        self.ctx = ctx
        self.q   = q
        self.wx  = WeChatWindow()
        self._last_msg: dict[str, str] = {}
        self._seen_msgs: dict[str, set]  = {}
        self._last_reply: dict[str, str] = {}
        self._photo_req_count: dict[str, int] = {}

        # 轮巡模式子调度器（懒初始化）
        self._patrol = None
        # UI App 实例（启动时由 app.py 注入，供停止检查用）
        self._app = None

    # ── 停止检查（供 PatrolBot 内部各阻塞点调用）──────────
    def _app_running(self) -> bool:
        """
        返回当前监控是否仍在运行。
        PatrolBot 在每个可中断点调用此方法，
        UI 点击"停止"后 app.running 变 False，此方法随即返回 False。
        """
        if self._app is None:
            return True
        return bool(self._app.running)

    def _read_contact_by_redpoint(self, redpoint_x: int, redpoint_y: int) -> tuple[str, str]:
        """
        严格按照你的测量：
        以红点为左上角，向右120px，向下17px
        返回 (clean_name, raw_text)
        """
        region_width = 110
        region_height = 18

        bbox = (
            redpoint_x,
            redpoint_y,
            redpoint_x + region_width,
            redpoint_y + region_height
        )

        raw = OCR.extract(grab(bbox))
        self.log(f"     [红点区域OCR] 原文: {repr(raw[:100])}", "dim")

        name = OCR.clean_name(raw)
        clean = name if name != "未知" else "未识别"
        return clean, (raw or "").strip()

    # ── 白名单匹配 ───────────────────────────────────────
    def _in_whitelist(self, contact: str) -> bool:
        raw = self.cfg.get("whitelist", "").strip()
        if not raw:
            return True

        patterns = [p.strip() for p in raw.split(",") if p.strip()]
        if not patterns:
            return True

        for pat in patterns:
            try:
                if re.search(pat, contact):
                    return True
            except re.error:
                self.log(f"     ⚠️ 白名单正则无效「{pat}」，改用子串匹配", "yellow")
                if pat in contact:
                    return True
        return False

    # ── 黑名单匹配 ─────────────────────────────────
    def _name_matches(self, name: str, raw: str, patterns_str: str) -> bool:
        """检查联系人名或原始OCR文本是否匹配某个模式列表"""
        if not patterns_str or not patterns_str.strip():
            return False
        patterns = [p.strip() for p in patterns_str.split(",") if p.strip()]
        if not patterns:
            return False
        for pat in patterns:
            try:
                if re.search(pat, name) or re.search(pat, raw):
                    return True
            except re.error:
                if pat in name or pat in raw:
                    return True
        return False

    def _in_blacklist(self, contact: str) -> bool:
        raw = self.cfg.get("blacklist", "").strip()
        if not raw:
            return False

        patterns = [p.strip() for p in raw.split(",") if p.strip()]
        if not patterns:
            return False

        for pat in patterns:
            try:
                if re.search(pat, contact):
                    return True
            except re.error:
                self.log(f"     ⚠️ 黑名单正则无效「{pat}」，改用子串匹配", "yellow")
                if pat in contact:
                    return True
        return False

    # ── 日志 ─────────────────────────────────────────────
    def log(self, msg: str, tag: str = ""):
        self.q.put(("log", tag, msg))

    # ── 初始化 ───────────────────────────────────────────
    def setup(self) -> bool:
        ok = self.wx.find()
        if ok:
            self.log(f"✅ 微信窗口: {self.wx.rect}", "green")
        else:
            self.log("❌ 未找到微信窗口", "red")

        from core.deps import HAS_PADDLE, HAS_RAPID, IS_WINDOWS
        if HAS_PADDLE:
            self.log("🔍 OCR 引擎: PaddleOCR ✓（如识别异常请查看控制台错误输出）", "green")
        elif HAS_RAPID:
            self.log("🔍 OCR 引擎: RapidOCR ✓", "green")
        elif IS_WINDOWS:
            self.log("🔍 OCR 引擎: Windows WinRT（建议安装 paddleocr 或 rapidocr-onnxruntime）", "yellow")
        else:
            self.log("🔍 OCR 引擎: Tesseract / EasyOCR", "yellow")

        return ok

    # ── 主循环单次 tick ───────────────────────────────────
    def tick(self):
        self.wx.refresh()
        if not self.wx.found:
            if not self.setup():
                return

        self.wx.activate()
        time.sleep(0.35)

        lb  = self.wx.list_bbox()
        lx1, ly1, lx2, ly2 = lb
        if lx1 < 0 or ly1 < 0 or (lx2 - lx1) < 50 or (ly2 - ly1) < 100:
            self.log(f"窗口坐标异常，跳过本次 bbox={lb}", "dim")
            return
        img = grab(lb)
        if img is None:
            self.log(f"截图失败 bbox={lb}", "red")
            return

        self.log(f"  列表区域: {lb}", "dim")

        method  = "OpenCV" if (HAS_CV2 and HAS_NP) else "颜色扫描"
        badges  = BadgeCV.detect(img)

        if not badges:
            self.log("✓ 无红点，无新消息", "dim")
            return

        self.log(f"🔴 [{method}] 发现 {len(badges)} 个红点", "badge")
        self.q.put(("badge_found", len(badges)))

        badges.sort(key=lambda b: b["cy"])
        badge_interval = self.cfg.get("badge_interval", 3)
        list_height = ly2 - ly1  # 列表区域总高度
        for i, badge in enumerate(badges):
            self._handle_badge(i, len(badges), badge, lb, list_height)
            # 红点间隔等待：确保当前联系人消息完全处理完毕后再处理下一个红点
            if i < len(badges) - 1:
                self.log(f"  ⏳等待 {badge_interval}s 后处理下一个红点...", "dim")
                time.sleep(badge_interval)

    # ── 处理单个红点会话 ─────────────────────────────────
    def _handle_badge(self, idx: int, total: int, badge: dict, lb: tuple, list_height: int = 0):
        bx = lb[0] + badge["cx"]
        by = lb[1] + badge["cy"]
        click_x = (lb[0] + lb[2]) // 2
        click_y = by

        self.log(f"  [{idx+1}/{total}] 红点@({bx},{by})", "yellow")

        name, raw_name = self._read_contact_by_redpoint(bx, by)

        # 位置保护：列表底部 15% 区域的红点，若名字为“未识别”或包含“折叠”，则跳过
        rel_y = badge["cy"]  # 红点在列表图片内的Y坐标
        if list_height > 200 and rel_y > list_height * 0.85:
            if name == "未识别" or "折叠" in raw_name or "折叠" in name:
                self.log(f"     ⛔ 【{name}】位于列表底部，疑似“折叠的聊天”，跳过（未点击）", "dim")
                return
        self.log(f"     联系人: 【{name}】", "blue")
        self.q.put(("contact", name))

        if self.cfg.get("blacklist", "").strip():
            pre_name = name
            if self._in_blacklist(pre_name) or self._name_matches(pre_name, raw_name, self.cfg.get("blacklist", "")):
                self.log(f"     ⛔ 【{pre_name}】在黑名单，跳过（未点击）", "dim")
                return
        if self.cfg.get("whitelist", "").strip():
            pre_name = name
            self.log(f"     预判联系人: 【{pre_name}】", "dim")
            if not (self._in_whitelist(pre_name) or self._name_matches(pre_name, raw_name, self.cfg.get("whitelist", ""))):
                self.log(f"     ⛔ 【{pre_name}】不在白名单，跳过（未点击）", "dim")
                return

        self.log(f"     → 点击({click_x},{click_y})", "yellow")

        if not HAS_AG:
            self.log("缺少 pyautogui", "red")
            return
        self.wx.activate()
        time.sleep(0.2)
        pyautogui.moveTo(click_x, click_y, duration=0.15)
        pyautogui.click()
        time.sleep(1.0)

        if self._in_blacklist(name) or self._name_matches(name, raw_name, self.cfg.get("blacklist", "")):
            self.log(f"     ⛔ 【{name}】在黑名单，跳过", "dim")
            return
        if not self._in_whitelist(name):
            self.log(f"     ⛔ 【{name}】不在白名单，跳过", "dim")
            return

        lines = self._read_messages()
        if not lines:
            self.log("     OCR 无有效消息，跳过", "dim")
            return

        recent    = lines[-10:]
        last_line = lines[-1]

        if last_line == self._last_msg.get(name, ""):
            self.log(f"     已处理: {last_line}", "dim")
            return

        self._last_msg[name] = last_line

        context_lines = recent[:-1]
        # 末尾行太短时把全部行合并成完整消息
        if len(last_line) < 8 and len(recent) > 1:
            user_msg = "".join(recent)
        else:
            user_msg = last_line

        self.log(f"     📨 最新消息: {last_line}", "yellow")
        if context_lines:
            self.log(f"     📎 前情参考: {context_lines}", "dim")

        # OCR 增强：纠错后再路由
        if self.cfg.get("ocr_enhance", False):
            user_msg = self._ocr_enhance(user_msg)

        if _has_kw(last_line, PHOTO_KW):
            self.log(f"     🔍 最新消息含照片关键词，触发发图", "dim")
            self._route_photo(name, user_msg, context_lines)
            return

        if _has_meetup_intent(last_line):
            self.log(f"     🔍 最新消息含见面意图，触发委婉拒绝", "dim")
            self._route_meetup(name, user_msg, context_lines)
            return

        self._route_ai(name, user_msg, context_lines)

    # ── 路由：发图片（矜持版）────────────────────────────
    def _route_photo(self, contact: str, user_msg: str, context_lines: list = None):
        n = self._photo_req_count.get(contact, 0) + 1
        self._photo_req_count[contact] = n
        self.log(f"     📷 照片请求（第{n}次）", "purple")

        self._inject_context(contact, context_lines)

        if n == 1:
            reply = random.choice(PHOTO_SHY_1)
            self.log(f"     😳 矜持回复(1): {reply}", "green")
            self.ctx.add(contact, "user",      user_msg)
            self.ctx.add(contact, "assistant", reply)
            self.q.put(("chat", contact, user_msg, reply))
            if self.cfg.get("auto_send", True):
                random_delay(3, 6)
                send_text(self.wx, reply, self.log)
            return

        if n == 2:
            reply = random.choice(PHOTO_SHY_2)
            self.log(f"     😂 矜持回复(2): {reply}", "green")
            self.ctx.add(contact, "user",      user_msg)
            self.ctx.add(contact, "assistant", reply)
            self.q.put(("chat", contact, user_msg, reply))
            if self.cfg.get("auto_send", True):
                random_delay(3, 6)
                send_text(self.wx, reply, self.log)
            return

        self.log(f"     🖼 第{n}次，终于发照片~", "purple")
        photo_dir  = self.cfg.get("photo_dir", "")
        photo_path = get_random_photo(photo_dir, self.log)

        if not photo_path:
            self._route_ai(contact, user_msg, context_lines)
            return

        self.log(f"     🖼 图片: {os.path.basename(photo_path)}", "dim")
        if self.cfg.get("auto_send", True):
            random_delay(3, 6)
            send_photo(self.wx, photo_path, self.log)
        else:
            self.log(f"     📋 图片准备好（自动发送未开启）: {photo_path}", "yellow")

        self.ctx.add(contact, "user",      user_msg)
        self.ctx.add(contact, "assistant", "[发送了一张照片]")
        self.q.put(("chat", contact, user_msg, "[发送了一张照片]"))
        self._photo_req_count[contact] = 0

    # ── 路由：拒绝见面 ───────────────────────────────────
    def _route_meetup(self, contact: str, user_msg: str, context_lines: list = None):
    #    return False   # ← 加这一行，屏蔽见面推脱

        self.log("     🍽️ 检测到见面请求（最新消息触发）", "purple")
        reply = random.choice(REJECT_POOL)
        self.log(f"     🤖 推脱: {reply}", "green")

        self._inject_context(contact, context_lines)
        self.ctx.add(contact, "user",      user_msg)
        self.ctx.add(contact, "assistant", reply)
        self.q.put(("chat", contact, user_msg, reply))

        if self.cfg.get("auto_send", True):
            random_delay(3, 6)
            send_text(self.wx, reply, self.log)

    def _get_fallback_reply(self, contact: str) -> str:
        last = self._last_reply.get(contact, "")
        candidates = [r for r in self._FALLBACK_REPLIES if r != last]
        if candidates:
            return random.choice(candidates)
        return random.choice(self._FALLBACK_REPLIES)

    # ── 路由：AI 普通回复 ────────────────────────────────
    def _route_ai(self, contact: str, user_msg: str, context_lines: list = None):
        try:
            self._inject_context(contact, context_lines)

            ai    = AI(self.cfg)
            reply = ai.reply(
                self.cfg.get("persona", "你是友善的助手，回复简短自然，不超过30字。"),
                self.ctx.get(contact),
                user_msg,
            )

            if reply == self._last_reply.get(contact, ""):
                reply = self._get_fallback_reply(contact)
                self.log(f"     ⚠️ 回复重复，已替换为: {reply}", "dim")

            self._last_reply[contact] = reply
            self.ctx.add(contact, "user",      user_msg)
            self.ctx.add(contact, "assistant", reply)
            self.log(f"     🤖 AI: {reply}", "green")
            self.q.put(("chat", contact, user_msg, reply))

            if self.cfg.get("auto_send", True):
                random_delay(3, 6)
                send_text(self.wx, reply, self.log)
            else:
                from core.deps import HAS_CLIP, pyperclip
                if HAS_CLIP:
                    pyperclip.copy(reply)
                self.log("     📋 已复制（自动发送未开启）", "yellow")

        except Exception as e:
            self.log(f"     AI 失败: {e}", "red")

    # ── OCR 内容识别增强（AI纠错）────────────────────────
    def _ocr_enhance(self, raw_text: str) -> str:
        """
        把 OCR 识别出的原始文本交给 AI 做纠错润色：
          - 修正明显的识别错字（形近字、同音字替换）
          - 补全被截断的词语
          - 保持原意不变，不添加内容，不回答问题
        返回纠正后的文本；若 AI 调用失败则返回原文。
        """
        if not raw_text or not raw_text.strip():
            return raw_text

        prompt = (
            "以下是通过OCR识别出的微信聊天文字，可能存在识别错误、"
            "形近字替换、词语截断等问题。"
            "请你仅做文字纠错，修正不合语言逻辑的错别字，"
            "让语句通顺自然，保持原意，不要回答问题，不要添加任何内容。"
            "直接输出纠正后的文字，不要解释。"
            f" 原文：{raw_text}"
        )

        try:
            ai = AI(self.cfg)
            corrected = ai.reply(
                "你是专业的文字校对助手，只做错别字纠正，不回答问题，不添加内容。",
                [],          # 无历史
                prompt,
            ).strip()

            # 安全检查：若 AI 返回明显跑偏（长度超过原文3倍），回退原文
            if corrected and len(corrected) < len(raw_text) * 3:
                self.log(f"     🔬 OCR纠错: {repr(raw_text[:60])} → {repr(corrected[:60])}", "dim")
                return corrected
            else:
                self.log("     🔬 OCR纠错结果异常，回退原文", "dim")
                return raw_text
        except Exception as e:
            self.log(f"     🔬 OCR纠错失败: {e}，使用原文", "dim")
            return raw_text

    # ── 前情静默注入 history ─────────────────────────────
    def _inject_context(self, contact: str, context_lines: list | None):
        if not context_lines:
            return
        existing_contents = set()
        for m in self.ctx.get(contact):
            c = m["content"]
            if c.startswith("[前情参考] "):
                c = c[len("[前情参考] "):]
            existing_contents.add(c)

        for line in context_lines:
            if line in existing_contents:
                continue
            tagged = f"[前情参考] {line}"
            self.ctx.add(contact, "user", tagged)
            self.ctx.add(contact, "assistant", "（收到）")

    # ── 读联系人名 ───────────────────────────────────────
    def _read_contact(self, badge_screen_y: int) -> str:
        t_img   = grab(self.wx.title_bbox())
        raw_t   = OCR.extract(t_img)
        contact = OCR.clean_name(raw_t)

        if contact == "未知":
            row_box = self.wx.list_row_bbox(badge_screen_y)
            row_img = grab(row_box)
            raw_row = OCR.extract(row_img)
            contact = OCR.clean_name(raw_row)
            if raw_row:
                self.log(f"     [调试] 列表行OCR: {repr(raw_row[:60])}", "dim")

        if contact == "未知" and raw_t:
            self.log(f"     [调试] 标题OCR原文: {repr(raw_t[:60])}", "dim")

        return contact

    # ── 读最近消息 ───────────────────────────────────────
    def _read_messages(self) -> list[str]:
        """
        只截左侧对方气泡区（右侧是自己发送的消息，不作为回复对象）。
        优先级：从下往上取最新的对方消息。
        失败时降级到左侧底部区域。
        """
        # 只截左侧（对方气泡区）
        c_img = grab(self.wx.chat_left_bbox())
        raw   = OCR.extract(c_img) if c_img else ""
        self.log(f"     OCR 原文(前200): {repr(raw[:200])}", "dim")
        lines = OCR.clean_chat(raw)
        self.log(f"     清洗后共 {len(lines)} 行，最后5: {lines[-5:]}", "dim")

        if lines:
            return lines

        # 降级：左侧底部区域
        self.log("     全区 OCR 无结果，降级截左侧底部", "dim")
        c2    = grab(self.wx.chat_left_last_bbox())
        raw2  = OCR.extract(c2) if c2 else ""
        lines = OCR.clean_chat(raw2)

        if not lines:
            self.log("     底部 OCR 也无结果", "dim")

        return lines

    # ── 调试接口 ─────────────────────────────────────────
    def debug_save(self) -> str:
        self.wx.refresh()
        lb  = self.wx.list_bbox()
        img = grab(lb)
        if img is None:
            return "截图失败"
        path = os.path.abspath("debug_badges.png")
        if HAS_CV2:
            BadgeCV.draw_debug(img, path)
        else:
            img.save(path)
        chat_img = grab(self.wx.chat_last_bbox())
        save_debug(chat_img, "debug_chat.png")
        return path

    def debug_full_ocr(self) -> str:
        self.wx.refresh()
        img = grab(self.wx.chat_bbox())
        return OCR.extract(img)

    # ── 停止检查（供 PatrolBot 内部各阻塞点调用）──────────
    def _app_running(self) -> bool:
        """
        返回当前监控是否仍在运行。
        UI 点击"停止"后 app.running 变 False，此方法随即返回 False。
        _app 由 ui/app.py 在启动时注入，未注入时保守返回 True。
        """
        if self._app is None:
            return True
        return bool(self._app.running)

    # ── 轮巡模式入口 ─────────────────────────────────────
    def patrol_tick(self):
        """
        轮巡模式：从联系人列表从上到下逐一点击，
        有消息→AI路由回复，无消息→发开场问候。
        """
        if self._patrol is None:
            from core.patrol import PatrolBot
            self._patrol = PatrolBot(self)
        self._patrol.patrol_tick()

    def reload_greets(self):
        """重新加载问候语（更换 greet.json 路径后调用）"""
        if self._patrol:
            self._patrol.reload_greets()

    # ══════════════════════════════════════════════════════
    # ══════════════════════════════════════════════════════
    # 【单窗口值守模式】watch_tick()
    #
    # 设计原则：
    #   - 完全不涉及联系人列表、白名单、红点
    #   - 上下文 key 固定为 "__watch__"，跨轮次保留对话记忆
    #   - 首次运行（_watch_snapshot 为 None）：
    #       直接回复当前左侧最新一条，不做比对
    #   - 后续运行：
    #       OCR 结果末行 ≠ 上次快照 → 触发回复
    #       相同 → 跳过
    # ══════════════════════════════════════════════════════
    def watch_tick(self):
        if not self.wx.found:
            self.log("     ⚠️ [值守] 未找到微信窗口", "red")
            return

        self.wx.refresh()
        self.wx.activate()

        # ── 1. OCR 左侧气泡区（对方消息，排除右侧自己发的）──
        c_img = grab(self.wx.chat_left_bbox())
        raw   = OCR.extract(c_img) if c_img else ""
        lines = OCR.clean_chat(raw)

        if not lines:
            c2    = grab(self.wx.chat_left_last_bbox())
            raw   = OCR.extract(c2) if c2 else ""
            lines = OCR.clean_chat(raw)

        if not lines:
            self.log("     [值守] OCR 无内容，跳过", "dim")
            return

        last_line = lines[-1]
        self.log(f"     [值守] 当前末行: {last_line}", "dim")

        # ── 2. 快照比对 ───────────────────────────────────
        # _watch_snapshot 初始为 None（从未运行过）
        # None  → 首次，直接回复（不跳过）
        # 相同  → 无新消息，跳过
        # 不同  → 有新消息，回复
        prev = getattr(self, "_watch_snapshot", None)

        if prev is not None:
            # 内容完全一致 → 跳过
            if last_line == prev:
                self.log("     [值守] 无新内容，跳过", "dim")
                return
            # 指纹相同（只有标点/数字差异）→ 跳过，但更新快照
            fp      = re.sub(r"[^\u4e00-\u9fa5A-Za-z]", "", last_line)
            prev_fp = re.sub(r"[^\u4e00-\u9fa5A-Za-z]", "", prev)
            if fp and fp == prev_fp:
                self.log("     [值守] 指纹相同，跳过", "dim")
                self._watch_snapshot = last_line
                return
            self.log(f"     [值守] 检测到新消息 ↑ 上次: {prev}", "dim")
        else:
            self.log("     [值守] 首次运行，直接回复当前内容", "yellow")

        # 更新快照
        self._watch_snapshot = last_line

        # ── 3. 路由回复（固定 contact="__watch__"，不查联系人）─
        _WATCH_CONTACT = "__watch__"
        context_lines  = lines[:-1]
        user_msg       = last_line

        self.q.put(("contact", "值守中"))   # 仅用于 UI 显示

        if _has_kw(user_msg, PHOTO_KW):
            self._route_photo(_WATCH_CONTACT, user_msg, context_lines)
        elif _has_meetup_intent(user_msg):
            self._route_meetup(_WATCH_CONTACT, user_msg, context_lines)
        else:
            self._route_ai(_WATCH_CONTACT, user_msg, context_lines)

    def watch_reset(self):
        """手动重置值守快照（切换聊天对象时调用）"""
        self._watch_snapshot = None
        self.log("     [值守] 快照已重置，下次将立即回复当前内容", "yellow")


