"""
core/capture.py — 屏幕截图工具
"""
from core.deps import IS_WINDOWS, HAS_PIL, HAS_W32, HAS_NP
from core.deps import ImageGrab, win32api, win32con, np


def grab(bbox: tuple):
    """
    截取指定屏幕区域，返回 PIL.Image 或 None。
    自动裁剪到虚拟屏幕范围内，防止负坐标或越界导致崩溃。
    """
    if not HAS_PIL:
        return None
    try:
        l, t, r, b = [int(v) for v in bbox]
        if IS_WINDOWS and HAS_W32:
            vx = win32api.GetSystemMetrics(win32con.SM_XVIRTUALSCREEN)
            vy = win32api.GetSystemMetrics(win32con.SM_YVIRTUALSCREEN)
            vw = win32api.GetSystemMetrics(win32con.SM_CXVIRTUALSCREEN)
            vh = win32api.GetSystemMetrics(win32con.SM_CYVIRTUALSCREEN)
            l = max(vx, l);  t = max(vy, t)
            r = min(vx+vw, r); b = min(vy+vh, b)
        if r <= l or b <= t:
            return None
        try:
            return ImageGrab.grab(bbox=(l, t, r, b), all_screens=True)
        except Exception:
            return ImageGrab.grab(bbox=(l, t, r, b))
    except Exception:
        return None


def save_debug(img, filename: str) -> str | None:
    """将 PIL 图像保存到当前目录，返回绝对路径或 None"""
    if img is None or not HAS_PIL:
        return None
    import os
    try:
        path = os.path.abspath(filename)
        img.save(path)
        return path
    except Exception:
        return None
