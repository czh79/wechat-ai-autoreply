"""
core/ocr.py — OCR 识别引擎
优先级：PaddleOCR → RapidOCR → Windows WinRT → Tesseract → EasyOCR
"""
import re
import subprocess
import os
from core.deps import (IS_WINDOWS, HAS_PIL, HAS_TESS, HAS_EASYOCR, HAS_NP,
                        HAS_PADDLE, HAS_RAPID,
                        Image, ImageOps, pytesseract, easyocr, np,
                        _PaddleOCR, _RapidOCR)


class OCR:
    _easy_reader      = None
    _easy_init_failed = False
    _paddle_reader    = None
    _paddle_init_failed = False
    _rapid_reader     = None
    _rapid_init_failed  = False

    # ── 主入口 ────────────────────────────────────────────
    @staticmethod
    def extract(pil_img) -> str:
        """
        从 PIL 图像提取文字，返回清洗前的原始文本。
        优先级：PaddleOCR → RapidOCR → Windows WinRT → Tesseract → EasyOCR
        PaddleOCR/RapidOCR 直接接受 numpy array，无需预处理；
        后三个引擎使用预处理图像提升识别率。
        """
        if pil_img is None:
            return ""

        # PaddleOCR / RapidOCR：直接用原图（内部已做预处理）
        for fn in (OCR._paddle_ocr, OCR._rapid_ocr):
            try:
                t = fn(pil_img)
                if t and t.strip():
                    return t.strip()
            except Exception:
                pass

        # 后备引擎：原图 + 预处理图各试一次
        for img in [pil_img, OCR._preprocess(pil_img)]:
            if img is None:
                continue
            for fn in (OCR._win_ocr, OCR._tesseract, OCR._easy_ocr):
                try:
                    t = fn(img)
                    if t and t.strip():
                        return t.strip()
                except Exception:
                    pass
        return ""

    # ── PaddleOCR ─────────────────────────────────────────
    @staticmethod
    def _paddle_ocr(img) -> str | None:
        """
        PaddleOCR 增强版：增加图像预处理 + 高精度参数
        显著提升微信聊天文字识别率
        """
        if not HAS_PADDLE or OCR._paddle_init_failed:
            return None
        try:
            if OCR._paddle_reader is None:
                print("[PaddleOCR] 首次初始化模型（约1-3秒）...", flush=True)
                OCR._paddle_reader = _PaddleOCR(
                    use_angle_cls=True,      # 开启角度校正（重要）
                    lang="ch",
                    show_log=False,
                    det_db_thresh=0.3,       # 检测阈值优化
                    det_db_box_thresh=0.5,
                    det_db_unclip_ratio=2.0,
                    use_gpu=False
                )

            # === 图像预处理增强（关键提升）===
            if HAS_NP:
                import numpy as _np
                import cv2
                
                arr = _np.array(img.convert("RGB"))
                
                # 1. 灰度 + 二值化（对微信白色背景文字特别有效）
                gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
                _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                
                # 2. 轻微膨胀，让文字更清晰
                kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
                binary = cv2.dilate(binary, kernel, iterations=1)
                
                # 转回3通道给PaddleOCR
                arr = cv2.cvtColor(binary, cv2.COLOR_GRAY2RGB)
            else:
                arr = _np.array(img)

            # 执行 OCR
            result = OCR._paddle_reader.ocr(arr, cls=False)
            if not result or not result[0]:
                return None

            # 按 Y 坐标从上到下排序
            blocks = [item for item in result[0] if item and item[1] and item[1][0].strip()]
            blocks.sort(key=lambda b: b[0][0][1])

            # 同一气泡内行合并
            MERGE_Y_GAP = 12
            merged = []
            for b in blocks:
                text = b[1][0].strip()
                top_y = b[0][0][1]
                if merged and (top_y - merged[-1][0]) < MERGE_Y_GAP:
                    merged[-1] = (merged[-1][0], merged[-1][1] + " " + text)
                else:
                    merged.append((top_y, text))

            lines = [m[1] for m in merged if m[1]]
            return "\n".join(lines) if lines else None

        except Exception as e:
            import traceback
            print(f"[PaddleOCR] 错误: {e}", flush=True)
            # 只打印一次详细错误
            if not OCR._paddle_init_failed:
                print(traceback.format_exc(), flush=True)
            OCR._paddle_init_failed = True
            return None
    # ── RapidOCR ──────────────────────────────────────────
    @staticmethod
    def _rapid_ocr(img) -> str | None:
        """
        RapidOCR：ONNX 封装的 PaddleOCR 模型，无需 paddlepaddle 框架。
        体积更小，适合打包发布。准确率略低于完整 PaddleOCR。
        安装：pip install rapidocr-onnxruntime
        """
        if not HAS_RAPID or OCR._rapid_init_failed:
            return None
        try:
            if OCR._rapid_reader is None:
                OCR._rapid_reader = _RapidOCR()
            if HAS_NP:
                import numpy as _np
                arr = _np.array(img)
            else:
                import tempfile, os as _os
                tmp = _os.path.join(tempfile.gettempdir(), "_wx_rapid.png")
                img.save(tmp)
                arr = tmp
            result, _ = OCR._rapid_reader(arr)
            if not result:
                return None
            # RapidOCR item 格式: [坐标列表, 文字, 置信度]
            # 坐标列表: [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]，取左上角 y1 排序
            blocks = [item for item in result if item and len(item) > 1 and str(item[1]).strip()]
            try:
                blocks.sort(key=lambda b: b[0][0][1])
            except Exception:
                pass  # 坐标格式异常时跳过排序
            MERGE_Y_GAP = 12
            merged = []
            for b in blocks:
                text = str(b[1]).strip()
                try:
                    top_y = b[0][0][1]
                except Exception:
                    top_y = 9999
                if merged and (top_y - merged[-1][0]) < MERGE_Y_GAP:
                    merged[-1] = (merged[-1][0], merged[-1][1] + " " + text)
                else:
                    merged.append((top_y, text))
            lines = [m[1] for m in merged if m[1]]
            return "\n".join(lines) if lines else None
        except Exception:
            OCR._rapid_init_failed = True
            return None

    @staticmethod
    def _preprocess(img):
        """灰度 + 自动对比度 + 2x 放大，提升 OCR 准确率"""
        if img is None or not HAS_PIL:
            return None
        try:
            g = ImageOps.grayscale(img)
            g = ImageOps.autocontrast(g)
            w, h = g.size
            if w < 1200:
                g = g.resize((w * 2, h * 2), Image.Resampling.LANCZOS)
            return g
        except Exception:
            return None

    # ── Windows WinRT OCR ─────────────────────────────────
    @staticmethod
    def _win_ocr(img) -> str | None:
        if not IS_WINDOWS or not HAS_PIL:
            return None
        import tempfile
        try:
            tmp = os.path.join(tempfile.gettempdir(), "_wx5_ocr.png")
            img.save(tmp)
            ps = (
                "Add-Type -AN System.Runtime.WindowsRuntime;"
                "$null=[Windows.Storage.StorageFile,Windows.Storage,ContentType=WindowsRuntime];"
                "$null=[Windows.Media.Ocr.OcrEngine,Windows.Foundation,ContentType=WindowsRuntime];"
                "function AW($t,$rt){"
                "$m=([System.WindowsRuntimeSystemExtensions].GetMethods()"
                "|?{$_.Name-eq'AsTask'-and$_.GetParameters().Count-eq 1-and!$_.IsGenericMethod})[0];"
                "$g=$m.MakeGenericMethod($rt);$n=$g.Invoke($null,@($t));$n.Wait(-1)|Out-Null;$n.Result};"
                f"$e=[Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages();"
                f"$f=AW([Windows.Storage.StorageFile]::GetFileFromPathAsync('{tmp}'))"
                "([Windows.Storage.StorageFile]);"
                "$s=AW($f.OpenReadAsync())"
                "([Windows.Storage.Streams.IRandomAccessStreamWithContentType]);"
                "$d=AW([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($s))"
                "([Windows.Graphics.Imaging.BitmapDecoder]);"
                "$bmp=AW($d.GetSoftwareBitmapAsync())"
                "([Windows.Graphics.Imaging.SoftwareBitmap]);"
                "(AW($e.RecognizeAsync($bmp))([Windows.Media.Ocr.OcrResult])).Text"
            )
            r = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
                capture_output=True, text=True, timeout=15, encoding="utf-8",
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout.strip()
        except Exception:
            pass
        return None

    # ── Tesseract ─────────────────────────────────────────
    @staticmethod
    def _tesseract(img) -> str | None:
        if not HAS_TESS:
            return None
        try:
            return pytesseract.image_to_string(img, lang="chi_sim+eng")
        except Exception:
            return None

    # ── EasyOCR ───────────────────────────────────────────
    @staticmethod
    def _easy_ocr(img) -> str | None:
        if not HAS_EASYOCR or not HAS_NP or OCR._easy_init_failed:
            return None
        try:
            if OCR._easy_reader is None:
                OCR._easy_reader = easyocr.Reader(
                    ["ch_sim", "en"], gpu=False, verbose=False
                )
            arr = np.array(img)
            res = OCR._easy_reader.readtext(arr, detail=0, paragraph=False)
            if res:
                return "\n".join(str(x).strip() for x in res if str(x).strip())
        except Exception:
            OCR._easy_init_failed = True
        return None

    # ── 文本清洗 ─────────────────────────────────────────
    _SKIP_RE = [
        # ── 时间戳（全变体）────────────────────────────────
        r"^\d{1,2}[:;.]\d{2}([:;.]\d{2})?$",   # 17:57  19.31  19;22  17:57:06
        r"^\d{3,4}$",                             # 1926=19:26  190=19:0x
        # ── 日期标签 ────────────────────────────────────
        r"^(昨天|今天|星期[一二三四五六日天]|\d{4}[年/-]\d{1,2}[月/-]\d{1,2}[日]?)$",
        r"^.{0,4}(昨天|今天|阼天|星期[一二三四五六日天])\d{2,6}[;:.，。]?\d{0,2}$",
        # ── 纯数字 ────────────────────────────────────────
        r"^\d{1,2}$",
        # ── 系统气泡 ───────────────────────────────────────
        r"^\[.{1,15}\]$",
        r"^<.{1,15}>$",
        # ── 分割线 ─────────────────────────────────────────
        r"^[-─━═~～]{2,}$",
        # ── 纯空白 ─────────────────────────────────────────
        r"^[\s\u3000]+$",
        # ── 纯符号/数字噪声 ────────────────────────────────
        r"^[^\u4e00-\u9fa5A-Za-z]{1,6}$",
        # ── 纯字母短词（≤5字符全大写或全小写，无汉字）─────
        # 覆盖：nwr / AAU / Og / ARO / Clein / decode 等噪声单词
        r"^[A-Za-z]{1,5}$",
        # ── 含数字的字母混合短串（OCR噪声）────────────────
        # 覆盖：C3I1 / L0ca / ARO1 / 11h / 1209a
        r"^[A-Za-z0-9]{1,6}$",
        # ── 字母+汉字混合的单字噪声 ───────────────────────
        r"^[A-Za-z0-9][\u4e00-\u9fa5]$",
        r"^[\u4e00-\u9fa5][A-Za-z0-9]$",
        # ── 单字母/数字 + 标点残片 ────────────────────────
        r"^[A-Za-z0-9][;:.,。，!！?？~～]{1,2}$",
        r"^\d{2,4}[a-zA-Z]$",
        # ── 发件人后缀冒号噪声 ────────────────────────────
        r"^[\u4e00-\u9fa5][：:；;]$",
        # ── 纯标点/符号残片 ────────────────────────────────
        r"^[\W\d\s\u3000-\u303F\uFF00-\uFFEF]{1,6}$",
        # ── 微信 UI 元素 ───────────────────────────────────
        r"^(表情|语音|视频通话?|转账|红包|文件|位置|名片)$",
        r"^\d*条消息$",
        r"^查看\d+条",
        # ── 技术/代码噪声行（截到了编辑器/终端内容）──────
        # 覆盖：decode / decode brte / Ord3 i Dosition 2: inlralid...
        r"^(decode|encode|import|class|def |return|print|from |Total War|THREE)",
        r"inlralid|continuation bpte|readert|getlead",
        # 混杂数字+字母+空格的乱码行：字母数字混排且含多个空格（如 Ord3 i Dosition 2）
        # 规则：行内有数字、有字母、有空格，且中文字符比例<10%
        # 用 clean_chat 里的后置逻辑处理，此处只加显式关键词
        r"^(Ord|Dosi|inval|contin|positio|byte|error|exception|traceback)",
        # ── 明显非对话的工具提示行（含"支持""正则""回复所有"）
        r"支持正则|回复所有人|墨空则|则回复",
        # ── 含 ! 感叹号的纯英文短行（get ! / Last }）────────
        r"^[A-Za-z0-9\s\{\}!]{1,12}$",
    ]

    _SKIP_KW = frozenset({
        # 微信系统提示
        "发送", "搜索",
        "你已撤回一条消息", "对方撤回了一条消息",
        "你已撤回", "对方撤回",
        "查看更多消息", "以下为新消息", "以下为引用消息",
        "条消息", "查看更多",
        # 常驻 UI 元素
        "文件传输助手", "腾讯新闻", "服务通知",
        "更多", "表情", "语音", "视频", "转账",
        # 底部输入区域
        "发送文件", "语音输入",
    })

    # 常见汉字集：用于生僻字比例计算
    _COMMON_CHARS = set(
        "的一是了我不人在他有这个上们来到时大地为子中你说生国年着就那和要她出也得里后"
        "自以会家可下而过天去能对小多然于心学么之都好看起发当没成只如事把还用第样道想"
        "让将高问它但并从两点什么没也都不是地说很会吃喝玩乐聊约见面啊嗯哦哈嘿呀哟呢吧"
        "啦哼呵急慢才有趣想玩你觉得好吃午李张王赵刘陈杨黄周吴徐孙朱马胡郭林何高梁郑"
        "今明昨早下晚中现等请帮找给发送照图视频语音知道可以吗能回复消息联系时间方便"
        "一二三四五六七八九十百千万亿零喜欢开心一起出来谢谢随便随时工作朋友家人生活"
        "天气北京上海深圳广州成都杭州武汉南京西安觉得感觉认识聊天重庆男女天津哈尔滨"
        "永远跟着我屁虫真假爱恨情缘命运缘分幸福快乐悲伤痛苦思念牵挂"
        "漂亮帅气可爱温柔体贴善良勤劳努力聪明厉害棒强大弱小胆小勇敢"
        "约吃饭逛街看电影唱歌喝酒打球游泳旅游购物散步跑步健身"
        "心情状态表情动作语气疑问感叹命令请求建议邀请拒绝同意"
        # 口语/方言常用字
        "啥咋呗嘛嗝咯嘞唉哇噢哎啰咱俺您"
        "整挺蛮超贼老特别真假对嗯呢"
        "滚走来去搞弄干玩混说讲问答找给帮带拿放做"
        # 常用量词/虚词补充
        "些种类样位只头条张块元分角"
        "被把让叫给向往从于在以和与及"
    )

    # 常见词组：命中任一则认为行内有真实语义，不视为乱码
    _VALID_BIGRAMS = re.compile(
        r"(什么|慢慢|有趣|有意|来才|才有|更有|味道|想去|去玩|不想|想吃|好玩|觉得|你好|"
        r"今天|明天|昨天|可以|知道|喜欢|没有|一起|开心|出来|见面|吃饭|照片|发图|发张|"
        r"等等|不行|好的|嗯嗯|哈哈|谢谢|不客气|随便|随时|方便|时间|联系|回复|消息|"
        r"重庆|北京|上海|深圳|好吗|想你|想我|在吗|在干|干嘛|怎么|为什么|有空|没空|"
        r"工作|朋友|感觉|认识|聊天|天气|好看|漂亮|可爱|帅气|有意思|高兴|不错|挺好|"
        r"永远|跟着|跟我|跟你|屁虫|跟屁|约吗|出去|散步|逛街|看电影|唱歌|喝酒|"
        r"真的|假的|爱你|喜欢你|想你|思念|牵挂|幸福|快乐|开心|悲伤|心情|"
        r"加油|努力|厉害|棒棒|很棒|太棒|不错|挺好|真好|真棒|好厉害)"
    )

    @classmethod
    def _is_garbled(cls, text: str) -> bool:
        """
        乱码双重判断：
        1. 生僻字（不在常用字集）占汉字比例 > 35%
        2. 且行内不含任何常见词组
        两个条件同时满足才判为乱码。

        豁免规则：
        - 1字：直接豁免（单字过于极端，靠 _SKIP_RE 处理）
        - 2字：仅当两字都是常用字时豁免（避免误杀"好的""在吗"），
                含生僻字的2字（如"刁道"）不豁免，参与乱码判断
        - 3字+：全部参与判断
        """
        if len(text) <= 1:
            return False

        chinese_chars = [c for c in text if '\u4e00' <= c <= '\u9fa5']
        if not chinese_chars:
            return False

        rare_chars = [c for c in chinese_chars if c not in cls._COMMON_CHARS]
        rare_ratio = len(rare_chars) / len(chinese_chars)

        # 2字特殊处理：无生僻字则豁免，有生僻字则参与判断
        if len(text) == 2 and not rare_chars:
            return False

        if rare_ratio <= 0.35:
            return False
        if cls._VALID_BIGRAMS.search(text):
            return False
        return True

    # 只含ASCII字母的词：超过此长度才允许通过（避免短英文噪声）
    # 6 以上的英文单词（如 "decode" 还是会被 _SKIP_RE 显式过滤）
    # 这里作为补丁：纯英文行超过10字符才放行
    _MIN_PURE_EN_LEN = 10
    @classmethod
    def clean_chat(cls, raw: str) -> list[str]:
        """
        最终强力版：尽量保持原始长句完整，不轻易被逗号截断
        """
        if not raw:
            return []

        # 原始行
        original_lines = [line.strip() for line in raw.splitlines() if line.strip()]
        if not original_lines:
            return []

        result = []
        current_para = []

        for line in original_lines:
            if not line or len(line) < 2:
                continue

            # 过滤系统消息
            if any(kw in line for kw in ["撤回了一条消息", "你撤回", "对方撤回", "消息已撤回", "已送达", "系统消息"]):
                continue

            current_para.append(line)

            # === 核心调整：只有极长或明显句子结束时才强制合并 ===
            merged = " ".join(current_para)
            if len(merged) > 220 or any(c in line for c in "。！？…？！"):
                if current_para:
                    result.append(merged)
                    current_para = []
            # 短消息直接保留，不累计
            elif len(line) <= 40:
                if current_para and len(current_para) > 1:
                    result.append(" ".join(current_para[:-1]))
                result.append(line)
                current_para = []

        # 处理最后一段
        if current_para:
            result.append(" ".join(current_para))

        # 强力保底：从原始文本保留较长行（优先底部最新消息）
        if len(result) <= 6:
            backup = []
            for line in reversed(original_lines):
                cleaned = line.strip()
                if len(cleaned) >= 20 and not any(kw in cleaned for kw in ["撤回", "已送达", "系统"]):
                    backup.append(cleaned)
                    if len(backup) >= 10:
                        break
            backup.reverse()
            result = backup + result

        # 最终清洗
        seen = set()
        final = []
        for r in result:
            cleaned = re.sub(r"\s+", " ", r).strip()
            if cleaned and cleaned not in seen and len(cleaned) >= 8:   # 提高最小长度
                seen.add(cleaned)
                final.append(cleaned)

        return final[-15:]
    @staticmethod
    def clean_name(raw: str) -> str:
        """清洗联系人名称，去除干扰字符和尾部数字"""
        first = (raw or "").strip().splitlines()
        n = first[0] if first else ""
        n = re.sub(r"[\s\n\r]+", " ", n).strip()
        n = re.sub(r"\s*\d+\s*$", "", n).strip()
        n = re.sub(r"[^\u4e00-\u9fa5A-Za-z0-9_\-·\s]", "", n).strip()
        return n if 1 <= len(n) <= 20 else "未知"
