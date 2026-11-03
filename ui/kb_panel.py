"""
ui/kb_panel.py — 知识库管理面板

功能：
  - 启用/禁用知识库
  - 上传文件（.txt .md .pdf .docx）
  - 粘贴文本
  - 文档列表：查看/删除
  - 实时状态显示（文档数、块数）
"""
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
import threading
import os
import re

from ui.theme import T, lbl, btn


class KBPanel:
    def __init__(self, parent: tk.Frame, cfg: dict, on_save=None, log_fn=None):
        self.cfg    = cfg
        self.on_save = on_save
        self.log_fn  = log_fn or (lambda msg, tag="": None)
        self._build(parent)
        self._refresh_list()

    # ══ 构建 UI ══════════════════════════════════════════

    def _build(self, parent):
        wrap = tk.Frame(parent, bg=T["bg2"])
        wrap.pack(fill="both", expand=True, padx=8, pady=6)

        # ── 标题行 + 总开关 ───────────────────────────────
        top = tk.Frame(wrap, bg=T["bg2"])
        top.pack(fill="x", pady=(0, 6))

        tk.Label(top, text="📚 业务知识库",
                 bg=T["bg2"], fg=T["blue"],
                 font=("Microsoft YaHei UI", 11, "bold")).pack(side="left")

        self.v_enabled = tk.BooleanVar(
            value=self.cfg.get("kb_enabled", False))
        self._sw = tk.Checkbutton(
            top, text="启用",
            variable=self.v_enabled,
            command=self._on_toggle,
            bg=T["bg2"], fg=T["yellow"],
            selectcolor=T["bg3"],
            activebackground=T["bg2"],
            font=("Microsoft YaHei UI", 9),
        )
        self._sw.pack(side="right")

        tk.Label(top,
                 text="客服/业务场景：上传文档后，AI 会优先参考文档内容回答",
                 bg=T["bg2"], fg=T["dim"],
                 font=("Microsoft YaHei UI", 8),
                 wraplength=260, justify="left",
                 ).pack(side="left", padx=(8, 0))

        # ── 状态栏 ────────────────────────────────────────
        sf = tk.Frame(wrap, bg=T["bg3"], pady=4)
        sf.pack(fill="x", pady=(0, 8))

        self.v_status = tk.StringVar(value="未加载")
        tk.Label(sf, textvariable=self.v_status,
                 bg=T["bg3"], fg=T["green"],
                 font=("Consolas", 8)).pack(side="left", padx=8)

        # ── 上传区 ────────────────────────────────────────
        uf = tk.LabelFrame(wrap,
                           text=" 添加文档 ",
                           bg=T["bg2"], fg=T["text"],
                           font=("Microsoft YaHei UI", 9),
                           bd=1, relief="groove")
        uf.pack(fill="x", pady=(0, 8))

        # 按钮行
        bf = tk.Frame(uf, bg=T["bg2"])
        bf.pack(fill="x", padx=6, pady=(6, 4))

        btn(bf, "📂 上传文件",  self._upload_file,
            bg=T["bg3"], fg=T["blue"]).pack(side="left", padx=(0, 6))
        btn(bf, "📋 粘贴文本", self._paste_text,
            bg=T["bg3"], fg=T["yellow"]).pack(side="left")

        lbl(uf, "支持 .txt  .md  .pdf  .docx（pdf/docx 需安装对应库）",
            fg=T["dim"]).pack(anchor="w", padx=6, pady=(0, 6))

        # ── 文档列表 ──────────────────────────────────────
        lf = tk.LabelFrame(wrap,
                           text=" 已载入文档 ",
                           bg=T["bg2"], fg=T["text"],
                           font=("Microsoft YaHei UI", 9),
                           bd=1, relief="groove")
        lf.pack(fill="both", expand=True)

        # 列表 + 滚动条
        lbox_f = tk.Frame(lf, bg=T["bg2"])
        lbox_f.pack(fill="both", expand=True, padx=6, pady=6)

        sb = tk.Scrollbar(lbox_f, bg=T["bg3"])
        sb.pack(side="right", fill="y")

        self.listbox = tk.Listbox(
            lbox_f,
            bg=T["input"], fg=T["text"],
            selectbackground=T["bg3"],
            selectforeground=T["blue"],
            font=("Consolas", 9),
            relief="flat", bd=0,
            yscrollcommand=sb.set,
            height=6,
        )
        self.listbox.pack(side="left", fill="both", expand=True)
        sb.config(command=self.listbox.yview)

        btn(lf, "🗑 删除选中", self._delete_selected,
            bg=T["red"], fg=T["bg"]).pack(anchor="e", padx=6, pady=(0, 6))

    # ══ 事件处理 ══════════════════════════════════════════

    def _on_toggle(self):
        enabled = self.v_enabled.get()
        self.cfg["kb_enabled"] = enabled
        if self.on_save:
            self.on_save()
        self.log_fn(
            f"📚 知识库已{'启用' if enabled else '禁用'}",
            "green" if enabled else "yellow",
        )
        self._refresh_list()

    def _refresh_list(self):
        """刷新文档列表和状态栏"""
        try:
            from core.knowledge import get_doc_store
            ds = get_doc_store()
            docs = ds.list_documents()
            self.listbox.delete(0, tk.END)
            for d in docs:
                self.listbox.insert(
                    tk.END,
                    f"  {d['name']}  ({d['chunks']} 块)",
                )
            if docs:
                self.v_status.set(
                    f"✓ {ds.doc_count} 份文档 · {ds.chunk_count} 个检索块"
                    + ("  [已启用]" if self.cfg.get("kb_enabled") else "  [未启用]")
                )
            else:
                self.v_status.set("暂无文档，请上传")
        except Exception as e:
            self.v_status.set(f"加载失败: {e}")

    def _upload_file(self):
        paths = filedialog.askopenfilenames(
            title="选择文档",
            filetypes=[
                ("文本文件", "*.txt *.md"),
                ("PDF", "*.pdf"),
                ("Word", "*.docx"),
                ("所有文件", "*.*"),
            ],
        )
        if not paths:
            return
        threading.Thread(target=self._do_upload, args=(list(paths),),
                         daemon=True).start()

    def _do_upload(self, paths: list[str]):
        from core.knowledge import get_doc_store
        ds = get_doc_store()
        ok, fail = 0, 0
        for path in paths:
            name = os.path.basename(path)
            try:
                text = self._read_file(path)
                if not text.strip():
                    self.log_fn(f"⚠️ {name} 内容为空，跳过", "yellow")
                    fail += 1
                    continue
                if ds.add_document(name, text):
                    self.log_fn(f"📚 已导入: {name} ({len(text)} 字)", "green")
                    ok += 1
                else:
                    fail += 1
            except Exception as e:
                self.log_fn(f"❌ 导入失败 {name}: {e}", "red")
                fail += 1
        self.log_fn(
            f"📚 上传完成：成功 {ok} 份{'，失败 ' + str(fail) + ' 份' if fail else ''}",
            "green" if not fail else "yellow",
        )
        self._refresh_list()

    def _read_file(self, path: str) -> str:
        """读取各类文件为纯文本"""
        ext = os.path.splitext(path)[1].lower()
        if ext in (".txt", ".md"):
            for enc in ("utf-8", "gbk", "utf-16"):
                try:
                    with open(path, "r", encoding=enc) as f:
                        return f.read()
                except UnicodeDecodeError:
                    continue
            raise ValueError("无法识别文件编码")
        elif ext == ".pdf":
            return self._read_pdf(path)
        elif ext == ".docx":
            return self._read_docx(path)
        else:
            # 尝试当 txt 读
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()

    @staticmethod
    def _read_pdf(path: str) -> str:
        try:
            import pdfplumber
            with pdfplumber.open(path) as pdf:
                return "\n".join(
                    p.extract_text() or "" for p in pdf.pages)
        except ImportError:
            pass
        try:
            import pypdf
            reader = pypdf.PdfReader(path)
            return "\n".join(
                page.extract_text() or "" for page in reader.pages)
        except ImportError:
            pass
        raise ImportError("请安装 pdfplumber 或 pypdf：pip install pdfplumber")

    @staticmethod
    def _read_docx(path: str) -> str:
        try:
            import docx
            doc = docx.Document(path)
            return "\n".join(p.text for p in doc.paragraphs)
        except ImportError:
            raise ImportError("请安装 python-docx：pip install python-docx")

    def _paste_text(self):
        """弹出文本输入对话框"""
        dlg = PasteDialog(self.listbox.winfo_toplevel(), on_confirm=self._on_paste)
        dlg.grab_set()

    def _on_paste(self, name: str, text: str):
        def run():
            from core.knowledge import get_doc_store
            ds = get_doc_store()
            if ds.add_document(name, text):
                self.log_fn(f"📚 已导入文本: {name} ({len(text)} 字)", "green")
            else:
                self.log_fn(f"❌ 导入失败: {name}", "red")
            self._refresh_list()
        threading.Thread(target=run, daemon=True).start()

    def _delete_selected(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        raw  = self.listbox.get(sel[0])
        name = raw.strip().split("  (")[0].strip()
        if not messagebox.askyesno("确认删除", f"删除文档「{name}」？"):
            return
        from core.knowledge import get_doc_store
        ds = get_doc_store()
        if ds.remove_document(name):
            self.log_fn(f"🗑 已删除: {name}", "yellow")
        self._refresh_list()


# ══════════════════════════════════════════════════════════
#  粘贴文本对话框
# ══════════════════════════════════════════════════════════

class PasteDialog(tk.Toplevel):
    def __init__(self, parent, on_confirm=None):
        super().__init__(parent)
        self.on_confirm = on_confirm
        self.title("粘贴文本")
        self.configure(bg=T["bg2"])
        self.resizable(True, True)
        self.geometry("520x420")
        self._build()

    def _build(self):
        wrap = tk.Frame(self, bg=T["bg2"], padx=12, pady=10)
        wrap.pack(fill="both", expand=True)

        lbl(wrap, "文档名称（用于在列表中识别）").pack(anchor="w")
        self.v_name = tk.StringVar(value="粘贴文档")
        tk.Entry(
            wrap, textvariable=self.v_name,
            bg=T["input"], fg=T["text"],
            insertbackground=T["blue"],
            relief="flat", font=("Consolas", 10), bd=4,
        ).pack(fill="x", pady=(2, 10))

        lbl(wrap, "文本内容").pack(anchor="w")
        self.text_area = scrolledtext.ScrolledText(
            wrap,
            bg=T["input"], fg=T["text"],
            insertbackground=T["blue"],
            relief="flat", font=("Microsoft YaHei UI", 9),
            bd=4, height=14,
        )
        self.text_area.pack(fill="both", expand=True, pady=(2, 10))

        bf = tk.Frame(wrap, bg=T["bg2"])
        bf.pack(fill="x")

        self.v_hint = tk.StringVar()
        tk.Label(bf, textvariable=self.v_hint,
                 bg=T["bg2"], fg=T["dim"],
                 font=("Microsoft YaHei UI", 8)).pack(side="left")

        btn(bf, "取消", self.destroy,
            bg=T["bg3"]).pack(side="right", padx=(4, 0))
        btn(bf, "✓ 确认导入", self._confirm,
            bg=T["green"], fg=T["bg"]).pack(side="right")

        # 字数统计
        self.text_area.bind("<KeyRelease>", self._update_count)

    def _update_count(self, _=None):
        n = len(self.text_area.get("1.0", tk.END).strip())
        self.v_hint.set(f"{n} 字")

    def _confirm(self):
        name = self.v_name.get().strip()
        text = self.text_area.get("1.0", tk.END).strip()
        if not name:
            messagebox.showwarning("提示", "请填写文档名称", parent=self)
            return
        if not text:
            messagebox.showwarning("提示", "内容不能为空", parent=self)
            return
        self.destroy()
        if self.on_confirm:
            self.on_confirm(name, text)
