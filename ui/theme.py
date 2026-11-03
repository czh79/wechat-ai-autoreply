"""
ui/theme.py — 颜色主题 & 公共 Widget 工厂
"""
import tkinter as tk

T = {
    "bg":     "#0d1117",
    "bg2":    "#161b22",
    "bg3":    "#21262d",
    "card":   "#1c2128",
    "border": "#30363d",
    "green":  "#3fb950",
    "blue":   "#58a6ff",
    "red":    "#f85149",
    "yellow": "#e3b341",
    "purple": "#bc8cff",
    "text":   "#e6edf3",
    "dim":    "#8b949e",
    "input":  "#010409",
    "wechat": "#07c160",
    "badge":  "#ff3b30",
}

LOG_TAGS = [
    ("green",  T["green"]),
    ("red",    T["red"]),
    ("yellow", T["yellow"]),
    ("dim",    T["dim"]),
    ("blue",   T["blue"]),
    ("badge",  T["badge"]),
    ("purple", T["purple"]),
]


def lbl(parent, text, **kw):
    d = dict(bg=T["bg2"], fg=T["dim"],
             font=("Microsoft YaHei UI", 9), anchor="w")
    d.update(kw)
    return tk.Label(parent, text=text, **d)


def ent(parent, var=None, show=None):
    return tk.Entry(
        parent, textvariable=var, show=show, width=28,
        bg=T["input"], fg=T["text"], insertbackground=T["blue"],
        relief="flat", font=("Consolas", 10), bd=4,
    )


def btn(parent, text, cmd, bg=None, fg=None, **kw):
    font = kw.pop("font", ("Microsoft YaHei UI", 9))
    return tk.Button(
        parent, text=text, command=cmd,
        bg=bg or T["bg3"], fg=fg or T["text"],
        relief="flat", cursor="hand2", font=font, **kw,
    )


def card_stat(parent, label: str, var_name: str, default: str, color: str):
    """创建一个统计数字卡片，返回 (frame, StringVar)"""
    c  = tk.Frame(parent, bg=T["card"])
    c.pack(fill="x", pady=3)
    sv = tk.StringVar(value=default)
    tk.Label(c, text=label, bg=T["card"], fg=T["dim"],
             font=("Microsoft YaHei UI", 9)).pack(anchor="w", padx=10, pady=(6, 0))
    tk.Label(c, textvariable=sv, bg=T["card"], fg=color,
             font=("Microsoft YaHei UI", 14, "bold")).pack(anchor="w", padx=10, pady=(0, 6))
    return c, sv
