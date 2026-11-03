"""
core/sender.py — 消息 & 图片发送

修复：发送图片改用剪贴板（win32clipboard）直接写入图像数据，
      而非把文件路径粘贴到输入框。
"""
import os
import time
import random
from core.deps import (IS_WINDOWS, HAS_AG, HAS_CLIP, HAS_W32,
                        pyautogui, pyperclip, win32con)


def random_delay(lo: float = 3.0, hi: float = 6.0):
    """回复前随机等待，模拟人类思考节奏"""
    d = random.uniform(lo, hi)
    time.sleep(d)


def send_text(wx_window, text: str, log_fn=None) -> bool:
    """
    发送文字消息：
      1. 激活微信
      2. 点击输入框聚焦
      3. pyperclip 复制 → Ctrl+V 粘贴
      4. Enter 发送
    """
    def _log(msg, tag="dim"):
        if log_fn:
            log_fn(msg, tag)

    if not HAS_AG:
        _log("缺少 pyautogui，无法发送", "red")
        return False

    wx_window.activate()
    time.sleep(0.3)

    ix, iy = wx_window.input_click_pos()
    pyautogui.click(ix, iy)
    time.sleep(0.25)

    if HAS_CLIP:
        pyperclip.copy(text)
        pyautogui.hotkey("ctrl", "v")
    else:
        pyautogui.typewrite(text, interval=0.04)

    time.sleep(0.2)
    pyautogui.press("enter")
    _log("     ✅ 文字已发送", "green")
    return True


def send_photo(wx_window, photo_path: str, log_fn=None) -> bool:
    """
    发送图片：
      用 win32clipboard 将图片以 CF_DIB 格式写入剪贴板，
      然后 Ctrl+V 粘贴到微信输入框发送。
      这样微信会识别为图片而非文件路径文字。

    若 win32clipboard 不可用，降级为文件拖入方案（pyautogui）。
    """
    def _log(msg, tag="dim"):
        if log_fn:
            log_fn(msg, tag)

    if not os.path.isfile(photo_path):
        _log(f"     图片不存在: {photo_path}", "red")
        return False

    wx_window.activate()
    time.sleep(0.3)

    # ── 方案A：win32clipboard 写入 CF_DIB ─────────────────
    if IS_WINDOWS and _try_clipboard_image(photo_path, _log):
        ix, iy = wx_window.input_click_pos()
        pyautogui.click(ix, iy)
        time.sleep(0.25)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.5)
        pyautogui.press("enter")
        _log(f"     ✅ 图片已发送（剪贴板）: {os.path.basename(photo_path)}", "green")
        return True

    # ── 方案B：截图区域拖拽文件（无 win32clipboard）─────────
    _log("     win32clipboard 不可用，尝试文件路径方式", "yellow")
    return _send_photo_fallback(wx_window, photo_path, _log)


# ── 内部实现 ──────────────────────────────────────────────

def _try_clipboard_image(photo_path: str, log_fn) -> bool:
    """
    用 win32clipboard + PIL 将图片写入剪贴板（CF_DIB 格式）。
    微信可以识别该格式并以图片发送。
    """
    try:
        import win32clipboard
        from PIL import Image
        import io

        img = Image.open(photo_path).convert("RGB")
        # 转 BMP 字节流（去掉 14 字节文件头，只保留 DIB 部分）
        buf = io.BytesIO()
        img.save(buf, format="BMP")
        bmp_data = buf.getvalue()[14:]

        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.CF_DIB, bmp_data)
        win32clipboard.CloseClipboard()
        return True

    except ImportError:
        log_fn("     win32clipboard 未安装，跳过", "dim")
    except Exception as e:
        log_fn(f"     剪贴板写图失败: {e}", "yellow")
    return False


def _send_photo_fallback(wx_window, photo_path: str, log_fn) -> bool:
    """
    降级方案：用微信「发送文件」快捷键打开文件对话框，
    粘贴路径后发送。
    """
    if not HAS_AG or not HAS_CLIP:
        log_fn("     缺少依赖，无法发送图片", "red")
        return False
    try:
        ix, iy = wx_window.input_click_pos()
        pyautogui.click(ix, iy)
        time.sleep(0.25)

        # Ctrl+Alt+F 在部分微信版本可打开文件选择器
        # 通用方案：直接把路径写入剪贴板，然后在文件对话框粘贴
        pyperclip.copy(photo_path)

        # 点击输入区右侧"+"按钮区域（粗略位置，用户可能需要手动调）
        lx, ly = wx_window.input_click_pos()
        pyautogui.click(lx + 250, ly)
        time.sleep(0.8)

        # 尝试粘贴路径（文件选择器中）
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.3)
        pyautogui.press("enter")
        time.sleep(0.5)
        pyautogui.press("enter")

        log_fn(f"     ✅ 图片路径已发送（降级）: {os.path.basename(photo_path)}", "yellow")
        return True
    except Exception as e:
        log_fn(f"     发送图片失败: {e}", "red")
        return False


# ── 图片库 ────────────────────────────────────────────────
PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}


def get_random_photo(photo_dir: str, log_fn=None) -> str | None:
    """从指定目录随机返回一张图片的绝对路径"""
    def _log(msg, tag="dim"):
        if log_fn:
            log_fn(msg, tag)

    if not os.path.isdir(photo_dir):
        _log(f"图片目录不存在: {photo_dir}", "red")
        return None
    files = [
        f for f in os.listdir(photo_dir)
        if os.path.splitext(f)[1].lower() in PHOTO_EXTS
    ]
    if not files:
        _log(f"图片目录为空: {photo_dir}", "red")
        return None
    return os.path.join(photo_dir, random.choice(files))
