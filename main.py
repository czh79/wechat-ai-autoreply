"""
微信 AI 自动回复助手 — 程序入口
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    import tkinter as tk
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    root = tk.Tk()
    root.withdraw()

    from ui.app import App
    root.deiconify()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
