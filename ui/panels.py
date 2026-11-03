"""
ui/panels.py — 侧边栏各 Tab 面板（配置 / 角色 / 调试 / 状态）
"""
import tkinter as tk
from tkinter import ttk, scrolledtext

from ui.theme import T, lbl, ent, btn, card_stat, LOG_TAGS
from core.deps import ALL_DEPS


# ══════════════════════════════════════════════════════════
# 配置 Tab
# ══════════════════════════════════════════════════════════
class ConfigPanel:
    def __init__(self, parent, cfg: dict, on_save, on_backend_change):
        self.cfg  = cfg
        self._save_cb    = on_save
        self._bk_cb      = on_backend_change

        f = tk.Frame(parent, bg=T["bg2"])
        f.pack(fill="both", expand=True, padx=10, pady=8)
        self.frame = f

        self._build_backend(f)
        self._build_ollama(f)
        self._build_deepseek(f)
        self._build_doubao(f)
        self._build_save(f)
        self._on_backend()

    def _build_backend(self, f):
        lbl(f, "AI 后端").pack(anchor="w", pady=(8, 2))
        self.v_bk = tk.StringVar(value=self.cfg.get("backend", "ollama"))
        bf = tk.Frame(f, bg=T["bg2"]); bf.pack(fill="x")
        for val, txt in [("ollama", "🏠 Ollama（本地）"),
                          ("deepseek", "☁ DeepSeek（云端）"),
                          ("doubao",  "🫘 豆包（联网）"),
                          ("hybrid",  "🔀 混合（DeepSeek+豆包）")]:
            tk.Radiobutton(
                bf, text=txt, variable=self.v_bk, value=val,
                bg=T["bg2"], fg=T["text"], selectcolor=T["bg3"],
                activebackground=T["bg2"], activeforeground=T["green"],
                font=("Microsoft YaHei UI", 9),
                command=self._on_backend,
            ).pack(anchor="w")

    def _build_ollama(self, f):
        self.fr_ol = tk.LabelFrame(
            f, text=" Ollama ", bg=T["bg2"], fg=T["green"],
            font=("Microsoft YaHei UI", 9), bd=1, relief="groove")
        self.fr_ol.pack(fill="x", pady=4)
        lbl(self.fr_ol, "服务地址", bg=T["bg2"]).pack(anchor="w", padx=6, pady=(4, 0))
        self.v_url = tk.StringVar(value=self.cfg.get("ollama_url", "http://localhost:11434"))
        ent(self.fr_ol, self.v_url).pack(fill="x", padx=6, pady=2)
        lbl(self.fr_ol, "模型", bg=T["bg2"]).pack(anchor="w", padx=6)
        self.v_mdl = tk.StringVar(value=self.cfg.get("ollama_model", "qwen2.5:1.5b"))
        ent(self.fr_ol, self.v_mdl).pack(fill="x", padx=6, pady=(2, 8))

    def _build_deepseek(self, f):
        self.fr_ds = tk.LabelFrame(
            f, text=" DeepSeek ", bg=T["bg2"], fg=T["dim"],
            font=("Microsoft YaHei UI", 9), bd=1, relief="groove")
        self.fr_ds.pack(fill="x", pady=4)
        lbl(self.fr_ds, "API Key", bg=T["bg2"]).pack(anchor="w", padx=6, pady=(4, 0))
        self.v_key = tk.StringVar(value=self.cfg.get("deepseek_api_key", ""))
        ent(self.fr_ds, self.v_key, show="*").pack(fill="x", padx=6, pady=2)
        lbl(self.fr_ds, "模型", bg=T["bg2"]).pack(anchor="w", padx=6)
        self.v_dsm = tk.StringVar(value=self.cfg.get("deepseek_model", "deepseek-v4-flash"))
        ttk.Combobox(
            self.fr_ds, textvariable=self.v_dsm, width=26,
            values=["deepseek-v4-flash", "deepseek-v4-pro"],
        ).pack(fill="x", padx=6, pady=(2, 8))

    def _build_doubao(self, f):
        self.fr_db = tk.LabelFrame(
            f, text=" 豆包 (Doubao) ", bg=T["bg2"], fg=T["dim"],
            font=("Microsoft YaHei UI", 9), bd=1, relief="groove")
        self.fr_db.pack(fill="x", pady=4)
        lbl(self.fr_db, "API Key", bg=T["bg2"]).pack(anchor="w", padx=6, pady=(4, 0))
        self.v_db_key = tk.StringVar(value=self.cfg.get("doubao_api_key", ""))
        ent(self.fr_db, self.v_db_key, show="*").pack(fill="x", padx=6, pady=2)
        lbl(self.fr_db, "Endpoint ID", bg=T["bg2"]).pack(anchor="w", padx=6)
        self.v_db_ep = tk.StringVar(value=self.cfg.get("doubao_endpoint", ""))
        ent(self.fr_db, self.v_db_ep).pack(fill="x", padx=6, pady=2)
        lbl(self.fr_db, "模型名", bg=T["bg2"]).pack(anchor="w", padx=6)
        self.v_db_mdl = tk.StringVar(value=self.cfg.get("doubao_model", "doubao-seed-2-0-lite-260215"))
        ent(self.fr_db, self.v_db_mdl).pack(fill="x", padx=6, pady=(2, 8))

    def _build_save(self, f):
        btn(f, "💾  保存配置", self._save_cb,
            bg=T["green"], fg=T["bg"], padx=10, pady=6,
            font=("Microsoft YaHei UI", 10, "bold")).pack(fill="x", pady=8)

    def _on_backend(self):
        b = self.v_bk.get()
        self.fr_ol.configure(fg=T["green"] if b == "ollama"    else T["dim"])
        self.fr_ds.configure(fg=T["blue"]  if b == "deepseek"  else T["dim"])
        self.fr_db.configure(fg=T["blue"]  if b in ("doubao", "hybrid") else T["dim"])

    def collect(self) -> dict:
        """收集模型配置"""
        return dict(
            backend          = self.v_bk.get(),
            ollama_url       = self.v_url.get().strip(),
            ollama_model     = self.v_mdl.get().strip(),
            deepseek_api_key = self.v_key.get().strip(),
            deepseek_model   = self.v_dsm.get().strip(),
            doubao_api_key   = self.v_db_key.get().strip(),
            doubao_endpoint  = self.v_db_ep.get().strip(),
            doubao_model     = self.v_db_mdl.get().strip(),
        )


# ══════════════════════════════════════════════════════════
# 角色 Tab
# ══════════════════════════════════════════════════════════
class PersonaPanel:
    PRESETS = [
        ("💬 活泼少女",
         "你是一个活泼可爱的女生，说话风格亲切、俏皮，喜欢用emoji，回复简短自然，不超过30字；"
         "你是26岁，从事人力资源工作，偶尔傲娇，但情商很高，说话讨人喜欢。"),
        ("🤓 理工男",
         "你是严谨的理工男，说话逻辑清晰，偶尔幽默，不超过50字。"),
        ("😎 酷盖",
         "你很酷，说话极简有力，不超过15字。"),
        ("🌸 温柔姐",
         "你是温柔体贴的大姐姐，回复暖心，不超过40字。"),
    ]

    def __init__(self, parent, cfg: dict, on_apply):
        self._apply_cb = on_apply
        f = tk.Frame(parent, bg=T["bg2"])
        f.pack(fill="both", expand=True, padx=10, pady=8)
        self.frame = f

        lbl(f, "🎭 System Prompt（性格设定）").pack(anchor="w", pady=(8, 4))
        self.txt = scrolledtext.ScrolledText(
            f, height=11, wrap="word",
            bg=T["input"], fg=T["text"], insertbackground=T["blue"],
            font=("Microsoft YaHei UI", 10), relief="flat", bd=4,
        )
        self.txt.pack(fill="both", expand=True)
        self.txt.insert("1.0", cfg.get("persona", ""))

        lbl(f, "快速预设").pack(anchor="w", pady=(8, 2))
        bf = tk.Frame(f, bg=T["bg2"]); bf.pack(fill="x")
        for name, pr in self.PRESETS:
            btn(bf, name,
                lambda p=pr: (self.txt.delete("1.0", "end"), self.txt.insert("1.0", p)),
                padx=5, pady=3).pack(side="left", padx=2, pady=2)

        btn(f, "✅  应用（清空全部历史）", self._apply_cb,
            bg=T["wechat"], fg="white", padx=10, pady=6,
            font=("Microsoft YaHei UI", 10, "bold")).pack(fill="x", pady=(8, 0))

    def get_persona(self) -> str:
        return self.txt.get("1.0", "end").strip()


# ══════════════════════════════════════════════════════════
# 其他配置 Tab（原调试 + 参数设置）
# ══════════════════════════════════════════════════════════
class OthersPanel:
    def __init__(self, parent, cfg: dict, on_find_wx, on_dbg_img, on_dbg_ocr, on_tick, on_save=None):
        self.cfg = cfg
        self._save_cb = on_save
        f = tk.Frame(parent, bg=T["bg2"])
        f.pack(fill="both", expand=True, padx=10, pady=8)
        self.frame = f

        # ── 调试功能区 ─────────────────────────────────
        cfr = tk.Frame(f, bg=T["card"]); cfr.pack(fill="x", pady=4)
        tk.Label(cfr, text="微信窗口", bg=T["card"], fg=T["dim"],
                 font=("Microsoft YaHei UI", 9)).pack(anchor="w", padx=8, pady=(6, 0))
        self.v_wx = tk.StringVar(value="未绑定")
        tk.Label(cfr, textvariable=self.v_wx, bg=T["card"], fg=T["green"],
                 font=("Consolas", 9)).pack(anchor="w", padx=8, pady=(0, 6))

        actions = [
            ("🔍 查找微信窗口",   on_find_wx,  T["blue"]),
            ("📸 保存调试截图",   on_dbg_img,  T["bg3"]),
            ("📝 全量 OCR 测试",  on_dbg_ocr,  T["bg3"]),
            ("🔴 立即检测红点",   on_tick,     T["badge"]),
        ]
        for txt, cmd, bg in actions:
            btn(f, txt, cmd, bg=bg,
                fg="white" if bg != T["bg3"] else T["text"],
                pady=5).pack(fill="x", pady=2)

        # ── 参数配置区 ─────────────────────────────────
        pf = tk.LabelFrame(f, text=" 参数 ", bg=T["bg2"], fg=T["green"],
                            font=("Microsoft YaHei UI", 9), bd=1, relief="groove")
        pf.pack(fill="x", pady=(8, 4))

        r1 = tk.Frame(pf, bg=T["bg2"]); r1.pack(fill="x", padx=6, pady=3)
        lbl(r1, "Temperature:", bg=T["bg2"]).pack(side="left")
        self.v_tp = tk.DoubleVar(value=self.cfg.get("temperature", 0.85))
        tk.Scale(r1, variable=self.v_tp, from_=0, to=2, resolution=0.05,
                 orient="horizontal", length=100, bg=T["bg2"], fg=T["text"],
                 troughcolor=T["bg3"], highlightthickness=0, sliderlength=12,
                 ).pack(side="left")
        tk.Label(r1, textvariable=self.v_tp, bg=T["bg2"], fg=T["blue"],
                 font=("Consolas", 9), width=5).pack(side="left")

        r2 = tk.Frame(pf, bg=T["bg2"]); r2.pack(fill="x", padx=6, pady=(0, 4))
        lbl(r2, "检测间隔(秒):", bg=T["bg2"]).pack(side="left")
        self.v_iv = tk.IntVar(value=self.cfg.get("interval", 6))
        tk.Spinbox(r2, from_=3, to=60, textvariable=self.v_iv, width=5,
                   bg=T["input"], fg=T["text"],
                   buttonbackground=T["bg3"]).pack(side="left", padx=4)

        r3 = tk.Frame(pf, bg=T["bg2"]); r3.pack(fill="x", padx=6, pady=(0, 4))
        lbl(r3, "红点间隔(秒):", bg=T["bg2"]).pack(side="left")
        self.v_bi = tk.IntVar(value=self.cfg.get("badge_interval", 3))
        tk.Spinbox(r3, from_=1, to=30, textvariable=self.v_bi, width=5,
                   bg=T["input"], fg=T["text"],
                   buttonbackground=T["bg3"]).pack(side="left", padx=4)
        tk.Label(r3, text="(两个红点处理之间的等待秒数)",
                 bg=T["bg2"], fg=T["dim"],
                 font=("Microsoft YaHei UI", 8)).pack(side="left")

        # ── 开关区 ─────────────────────────────────────
        self.v_as = tk.BooleanVar(value=self.cfg.get("auto_send", True))
        tk.Checkbutton(f, text="🚀 自动发送（Ctrl+V + Enter）",
                       variable=self.v_as, bg=T["bg2"], fg=T["yellow"],
                       selectcolor=T["bg3"], activebackground=T["bg2"],
                       font=("Microsoft YaHei UI", 9),
                       ).pack(anchor="w", pady=(4, 0))

        self.v_logfile = tk.BooleanVar(value=self.cfg.get("log_to_file", False))
        tk.Checkbutton(f, text="📝 日志输出到文件",
                       variable=self.v_logfile, bg=T["bg2"], fg=T["yellow"],
                       selectcolor=T["bg3"], activebackground=T["bg2"],
                       font=("Microsoft YaHei UI", 9),
                       ).pack(anchor="w", pady=(4, 0))

        self.v_ocr_enhance = tk.BooleanVar(value=self.cfg.get("ocr_enhance", False))
        tk.Checkbutton(f, text="🔬 内容识别AI加强（OCR纠错）",
                       variable=self.v_ocr_enhance, bg=T["bg2"], fg=T["blue"],
                       selectcolor=T["bg3"], activebackground=T["bg2"],
                       font=("Microsoft YaHei UI", 9),
                       ).pack(anchor="w", pady=(4, 0))

        # ── 路径区 ─────────────────────────────────────
        lbl(f, "图片目录（照片请求时发送）").pack(anchor="w", pady=(8, 2))
        self.v_pdir = tk.StringVar(value=self.cfg.get("photo_dir", ""))
        ent(f, self.v_pdir).pack(fill="x", pady=2)

        lbl(f, "白名单（逗号分隔，支持正则，留空=回复所有人）").pack(anchor="w", pady=(4, 2))
        self.v_wl = tk.StringVar(value=self.cfg.get("whitelist", ""))
        ent(f, self.v_wl).pack(fill="x", pady=2)

        lbl(f, "黑名单（逗号分隔，支持正则，匹配则忽略）").pack(anchor="w", pady=(4, 2))
        self.v_bl = tk.StringVar(value=self.cfg.get("blacklist", ""))
        ent(f, self.v_bl).pack(fill="x", pady=2)

        # ── 保存按钮 ─────────────────────────────────
        btn(f, "💾  保存配置", self._save_cb,
            bg=T["green"], fg=T["bg"], padx=10, pady=6,
            font=("Microsoft YaHei UI", 10, "bold")).pack(fill="x", pady=(8, 0))

        # ── OCR 原文输出区 ─────────────────────────────
        lbl(f, "OCR 原文输出").pack(anchor="w", pady=(10, 3))
        self.txt_ocr = scrolledtext.ScrolledText(
            f, height=6, wrap="word",
            bg=T["input"], fg=T["yellow"],
            font=("Consolas", 9), relief="flat", bd=2,
        )
        self.txt_ocr.pack(fill="both", expand=True)

    def set_wx_info(self, text: str):
        self.v_wx.set(text)

    def set_ocr(self, text: str):
        self.txt_ocr.delete("1.0", "end")
        self.txt_ocr.insert("1.0", text)

    def collect(self) -> dict:
        return dict(
            badge_interval = int(self.v_bi.get()),
            temperature  = float(self.v_tp.get()),
            interval     = int(self.v_iv.get()),
            auto_send    = self.v_as.get(),
            ocr_enhance  = self.v_ocr_enhance.get(),
            log_to_file  = self.v_logfile.get(),
            photo_dir    = self.v_pdir.get().strip(),
            whitelist    = self.v_wl.get().strip(),
            blacklist    = self.v_bl.get().strip(),
        )



# ══════════════════════════════════════════════════════════
# 状态 Tab
# ══════════════════════════════════════════════════════════
class StatusPanel:
    def __init__(self, parent, on_install):
        f = tk.Frame(parent, bg=T["bg2"])
        f.pack(fill="both", expand=True, padx=10, pady=8)
        self.frame = f

        _, self.v_cnt = card_stat(f, "已回复",  "v_cnt", "0",  T["green"])
        _, self.v_bdn = card_stat(f, "红点触发", "v_bdn", "0",  T["badge"])
        _, self.v_st  = card_stat(f, "运行状态", "v_st",  "待机", T["yellow"])

        lbl(f, "依赖检测").pack(anchor="w", pady=(10, 3))
        for name, ok in ALL_DEPS.items():
            r = tk.Frame(f, bg=T["bg2"]); r.pack(fill="x")
            tk.Label(r, text="✓" if ok else "✗", bg=T["bg2"],
                     fg=T["green"] if ok else T["red"],
                     font=("Consolas", 10)).pack(side="left")
            tk.Label(r, text=f" {name}", bg=T["bg2"], fg=T["text"],
                     font=("Microsoft YaHei UI", 9)).pack(side="left")

        btn(f, "📦 安装全部依赖", on_install, pady=4).pack(fill="x", pady=(10, 0))


# ══════════════════════════════════════════════════════════
# 轮巡模式配置 Tab
# ══════════════════════════════════════════════════════════
class PatrolPanel:
    """
    轮巡模式专属配置面板。
    负责配置：联系人间隔、最大联系人数、问候语文件路径、问候语预览/编辑。
    """

    def __init__(self, parent, cfg: dict, on_save):
        self.cfg      = cfg
        self._save_cb = on_save

        f = tk.Frame(parent, bg=T["bg2"])
        f.pack(fill="both", expand=True, padx=10, pady=8)
        self.frame = f

        self._build_intro(f)
        self._build_timing(f)
        self._build_greet_path(f)
        self._build_greet_preview(f)
        self._build_save(f)

    # ── 说明区 ────────────────────────────────────────────
    def _build_intro(self, f):
        info = tk.LabelFrame(
            f, text=" ℹ️ 轮巡模式说明 ",
            bg=T["bg2"], fg=T["blue"],
            font=("Microsoft YaHei UI", 9), bd=1, relief="groove",
        )
        info.pack(fill="x", pady=(6, 8))
        desc = (
            "轮巡模式：固定坐标步进 + PageDown 翻页 + PageUp 回顶\n"
            "  • 第1行Y固定，每行间距 66px，每屏处理 15 人\n"
            "  • 一屏处理完 → 点击列表区激活焦点 → 按 PageDown\n"
            "  • 全部处理完 → 连按 PageUp N 次回到顶部 → 新一轮\n"
            "  • 有新消息 → AI 智能回复  |  无消息 → 发开场问候\n"
            "点击工具栏「切换→轮巡」按钮启用本模式。"
        )
        tk.Label(
            info, text=desc,
            bg=T["bg2"], fg=T["dim"],
            font=("Microsoft YaHei UI", 9),
            justify="left",
        ).pack(anchor="w", padx=8, pady=6)

    # ── 时序参数 ──────────────────────────────────────────
    def _build_timing(self, f):
        pf = tk.LabelFrame(
            f, text=" ⏱ 时序参数 ",
            bg=T["bg2"], fg=T["green"],
            font=("Microsoft YaHei UI", 9), bd=1, relief="groove",
        )
        pf.pack(fill="x", pady=4)

        # 每个联系人处理间隔
        r1 = tk.Frame(pf, bg=T["bg2"]); r1.pack(fill="x", padx=8, pady=4)
        lbl(r1, "联系人间隔(秒):", bg=T["bg2"]).pack(side="left")
        self.v_ci = tk.IntVar(value=self.cfg.get("patrol_contact_interval", 8))
        tk.Spinbox(
            r1, from_=3, to=120, textvariable=self.v_ci, width=5,
            bg=T["input"], fg=T["text"], buttonbackground=T["bg3"],
        ).pack(side="left", padx=6)
        tk.Label(
            r1, text="(点击每人后等待此时间再继续)",
            bg=T["bg2"], fg=T["dim"],
            font=("Microsoft YaHei UI", 8),
        ).pack(side="left")

        # 最大联系人数
        r2 = tk.Frame(pf, bg=T["bg2"]); r2.pack(fill="x", padx=8, pady=(0, 6))
        lbl(r2, "最大联系人数:", bg=T["bg2"]).pack(side="left")
        self.v_mc = tk.IntVar(value=self.cfg.get("patrol_max_contacts", 1000))
        tk.Spinbox(
            r2, from_=1, to=9999, textvariable=self.v_mc, width=6,
            bg=T["input"], fg=T["text"], buttonbackground=T["bg3"],
        ).pack(side="left", padx=6)
        tk.Label(
            r2, text="(每次轮巡最多处理此数量的联系人)",
            bg=T["bg2"], fg=T["dim"],
            font=("Microsoft YaHei UI", 8),
        ).pack(side="left")

        # PageUp 回顶次数
        r3 = tk.Frame(pf, bg=T["bg2"]); r3.pack(fill="x", padx=8, pady=(0, 6))
        lbl(r3, "回顶 PageUp 次数:", bg=T["bg2"]).pack(side="left")
        self.v_pu = tk.IntVar(value=self.cfg.get("patrol_pageup_count", 20))
        tk.Spinbox(
            r3, from_=1, to=100, textvariable=self.v_pu, width=5,
            bg=T["input"], fg=T["text"], buttonbackground=T["bg3"],
        ).pack(side="left", padx=6)
        tk.Label(
            r3, text="(所有联系人处理完后，连按此次数 PageUp 回到列表顶部)",
            bg=T["bg2"], fg=T["dim"],
            font=("Microsoft YaHei UI", 8),
        ).pack(side="left")

    # ── 问候语文件路径 ────────────────────────────────────
    def _build_greet_path(self, f):
        gf = tk.LabelFrame(
            f, text=" 💬 问候语配置文件 ",
            bg=T["bg2"], fg=T["green"],
            font=("Microsoft YaHei UI", 9), bd=1, relief="groove",
        )
        gf.pack(fill="x", pady=4)

        tk.Label(
            gf,
            text="无新消息时随机从此 JSON 文件中选一条发送",
            bg=T["bg2"], fg=T["dim"],
            font=("Microsoft YaHei UI", 8),
        ).pack(anchor="w", padx=8, pady=(4, 0))

        pr = tk.Frame(gf, bg=T["bg2"]); pr.pack(fill="x", padx=8, pady=(2, 6))
        self.v_gp = tk.StringVar(value=self.cfg.get("greet_path", "greet.json"))
        ent(pr, self.v_gp).pack(side="left", fill="x", expand=True)
        btn(
            pr, "📂 重载", self._reload_preview,
            bg=T["bg3"], fg=T["text"], padx=6, pady=2,
        ).pack(side="right", padx=(4, 0))

    # ── 问候语预览 & 快速编辑 ─────────────────────────────
    def _build_greet_preview(self, f):
        lbl(f, "问候语预览（可直接编辑后保存）").pack(anchor="w", pady=(8, 3))

        self.txt_greet = scrolledtext.ScrolledText(
            f, height=10, wrap="word",
            bg=T["input"], fg=T["yellow"],
            font=("Microsoft YaHei UI", 10), relief="flat", bd=4,
        )
        self.txt_greet.pack(fill="both", expand=True)

        # 立即载入预览
        self._reload_preview()

        hint = tk.Label(
            f,
            text="✏ 直接在上方编辑，点「保存」后同步写入 JSON 文件",
            bg=T["bg2"], fg=T["dim"],
            font=("Microsoft YaHei UI", 8),
        )
        hint.pack(anchor="w", pady=(2, 0))

    # ── 底部保存按钮 ──────────────────────────────────────
    def _build_save(self, f):
        bf = tk.Frame(f, bg=T["bg2"]); bf.pack(fill="x", pady=(8, 0))
        btn(
            bf, "💾  保存配置", self._on_save,
            bg=T["green"], fg=T["bg"], padx=10, pady=6,
            font=("Microsoft YaHei UI", 10, "bold"),
        ).pack(side="left", fill="x", expand=True, padx=(0, 4))
        btn(
            bf, "🔄 重载问候语", self._reload_preview,
            bg=T["bg3"], fg=T["text"], padx=8, pady=6,
        ).pack(side="right")

    # ── 内部方法 ──────────────────────────────────────────
    def _reload_preview(self):
        """从文件重新加载问候语到预览框"""
        import json, os
        path = self.v_gp.get().strip()
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as fp:
                    data = json.load(fp)
                lines = "\n".join(
                    f"{i+1}. {item['text']}"
                    for i, item in enumerate(data)
                    if isinstance(item, dict) and item.get("text")
                )
            else:
                lines = f"⚠️ 文件不存在: {path}\n\n请检查路径或点击「保存」创建默认文件"
        except Exception as e:
            lines = f"❌ 加载失败: {e}"

        self.txt_greet.delete("1.0", "end")
        self.txt_greet.insert("1.0", lines)

    def _on_save(self):
        """保存配置 + 将预览框内容写回 JSON 文件"""
        import json, re
        # 先写回 greet.json
        path = self.v_gp.get().strip()
        raw = self.txt_greet.get("1.0", "end").strip()
        lines = [
            re.sub(r"^\d+\.\s*", "", line).strip()
            for line in raw.splitlines()
            if line.strip()
        ]
        data = [{"id": i+1, "text": line} for i, line in enumerate(lines) if line]
        try:
            with open(path, "w", encoding="utf-8") as fp:
                json.dump(data, fp, ensure_ascii=False, indent=2)
        except Exception as e:
            import tkinter.messagebox as mb
            mb.showerror("保存失败", str(e))
            return
        # 再调全局保存
        self._save_cb()

    def collect(self) -> dict:
        """收集轮巡配置项"""
        return {
            "patrol_contact_interval": int(self.v_ci.get()),
            "patrol_max_contacts":     int(self.v_mc.get()),
            "patrol_pageup_count":     int(self.v_pu.get()),
            "greet_path":              self.v_gp.get().strip(),
        }


# ══════════════════════════════════════════════════════════
# 单窗口值守 Tab
# ══════════════════════════════════════════════════════════
class WatchPanel:
    """
    单窗口值守模式配置面板。
    不扫联系人列表，只盯当前打开的聊天窗口，
    每隔 N 秒 OCR 左侧气泡区，有新内容就 AI 回复。
    """

    def __init__(self, parent, cfg: dict, on_save):
        self.cfg      = cfg
        self._save_cb = on_save

        f = tk.Frame(parent, bg=T["bg2"])
        f.pack(fill="both", expand=True, padx=10, pady=8)
        self.frame = f

        self._build_intro(f)
        self._build_timing(f)
        self._build_save(f)

    # ── 说明区 ────────────────────────────────────────────
    def _build_intro(self, f):
        info = tk.LabelFrame(
            f, text=" 👁 单窗口值守说明 ",
            bg=T["bg2"], fg=T["blue"],
            font=("Microsoft YaHei UI", 9), bd=1, relief="groove",
        )
        info.pack(fill="x", pady=(6, 8))
        desc = (
            "值守模式：盯住当前微信聊天窗口，不切换联系人\n"
            "  • 每隔 N 秒截图一次左侧气泡区（对方消息）\n"
            "  • 与上次快照比对，仅内容有变化时才触发 AI 回复\n"
            "  • 联系人从标题栏自动识别，上下文独立维护\n"
            "  • 适合：专注陪聊某一个人，或调试 AI 回复效果\n"
            "点击工具栏「切换→值守」按钮启用本模式。"
        )
        tk.Label(
            info, text=desc,
            bg=T["bg2"], fg=T["dim"],
            font=("Microsoft YaHei UI", 9),
            justify="left",
        ).pack(anchor="w", padx=8, pady=6)

    # ── 时序参数 ──────────────────────────────────────────
    def _build_timing(self, f):
        pf = tk.LabelFrame(
            f, text=" ⏱ 检测间隔 ",
            bg=T["bg2"], fg=T["green"],
            font=("Microsoft YaHei UI", 9), bd=1, relief="groove",
        )
        pf.pack(fill="x", pady=4)

        r1 = tk.Frame(pf, bg=T["bg2"]); r1.pack(fill="x", padx=8, pady=6)
        lbl(r1, "检测间隔(秒):", bg=T["bg2"]).pack(side="left")
        self.v_interval = tk.IntVar(value=self.cfg.get("watch_interval", 5))
        tk.Spinbox(
            r1, from_=1, to=120, textvariable=self.v_interval, width=5,
            bg=T["input"], fg=T["text"], buttonbackground=T["bg3"],
        ).pack(side="left", padx=6)
        tk.Label(
            r1, text="（每隔此秒数检查一次左侧消息，默认 5 秒）",
            bg=T["bg2"], fg=T["dim"],
            font=("Microsoft YaHei UI", 8),
        ).pack(side="left")

        # 说明：快照比对机制
        r2 = tk.Frame(pf, bg=T["bg2"]); r2.pack(fill="x", padx=8, pady=(0, 6))
        tk.Label(
            r2,
            text="✅ 只有左侧消息最后一行与上次不同，才会触发 AI 回复（防重复）",
            bg=T["bg2"], fg=T["green"],
            font=("Microsoft YaHei UI", 8),
        ).pack(anchor="w")

    # ── 保存按钮 ──────────────────────────────────────────
    def _build_save(self, f):
        bf = tk.Frame(f, bg=T["bg2"]); bf.pack(fill="x", pady=(12, 0))
        btn(
            bf, "💾  保存配置", self._on_save,
            bg=T["green"], fg=T["bg"], padx=10, pady=6,
            font=("Microsoft YaHei UI", 10, "bold"),
        ).pack(fill="x")

    def _on_save(self):
        self._save_cb()

    def collect(self) -> dict:
        return {
            "watch_interval": int(self.v_interval.get()),
        }
