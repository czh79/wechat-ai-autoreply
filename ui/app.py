"""
ui/app.py — 主窗口 v6.0
微信自动回复助手
"""
import json, os, queue, subprocess, sys, threading, time
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

from ui.theme  import T, btn, LOG_TAGS
from ui.panels import ConfigPanel, PersonaPanel, OthersPanel, StatusPanel, PatrolPanel, WatchPanel
from ui.kb_panel import KBPanel
from core.bot     import Bot
from core.context import Context
from core.ocr     import OCR

_CFG_FILE = "wx_ai_config.json"

_DEFAULT_CFG = dict(
    backend="ollama",
    ollama_url="http://localhost:11434",
    ollama_model="qwen2.5:1.5b",
    deepseek_api_key="",
    deepseek_model="deepseek-v4-flash",
    temperature=0.85,
    max_tokens=300,
    interval=6,
    auto_send=True,
    doubao_api_key="",
    doubao_endpoint="",
    doubao_model="doubao-seed-2-0-lite-260215",
    log_to_file=False,
    photo_dir="",
    blacklist="",
    badge_interval=3,
    # 红点处理间隔，每个红点处理完毕后等待数秒，再处理下一个
    # 轮巡模式配置
    patrol_mode=False,
    patrol_contact_interval=8,
    patrol_max_contacts=1000,
    patrol_pageup_count=20,
    greet_path="greet.json",
    # 值守模式配置
    watch_mode=False,
    watch_interval=5,
    persona=(
        "你是一个活泼可爱的女生，说话风格亲切、俏皮，喜欢用emoji，"
        "回复简短自然，不超过30字；你是26岁，从事人力资源工作，"
        "偶尔傲娇，但情商很高，说话讨人喜欢。"
    ),
)


def _load_cfg():
    cfg = dict(_DEFAULT_CFG)
    try:
        if os.path.exists(_CFG_FILE):
            with open(_CFG_FILE, "r", encoding="utf-8") as f:
                cfg.update(json.load(f))
    except Exception as e:
        print(f"⚠️ 加载配置失败: {e}")
    return cfg


def _save_cfg(cfg):
    try:
        with open(_CFG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ 保存配置失败: {e}")


class App:
    def __init__(self, root: tk.Tk):
        self.root    = root
        self.root.title("AI 自动回复  v6.0  —  微信")
        self.root.configure(bg=T["bg"])
        self.root.geometry("1140x780")
        self.root.minsize(940, 660)

        self.cfg     = _load_cfg()
        self.ctx     = Context(max_turns=12)
        self.q       = queue.Queue()
        self.bot     = Bot(self.cfg, self.ctx, self.q)
        self.running = False
        self.n_reply = 0
        self.n_badge = 0
        self._patrol_mode = self.cfg.get("patrol_mode", False)
        self._watch_mode  = self.cfg.get("watch_mode",  False)

        self._build()
        self._poll()
        self.root.after(800,  lambda: threading.Thread(
            target=self._auto_find, daemon=True).start())

    def _auto_find(self):
        self.bot.setup()

    # ══ 构建界面 ══════════════════════════════════════════
    def _build(self):
        self.root.columnconfigure(0, weight=0)
        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(0, weight=1)
        self._build_sidebar()
        self._build_main()

    # ── 侧边栏 ────────────────────────────────────────────
    def _build_sidebar(self):
        side = tk.Frame(self.root, bg=T["bg2"], width=305)
        side.grid(row=0, column=0, sticky="ns")
        side.grid_propagate(False)

        # 标题
        hdr = tk.Frame(side, bg=T["bg3"], pady=12)
        hdr.pack(fill="x")
        tk.Label(hdr, text="🤖  AI 自动回复助手",
                 font=("Microsoft YaHei UI", 12, "bold"),
                 bg=T["bg3"], fg=T["green"]).pack()
        tk.Label(hdr, text="v6.0  •  微信",
                 font=("Consolas", 8), bg=T["bg3"], fg=T["dim"]).pack(pady=(0, 4))

        nb = ttk.Notebook(side); nb.pack(fill="both", expand=True, padx=6, pady=4)
        s  = ttk.Style(); s.theme_use("clam")
        s.configure("TNotebook", background=T["bg2"], borderwidth=0)
        s.configure("TNotebook.Tab", background=T["bg3"], foreground=T["text"],
                    padding=[7, 3], font=("Microsoft YaHei UI", 8))

        tabs = {}
        for title in ["⚙ 配置", "🎭 角色", "📚 知识库", "🔄 轮巡", "👁 值守", "🔧 其他配置", "📊 状态"]:
            f = tk.Frame(nb, bg=T["bg2"])
            nb.add(f, text=title)
            tabs[title] = f

        self.cfg_panel = ConfigPanel(
            tabs["⚙ 配置"], self.cfg,
            on_save=self._save,
            on_backend_change=lambda: None,
        )
        self.persona_panel = PersonaPanel(
            tabs["🎭 角色"], self.cfg,
            on_apply=self._apply_persona,
        )
        self.kb_panel = KBPanel(
            tabs["📚 知识库"], self.cfg,
            on_save=self._save,
            log_fn=self._log,
        )
        self.patrol_panel = PatrolPanel(
            tabs["🔄 轮巡"], self.cfg,
            on_save=self._save,
        )
        self.watch_panel = WatchPanel(
            tabs["👁 值守"], self.cfg,
            on_save=self._save,
        )
        self.others_panel = OthersPanel(
            tabs["🔧 其他配置"], self.cfg,
            on_find_wx  = self._find_app,
            on_dbg_img  = self._dbg_img,
            on_dbg_ocr  = self._dbg_ocr,
            on_tick     = self._tick_now,
            on_save     = self._save,
        )
        self.status_panel = StatusPanel(tabs["📊 状态"], on_install=self._install)

    # ── 主面板 ────────────────────────────────────────────
    def _build_main(self):
        main = tk.Frame(self.root, bg=T["bg"])
        main.grid(row=0, column=1, sticky="nsew")
        main.columnconfigure(0, weight=1)
        main.rowconfigure(1, weight=1)

        # 工具栏
        bar = tk.Frame(main, bg=T["bg3"], pady=9, padx=14)
        bar.grid(row=0, column=0, sticky="ew")

        # 平台指示灯
        self.v_platform_lbl = tk.StringVar(value="💬 微信模式")
        tk.Label(bar, textvariable=self.v_platform_lbl,
                 font=("Microsoft YaHei UI", 11, "bold"),
                 bg=T["bg3"], fg=T["green"]).pack(side="left")

        # 模式切换标签
        self.v_mode_lbl = tk.StringVar(value="🔴 红点模式")
        self.lbl_mode = tk.Label(
            bar, textvariable=self.v_mode_lbl,
            font=("Microsoft YaHei UI", 9),
            bg=T["bg3"], fg=T["yellow"], padx=8,
        )
        self.lbl_mode.pack(side="left", padx=(12, 0))

        self.btn_s = tk.Button(
            bar, text="▶  开始监控", command=self._toggle,
            bg=T["wechat"], fg="white", relief="flat", cursor="hand2",
            font=("Microsoft YaHei UI", 10, "bold"), padx=14, pady=4,
        )
        self.btn_s.pack(side="right", padx=4)
        btn(bar, "🗑", self._clear, padx=6, pady=4).pack(side="right")
        # 值守模式切换按钮
        self.btn_watch = tk.Button(
            bar, text="切换→值守", command=self._toggle_watch,
            bg=T["bg3"], fg=T["purple"], relief="flat", cursor="hand2",
            font=("Microsoft YaHei UI", 9), padx=8, pady=4,
        )
        self.btn_watch.pack(side="right", padx=2)
        # 红点/轮巡切换按钮
        self.btn_mode = tk.Button(
            bar, text="切换→轮巡", command=self._toggle_mode,
            bg=T["bg3"], fg=T["blue"], relief="flat", cursor="hand2",
            font=("Microsoft YaHei UI", 9), padx=8, pady=4,
        )
        self.btn_mode.pack(side="right", padx=2)

        # 内容区
        ct = tk.Frame(main, bg=T["bg"])
        ct.grid(row=1, column=0, sticky="nsew", padx=10, pady=8)
        ct.columnconfigure(0, weight=1)
        ct.columnconfigure(1, weight=1)
        ct.rowconfigure(0, weight=1)

        self._build_log(ct)
        self._build_chat(ct)

        # 状态栏
        sb = tk.Frame(main, bg=T["bg3"], pady=3, padx=14)
        sb.grid(row=2, column=0, sticky="ew")
        self.v_sb = tk.StringVar(value="就绪")
        tk.Label(sb, textvariable=self.v_sb, bg=T["bg3"], fg=T["dim"],
                 font=("Consolas", 9)).pack(side="left")
        tk.Label(sb, text="v6.0 • 微信 • OpenCV • 多人上下文",
                 bg=T["bg3"], fg=T["dim"], font=("Consolas", 9)).pack(side="right")

        self._log("🚀 v6.0 微信版启动", "green")
        self._log("配置AI → 开始监控", "yellow")
        # 恢复保存的模式状态
        if self._watch_mode:
            self.v_mode_lbl.set("👁 值守模式")
            self.btn_watch.configure(text="退出值守", fg=T["red"])
            self.btn_mode.configure(state="disabled")
            self._log("👁 上次保存为值守模式，已恢复", "blue")
        elif self._patrol_mode:
            self.v_mode_lbl.set("🔄 轮巡模式")
            self.btn_mode.configure(text="切换→红点", fg=T["green"])
            self._log("🔄 上次保存为轮巡模式，已恢复", "blue")

    def _build_log(self, parent):
        lf = tk.LabelFrame(parent, text=" 📋 运行日志 ", bg=T["bg"], fg=T["green"],
                            font=("Microsoft YaHei UI", 9), bd=1, relief="groove")
        lf.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        self.log_w = scrolledtext.ScrolledText(
            lf, wrap="word", state="disabled",
            bg=T["bg2"], fg=T["text"],
            font=("Microsoft YaHei UI", 9), relief="flat", bd=0,
        )
        self.log_w.pack(fill="both", expand=True, padx=3, pady=3)
        for tag, col in LOG_TAGS:
            self.log_w.tag_config(tag, foreground=col)

    def _build_chat(self, parent):
        rp = tk.Frame(parent, bg=T["bg"])
        rp.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        rp.rowconfigure(0, weight=1)
        rp.columnconfigure(0, weight=1)

        self.v_contact = tk.StringVar(value="—")
        ch = tk.Frame(rp, bg=T["bg3"], pady=5); ch.pack(fill="x")
        tk.Label(ch, text="当前联系人：", bg=T["bg3"], fg=T["dim"],
                 font=("Microsoft YaHei UI", 9)).pack(side="left", padx=8)
        tk.Label(ch, textvariable=self.v_contact, bg=T["bg3"], fg=T["blue"],
                 font=("Microsoft YaHei UI", 11, "bold")).pack(side="left")

        cf = tk.LabelFrame(rp, text=" 💬 对话记录（多人独立上下文）",
                            bg=T["bg"], fg=T["green"],
                            font=("Microsoft YaHei UI", 9), bd=1, relief="groove")
        cf.pack(fill="both", expand=True, pady=4)
        self.chat_w = scrolledtext.ScrolledText(
            cf, wrap="word", state="disabled",
            bg=T["bg2"], fg=T["text"],
            font=("Microsoft YaHei UI", 10), relief="flat", bd=0,
        )
        self.chat_w.pack(fill="both", expand=True, padx=3, pady=3)
        self.chat_w.tag_config("who",  foreground=T["purple"])
        self.chat_w.tag_config("user", foreground=T["yellow"])
        self.chat_w.tag_config("ai",   foreground=T["green"])

        mf = tk.LabelFrame(rp, text=" ✏ 手动测试 ", bg=T["bg"], fg=T["green"],
                            font=("Microsoft YaHei UI", 9), bd=1, relief="groove")
        mf.pack(fill="x")
        mr = tk.Frame(mf, bg=T["bg"]); mr.pack(fill="x", padx=4, pady=4)
        self.v_inp = tk.StringVar()
        e = tk.Entry(mr, textvariable=self.v_inp, bg=T["input"], fg=T["text"],
                     insertbackground=T["blue"], relief="flat",
                     font=("Microsoft YaHei UI", 11), bd=4)
        e.pack(side="left", fill="x", expand=True)
        e.bind("<Return>", lambda _: self._manual())
        btn(mr, "发给AI ➤", self._manual,
            bg=T["green"], fg=T["bg"], padx=10, pady=4,
            font=("Microsoft YaHei UI", 9, "bold")).pack(side="right", padx=(4, 0))

    # ══ 回调 ══════════════════════════════════════════════
    def _save(self):
        self.cfg.update(self.cfg_panel.collect())
        self.cfg.update(self.others_panel.collect())
        self.cfg["persona"]    = self.persona_panel.get_persona()
        self.cfg["kb_enabled"] = self.kb_panel.v_enabled.get()
        self.cfg.update(self.patrol_panel.collect())
        self.cfg.update(self.watch_panel.collect())
        self.bot.cfg = self.cfg
        self.bot.reload_greets()
        _save_cfg(self.cfg)
        self._log(f"💾 配置已保存 | {self.cfg['backend']} | {self.cfg['interval']}s", "green")

    def _apply_persona(self):
        self.cfg["persona"] = self.persona_panel.get_persona()
        self.bot.cfg = self.cfg
        _save_cfg(self.cfg)
        self.ctx.clear()
        self._log("🎭 角色已更新，全部历史清空", "yellow")
        self._log("💾 配置已保存", "green")

    def _find_app(self):
        def run():
            ok  = self.bot.setup()
            if ok:
                r = self.bot.wx.rect
                self.q.put(("wx_rect", str(r)))
                self.q.put(("log","dim", f"  列表区: {self.bot.wx.list_bbox()}"))
                self.q.put(("log","dim", f"  聊天区: {self.bot.wx.chat_last_bbox()}"))
        threading.Thread(target=run, daemon=True).start()

    def _dbg_img(self):
        def run():
            path = self.bot.debug_save()
            self.q.put(("log", "yellow", f"📸 调试图: {path}"))
        threading.Thread(target=run, daemon=True).start()

    def _dbg_ocr(self):
        def run():
            self.bot.wx.activate()
            time.sleep(0.3)
            raw   = self.bot.debug_full_ocr()
            lines = OCR.clean_chat(raw)
            self.q.put(("ocr_result", raw))
            last3 = lines[-3:] if lines else []
            self.q.put(("log", "yellow", f"共{len(lines)}行，最近3: {last3}"))
        threading.Thread(target=run, daemon=True).start()

    def _tick_now(self):
        threading.Thread(target=self.bot.tick, daemon=True).start()

    def _toggle_watch(self):
        """切换单窗口值守模式"""
        if self.running:
            messagebox.showwarning("提示", "请先停止监控再切换模式")
            return
        self._watch_mode = not self._watch_mode
        if self._watch_mode:
            # 值守模式开启时，强制退出轮巡
            self._patrol_mode = False
            self.cfg["patrol_mode"] = False
            self.v_mode_lbl.set("👁 值守模式")
            self.btn_watch.configure(text="退出值守", fg=T["red"])
            self.btn_mode.configure(state="disabled")
            # 重置快照，确保启动后首轮立即回复当前内容
            self.bot.watch_reset()
            iv = self.cfg.get("watch_interval", 5)
            self._log(f"👁 已切换为值守模式（仅当前窗口，每 {iv}s 检查一次）", "blue")
        else:
            self.v_mode_lbl.set("🔴 红点模式")
            self.btn_watch.configure(text="切换→值守", fg=T["purple"])
            self.btn_mode.configure(state="normal")
            self._log("🔴 已退出值守模式，恢复红点模式", "yellow")
        self.cfg["watch_mode"] = self._watch_mode
        _save_cfg(self.cfg)

    def _toggle_mode(self):
        """切换红点模式 / 轮巡模式"""
        if self.running:
            messagebox.showwarning("提示", "请先停止监控再切换模式")
            return
        self._patrol_mode = not self._patrol_mode
        if self._patrol_mode:
            self.v_mode_lbl.set("🔄 轮巡模式")
            self.btn_mode.configure(text="切换→红点", fg=T["green"])
            self._log("🔄 已切换为轮巡模式（从上到下遍历联系人）", "blue")
        else:
            self.v_mode_lbl.set("🔴 红点模式")
            self.btn_mode.configure(text="切换→轮巡", fg=T["blue"])
            self._log("🔴 已切换为红点模式（检测新消息红点）", "yellow")
        self.cfg["patrol_mode"] = self._patrol_mode
        _save_cfg(self.cfg)

    def _toggle(self):
        if self.running:
            self.running = False
            self.btn_s.configure(text="▶  开始监控", bg=T["wechat"])
            self.status_panel.v_st.set("已停止")
            self._log("⏹ 监控已停止", "yellow")
        else:
            ok = self.bot.setup() if not self.bot.wx.found else True
            if not ok:
                messagebox.showerror("失败", "未找到微信窗口，请先打开微信")
                return
            self._save()
            self.running = True
            # 值守模式：重置快照，确保开始后立即回复当前内容
            if self._watch_mode:
                self.bot.watch_reset()
            # 开始监控后最小化到任务栏
            self.root.iconify()
            self.btn_s.configure(text="⏹  停止监控", bg=T["red"])
            self.status_panel.v_st.set("运行中 🟢")
            if self._watch_mode:
                mode_name = "值守"
            elif self._patrol_mode:
                mode_name = "轮巡"
            else:
                mode_name = "红点"
            self._log(f"▶ 【微信·{mode_name}模式】监控启动，间隔 {self.cfg['interval']}s", "green")
            self.bot._app = self   # 让 PatrolBot 能查询 running 状态
            threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while self.running:
            try:
                if self._watch_mode:
                    self.bot.watch_tick()
                    iv = self.cfg.get("watch_interval", 5)
                elif self._patrol_mode:
                    self.bot.patrol_tick()
                    iv = self.cfg.get("interval", 6)
                else:
                    self.bot.tick()
                    iv = self.cfg.get("interval", 6)
            except Exception as e:
                self.q.put(("log", "red", f"循环异常: {e}"))
                iv = self.cfg.get("interval", 6)
            for _ in range(iv * 4):
                if not self.running:
                    break
                time.sleep(0.25)

    def _manual(self):
        msg = self.v_inp.get().strip()
        if not msg: return
        self.v_inp.set("")
        contact = self.v_contact.get() or "测试"
        def run():
            try:
                from core.ai import AI
                ai  = AI(self.cfg)
                rep = ai.reply(self.cfg.get("persona",""), self.ctx.get(contact), msg)
                self.ctx.add(contact, "user",      msg)
                self.ctx.add(contact, "assistant", rep)
                self.q.put(("log",  "yellow", f"📨 {msg}"))
                self.q.put(("log",  "green",  f"🤖 {rep}"))
                self.q.put(("chat", contact,  msg, rep))
            except Exception as e:
                self.q.put(("log", "red", str(e)))
        threading.Thread(target=run, daemon=True).start()

    def _install(self):
        pkgs = ["Pillow","numpy","opencv-python","pyautogui",
                "pygetwindow","pyperclip","pytesseract","pywin32"]
        self._log(f"📦 安装: {' '.join(pkgs)}", "yellow")
        def run():
            try:
                r = subprocess.run(
                    [sys.executable,"-m","pip","install"]+pkgs,
                    capture_output=True, text=True, timeout=300,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                msg = "✅ 安装完成，请重启" if r.returncode==0 else f"❌ {r.stderr[-200:]}"
                self.q.put(("log","green" if r.returncode==0 else "red", msg))
            except Exception as e:
                self.q.put(("log","red",str(e)))
        threading.Thread(target=run, daemon=True).start()

    # ══ 日志 ══════════════════════════════════════════════
    def _log(self, msg: str, tag: str = ""):
        ts = time.strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        self.log_w.configure(state="normal")
        self.log_w.insert("end", line + "\n", tag or "")
        self.log_w.see("end")
        self.log_w.configure(state="disabled")
        self.v_sb.set(msg[:90])
        # 文件日志
        if self.cfg.get("log_to_file", False):
            try:
                log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                        f"log_{time.strftime('%Y%m%d')}.txt")
                with open(log_file, "a", encoding="utf-8") as lf:
                    lf.write(line + "\n")
            except Exception:
                pass

    def _chat_add(self, contact: str, u: str, a: str):
        self.chat_w.configure(state="normal")
        self.chat_w.insert("end", f"◆ {contact}\n", "who")
        self.chat_w.insert("end", f"  Ta: {u}\n",   "user")
        self.chat_w.insert("end", f"  AI: {a}\n\n", "ai")
        self.chat_w.see("end")
        self.chat_w.configure(state="disabled")

    def _clear(self):
        self.log_w.configure(state="normal")
        self.log_w.delete("1.0","end")
        self.log_w.configure(state="disabled")

    # ══ 队列轮询 ══════════════════════════════════════════
    def _poll(self):
        try:
            while True:
                item = self.q.get_nowait()
                kind = item[0]
                if kind == "log":
                    _, tag, msg = item
                    self._log(msg, tag)
                    if tag == "badge":
                        self.n_badge += 1
                        self.status_panel.v_bdn.set(str(self.n_badge))
                    if tag == "green" and "已发送" in msg:
                        self.n_reply += 1
                        self.status_panel.v_cnt.set(str(self.n_reply))
                elif kind == "chat":
                    _, contact, u, a = item
                    self._chat_add(contact, u, a)
                    self.v_contact.set(contact)
                elif kind == "contact":
                    self.v_contact.set(item[1])
                elif kind == "wx_rect":
                    self.others_panel.set_wx_info(item[1])
                elif kind == "ocr_result":
                    self.others_panel.set_ocr(item[1])
                elif kind == "badge_found":
                    self.n_badge += item[1]
                    self.status_panel.v_bdn.set(str(self.n_badge))
                elif kind == "patrol_stat":
                    # item = ("patrol_stat", visited, greeted)
                    self.status_panel.v_bdn.set(f"{item[1]}人/{item[2]}问候")
        except queue.Empty:
            pass
        self.root.after(120, self._poll)
