"""
core/deps.py — 依赖检测，统一在此 import 所有可选库
其他模块只需 from core.deps import HAS_PIL, HAS_CV2, ...
"""
import platform

IS_WINDOWS = platform.system() == "Windows"

# ── Pillow ────────────────────────────────────────────────
try:
    from PIL import Image, ImageGrab, ImageOps
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    Image = ImageGrab = ImageOps = None

# ── numpy ─────────────────────────────────────────────────
try:
    import numpy as np
    HAS_NP = True
except ImportError:
    HAS_NP = False
    np = None

# ── OpenCV ────────────────────────────────────────────────
try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False
    cv2 = None

# ── pyautogui ─────────────────────────────────────────────
try:
    import pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE    = 0.05
    HAS_AG = True
except ImportError:
    HAS_AG = False
    pyautogui = None

# ── pyperclip ─────────────────────────────────────────────
try:
    import pyperclip
    HAS_CLIP = True
except ImportError:
    HAS_CLIP = False
    pyperclip = None

# ── pygetwindow ───────────────────────────────────────────
try:
    import pygetwindow as gw
    HAS_GW = True
except ImportError:
    HAS_GW = False
    gw = None

# ── win32 ─────────────────────────────────────────────────
try:
    import win32gui, win32con, win32api
    HAS_W32 = True
except ImportError:
    HAS_W32 = False
    win32gui = win32con = win32api = None

# ── pytesseract ───────────────────────────────────────────
try:
    import pytesseract
    HAS_TESS = True
except ImportError:
    HAS_TESS = False
    pytesseract = None

# ── easyocr ───────────────────────────────────────────────
try:
    import easyocr
    HAS_EASYOCR = True
except ImportError:
    HAS_EASYOCR = False
    easyocr = None

ALL_DEPS = {
    "Pillow":         HAS_PIL,
    "numpy":          HAS_NP,
    "opencv-python":  HAS_CV2,
    "pyautogui":      HAS_AG,
    "pyperclip":      HAS_CLIP,
    "pygetwindow":    HAS_GW,
    "pywin32":        HAS_W32,
    "pytesseract":    HAS_TESS,
    "easyocr":        HAS_EASYOCR,
}

# ── PaddleOCR ─────────────────────────────────────────────
try:
    from paddleocr import PaddleOCR as _PaddleOCR
    HAS_PADDLE = True
except ImportError:
    HAS_PADDLE = False
    _PaddleOCR = None

# ── RapidOCR（轻量备选，ONNX 推理，无需 paddle 框架）────────
try:
    from rapidocr_onnxruntime import RapidOCR as _RapidOCR
    HAS_RAPID = True
except ImportError:
    HAS_RAPID = False
    _RapidOCR = None

# 更新 ALL_DEPS
ALL_DEPS.update({
    "paddleocr":             HAS_PADDLE,
    "rapidocr-onnxruntime":  HAS_RAPID,
})
