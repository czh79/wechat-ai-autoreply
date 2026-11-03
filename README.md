# 🤖 微信 AI 自动回复助手

> 不用 Hook、不碰协议：纯屏幕识别（截图 + 红点检测 + OCR）驱动的微信桌面端 AI 自动回复，支持多联系人独立上下文、知识库检索与本地大模型。

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey?logo=windows)](https://www.microsoft.com/windows)
[![LLM](https://img.shields.io/badge/LLM-Ollama%20%7C%20DeepSeek%20%7C%20Doubao-8b5cf6)](https://ollama.com/)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

**中文** | [English](#-english)

---

## 为什么用屏幕识别，而不是 Hook

微信自动回复的开源方案大多是 Hook 或协议逆向，代价是：账号风险高、微信一更新就失效、只能跑在特定版本上。

这个项目走 **RPA 路线**：像人一样看屏幕、点鼠标、敲键盘。

```
激活窗口 → 截图会话列表 → OpenCV 找红点 → 点进会话
        → OCR 读联系人名和最近几条消息 → 去重
        → LLM 生成回复 → 拟人化延迟 → 发送
```

好处是**不注入进程、不改协议、不依赖微信版本**；代价是必须保持窗口可见、依赖 OCR 准确率。这是一个诚实的工程权衡，不是银弹。

## 架构

```
main.py                 入口，启动 Tkinter 主窗口
├── core/               核心逻辑（无 UI 依赖，可单独测试）
│   ├── window.py       微信窗口定位 + 区域坐标
│   ├── capture.py      屏幕截图
│   ├── badge.py        OpenCV 红点检测
│   ├── ocr.py          OCR 引擎（WinRT / PaddleOCR / RapidOCR 三级回退）
│   ├── context.py      多联系人独立对话历史
│   ├── knowledge.py    知识库：TF-IDF 检索 + 话术 few-shot 注入
│   ├── ai.py           AI 后端（Ollama / DeepSeek / 豆包）
│   ├── sender.py       文本与图片发送、拟人化延迟
│   ├── patrol.py       轮巡模式
│   └── bot.py          主调度：红点模式 / 轮巡模式 / 值守模式
└── ui/                 界面层（Tkinter）
    ├── theme.py        配色与公共控件
    ├── panels.py       配置 / 角色 / 调试 / 状态面板
    ├── kb_panel.py     知识库管理
    └── app.py          主窗口
```

## 三种工作模式

| 模式 | 触发方式 | 适合 |
|---|---|---|
| **红点模式** | 检测未读红点 → 逐条处理 | 日常在线，响应及时 |
| **轮巡模式** | 从上到下扫描联系人列表 | 冷启动、批量触达 |
| **值守模式** | 固定间隔巡检指定会话 | 盯重点客户 |

## 技术细节

**OCR 三级回退** — 优先 Windows 内置 WinRT OCR（零依赖、够快）；装了 PaddleOCR 就用它（中文准确率最高）；再不行退 RapidOCR（约 30MB，无需 paddle 框架）。三者都没装也能跑，这是它能开箱即用的关键。

**多联系人上下文隔离** — `core/context.py` 为每个联系人维护独立的历史队列，取最近 3 条消息拼接后送入模型，去重 key 用最后一条，避免重复回复。

**图片发送走剪贴板位图** — 常见的坑是把文件路径字符串粘贴到输入框，微信只会收到一段路径文字。正确做法是用 `win32clipboard.SetClipboardData(CF_DIB, bmp_data)` 把位图直接写进剪贴板，Ctrl+V 后微信才识别为图片。

**拟人化节奏** — 发送前随机等待 3–6 秒，避免秒回带来的机器感。

## 快速开始

```bash
git clone https://github.com/czh79/wechat-ai-autoreply.git
cd wechat-ai-autoreply
pip install -r requirements.txt
```

**配置**

复制示例配置，填入你自己的密钥（**示例文件里没有任何真实密钥**）：

```bash
copy config.example.json wx_ai_config.json    # Windows
```

```json
{
  "backend": "ollama",
  "ollama_url": "http://localhost:11434",
  "ollama_model": "qwen2.5:1.5b",
  "deepseek_api_key": "",
  "persona": "你是一个简洁、礼貌、不说空话的助手。"
}
```

想全本地离线，装个 [Ollama](https://ollama.com/) 拉个模型即可，`backend` 保持 `ollama`：

```bash
ollama pull qwen2.5:1.5b
```

**运行**

```bash
python main.py
```

界面里先点「测试 OCR」确认能读到文字，再开「自动发送」。**第一次务必先用小号或自己的号试。**

## 环境要求

- Windows 10 / 11（依赖 `pywin32`、`pygetwindow`）
- 微信桌面版，窗口**不能被遮挡或最小化**
- 屏幕缩放建议 100%（125% 以上需要重调 `window.py` 里的坐标）

## ⚠️ 使用边界

自动化操作微信客户端**可能违反微信软件许可及服务协议**，账号存在被限制的风险。

本项目面向**个人学习与自有账号的效率辅助**：

- 不要用于群发营销、批量加好友、骚扰他人
- 不要用 AI 冒充真实身份骗取信任
- 涉及自动回复他人消息时，建议在签名或对话中表明自动化身份

作者不对使用者的账号风险与合规后果负责。请自行评估。

---

## 🇬🇧 English

> A screen-recognition-driven WeChat desktop auto-reply assistant: screenshot → red-badge detection → OCR → LLM reply. No process hooking, no protocol reverse-engineering.

Most WeChat automation projects hook the process or reverse the protocol — high account risk, breaks on every WeChat update. This one takes the RPA path: it looks at the screen, clicks, and types, exactly like a human would.

That trade-off is honest: no injection and version-independent, but the window must stay visible and OCR accuracy becomes your bottleneck.

### Architecture

`core/` is UI-independent and testable on its own — window locating, capture, badge detection, tiered OCR (WinRT → PaddleOCR → RapidOCR), per-contact context, TF-IDF knowledge retrieval, LLM backends (Ollama / DeepSeek / Doubao), and human-like sending delays. `ui/` is a Tkinter shell.

### Notable implementation details

- **Clipboard bitmap for images** — pasting a file *path* into the input box only sends path text; writing a DIB via `win32clipboard.SetClipboardData(CF_DIB, ...)` is what actually makes WeChat treat it as an image.
- **Per-contact context** — independent history queues, last 3 messages concatenated, deduplicated by the final message.
- **Three-tier OCR fallback** — runs with zero extra OCR packages installed, using Windows' built-in WinRT engine.

### Quick start

```bash
pip install -r requirements.txt
copy config.example.json wx_ai_config.json   # then fill in your own keys
python main.py
```

Requires Windows 10/11, WeChat desktop visible, 100% display scaling. Start with `auto_send: false` and verify OCR output first.

**No credentials are included in this repository.** `config.example.json` ships with empty key fields.

### ⚠️ Compliance

Automating the WeChat client may violate its terms of service and carries account-restriction risk. This project is intended for personal learning and assisting your own account — not for bulk marketing, mass friend requests, or impersonating a real person. Use at your own risk.

---

<div align="center">

技术实现上有参考价值的话，**点个 Star** ⭐

</div>
