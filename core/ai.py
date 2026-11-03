"""
core/ai.py — AI 回复引擎，支持 Ollama（本地）和 DeepSeek（云端）
集成知识库：每次回复时动态注入语义匹配的风格示例
"""
import json
import re
import urllib.request
import urllib.error

class AI:
    def __init__(self, cfg: dict):
        self.cfg = cfg

        # Responses API 多轮对话ID
        self._previous_response_id = None

        # 是否开启联网
        self.enable_web_search = cfg.get("doubao_web_search", True)

        # 是否开启思考
        self.enable_thinking = cfg.get("doubao_thinking", True)

    def reply(self, persona: str, history: list, user_msg: str) -> str:
        """
        生成回复：
          - kb_enabled=True 且有文档命中 → 业务客服模式（详细、忠实文档）
          - 否则 → 原有暧昧聊天模式（知识库直接命中 + few-shot 风格注入）
        """
        # ── 业务客服模式 ──────────────────────────────────
        if self.cfg.get("kb_enabled", False):
            doc_ctx = self._get_doc_context(user_msg)
            if doc_ctx:
                return self._reply_business(persona, history, user_msg, doc_ctx)

        # ── 聊天模式：优先知识库直接命中 ──────────────────
        direct = self._kb_direct_hit(user_msg)
        if direct:
            return direct

        # ── 聊天模式：AI + few-shot 风格注入 ──────────────
        enriched_persona = self._build_chat_persona(persona, user_msg)
        messages = (
            [{"role": "system", "content": enriched_persona}]
            + history
            + [{"role": "user", "content": user_msg}]
        )
        return self.clean_reply(self._call_llm(messages))

    # ── 业务文档检索 ──────────────────────────────────────
    def _get_doc_context(self, user_msg: str) -> str:
        """检索业务文档，返回拼接后的上下文，无结果返回空字符串"""
        try:
            from core.knowledge import get_doc_store
            ds = get_doc_store()
            if not ds.loaded:
                return ""
            hits = ds.search(user_msg, top_k=3)
            if not hits:
                return ""
            return "\n\n".join(
                f"[来源：{h['source']}]\n{h['text'].strip()}"
                for h in hits
            )
        except Exception:
            return ""

    # ── 业务客服回复 ──────────────────────────────────────
    def _reply_business(self, persona: str, history: list,
                        user_msg: str, doc_ctx: str) -> str:
        """
        业务模式：忠实于知识库文档内容，详细专业地回答。
        不使用暧昧话术，不限制字数，不要求装成女生。
        """
        rules = (
            "1. 严格依据上述知识库内容回答，不要编造或臆测\n"
            "2. 如知识库中有明确答案，直接给出；如没有，如实告知知识库中暂无相关信息\n"
            "3. 回答要清晰、完整、专业\n"
            "4. 可以适当组织语言，但不要偏离原文意思"
        )
        system = (
            ((persona + "\n\n") if persona.strip() else "")
            + "【业务知识库内容如下，请严格依据以下内容回答用户问题】\n"
            + doc_ctx
            + "\n\n【回答规范】\n"
            + rules
        )
        backend = self.cfg.get("backend", "ollama")

        if backend == "doubao":
            messages = [
                {"role": "system", "content": system},
                {"role": "user", "content": user_msg},
            ]
        else:
            messages = (
                [{"role": "system", "content": system}]
                + history
                + [{"role": "user", "content": user_msg}]
            )

        return self.clean_reply(self._call_llm(messages))

    # ── 聊天模式：构建 persona ────────────────────────────
    def _build_chat_persona(self, persona: str, user_msg: str) -> str:
        """原有暧昧聊天模式的 persona 构建，含 few-shot + 回复规范"""
        parts = [persona]
        try:
            from core.knowledge import get_kb
            kb = get_kb(self.cfg.get("kb_path", "know.json"))
            if kb.loaded:
                few_shot = kb.build_few_shot(user_msg, n_match=3, n_scene=2)
                if few_shot:
                    parts.append("\n\n" + few_shot)
        except Exception:
            pass

        rules = (
            "\n\n【回复规范】\n"
            "1. 日常聊天：回复简短自然（不超过25字），像真实在手机上发微信\n"
            "2. 知识性话题：如果对方谈论科学、知识、技术、历史等内容，请给出简要解释和见解，不要敷衍\n"
            "3. 可以用emoji，但不要堆砌，最多1个\n"
            "4. 语气要真实，有时候可以俏皮、有时候温柔、偶尔撒娇\n"
            "5. 不要暴露自己是AI，不要用'我理解你的感受'这类套话\n"
            "6. 如果对方分享有趣的知识或观点，要表现出兴趣并适当回应\n"
            "7. 回复要有人味，像个真实的女生在随手回消息"
        )
        parts.append(rules)
        return "".join(parts)

    def _call_llm(self, messages: list) -> str:
        backend = self.cfg.get("backend", "ollama")
        if backend == "ollama":
            return self._ollama(messages)
        elif backend == "deepseek":
            return self._deepseek(messages)
        elif backend == "doubao":
            return self._doubao(messages, enable_search=True)
        elif backend == "hybrid":
            return self._hybrid(messages)
        else:
            raise ValueError(f"未知后端: {backend}")

    # ── 知识库直接命中 ────────────────────────────────────
    def _kb_direct_hit(self, user_msg: str,
                       threshold: float = 0.85) -> str | None:
        """
        若 user_msg 与知识库某条的 a 字段相似度超过阈值，
        直接返回对应的 b（我方短回复），不走 AI。
        加入 ±20% 随机扰动防止每次一样。
        """
        try:
            from core.knowledge import get_kb, KnowledgeBase
            kb = get_kb(self.cfg.get("kb_path", "know.json"))
            if not kb.loaded:
                return None
            best = kb.find_best(user_msg, top_n=1)
            if not best:
                return None
            entry = best[0]
            sim = KnowledgeBase._sim(user_msg, entry.get("a", ""))
            if sim >= threshold:
                reply = entry.get("b", "")
                if reply:
                    return self.clean_reply(reply)
        except Exception:
            pass
        return None

    # ── 构建增强版 system prompt ──────────────────────────
    # ── 文本后处理 ────────────────────────────────────────
    @staticmethod
    def clean_reply(text: str) -> str:
        """
        清洗 AI 输出：
        1. 去掉动作/表情描述标记：
             [xxx]  (xxx)  *xxx*  【xxx】  （xxx）
           只过滤括号内是纯描述性文字（非链接、非数字）的情况
        2. 含"AI"（大小写均算）的整句删除
        3. 清理多余空行
        4. 如果过滤后为空，返回随机兜底话术
        """
        import random
        fallbacks = ["嗯嗯～", "好呀～", "知道啦", "哈哈", "好的", "了解～", "收到～", "明白啦"]
        
        if not text:
            return random.choice(fallbacks)

        # ── 步骤0：过滤豆包 seed 模型的思考/工具调用 token ──
        text = re.sub(r"<seed:[^>]*>", "", text)
        text = re.sub(r"<\[[A-Z_]+[^>]*\]>", "", text)
        text = re.sub(r"</?think[^>]*>", "", text)
        text = re.sub(r"<bbox>[^<]*</bbox>", "", text)
        text = re.sub(r"<[A-Za-z_]+<\d+>", "", text)

        # ── 步骤1：去掉动作/表情描述标记 ────────────────
        # 匹配 [内容] / 【内容】 / (内容) / （内容） / *内容*
        # 内容：不含换行，长度1~30字符，非纯数字/链接
        ACTION_PATTERNS = [
            r"\[([^\[\]\n]{1,30})\]",      # [xxx]
            r"【([^【】\n]{1,30})】",        # 【xxx】
            r"\*([^\*\n]{1,30})\*",         # *xxx*
            r"\(([^\(\)\n]{1,30})\)",       # (xxx)  —— 只过滤中文或描述性内容
            r"（([^（）\n]{1,30})）",        # （xxx）
        ]
        # 对括号类型，进一步判断：内容含中文或动词才过滤，避免误删 (1) 这种
        _CN_OR_ACTION = re.compile(r"[\u4e00-\u9fa5]|smile|laugh|nod|wink|blush|sigh|wave|cry|hug")

        for pat in ACTION_PATTERNS:
            def _replacer(m, p=pat):
                inner = m.group(1)
                # (xxx) / （xxx）：内容必须含中文或英文动作词才过滤
                if "(" in pat or "（" in pat:
                    if not _CN_OR_ACTION.search(inner):
                        return m.group(0)   # 不替换
                return ""
            text = re.sub(pat, _replacer, text)

        # ── 步骤2：含"AI"的整句删除 ──────────────────────
        # 句子分隔符：。！？…… ，, \n
        # 用句号/感叹/问号/换行切分，逐句检查
        sentences = re.split(r"(?<=[。！？\n])|(?<=\.\.\.)|(?<=…)", text)
        kept = []
        for s in sentences:
            # 匹配独立的 "AI"：前后是非字母数字字符（含中文、标点、行首行尾）
            if re.search(r"(?<![A-Za-z])AI(?![A-Za-z])", s, re.IGNORECASE):
                continue
            # 也丢弃含"人工智能"、"语言模型"、"大模型"的句子（暴露身份）
            if re.search(r"人工智能|语言模型|大模型|ChatGPT|claude|llm", s, re.IGNORECASE):
                continue
            kept.append(s)
        text = "".join(kept)

        # ── 步骤3：清理多余空白 ──────────────────────────
        text = re.sub(r"\n{2,}", "\n", text)   # 多空行→单空行
        text = re.sub(r"[ \t]{2,}", " ", text)  # 多空格→单空格
        text = text.strip()

        # ── 步骤4：兜底 ──────────────────────────────────
        if not text:
            return random.choice(fallbacks)

        return text

    # ── Ollama ────────────────────────────────────────────
    def _ollama(self, messages: list) -> str:
        url = self.cfg.get("ollama_url", "http://localhost:11434") + "/api/chat"
        payload = {
            "model":    self.cfg.get("ollama_model", "qwen2.5:1.5b"),
            "messages": messages,
            "stream":   False,
            "options":  {"temperature": self.cfg.get("temperature", 0.85)},
        }
        res = self._post(url, payload)
        return res["message"]["content"].strip()

    # ── DeepSeek ──────────────────────────────────────────
    def _deepseek(self, messages: list) -> str:
        key = self.cfg.get("deepseek_api_key", "")
        if not key:
            raise ValueError("未设置 DeepSeek API Key")
        payload = {
            "model":       self.cfg.get("deepseek_model", "deepseek-chat"),
            "messages":    messages,
            "temperature": self.cfg.get("temperature", 0.85),
            "max_tokens":  self.cfg.get("max_tokens", 300),
        }

        res = self._post(
            "https://api.deepseek.com/chat/completions",
            payload,
            headers={"Authorization": f"Bearer {key}"},
        )
        return res["choices"][0]["message"]["content"].strip()

    def _doubao(self, messages: list, enable_search: bool = True) -> str:
        """豆包 Responses API（新版）"""

        key = self.cfg.get("doubao_api_key", "")
        if not key:
            raise ValueError("未设置豆包 API Key")

        # 一定使用 Model ID，不要用 ep-xxxx
        model = self.cfg.get(
            "doubao_model",
            "doubao-seed-2-1-pro-260628"
        )

        base_url = self.cfg.get(
            "doubao_base_url",
            "https://ark.cn-beijing.volces.com/api/v3"
        )

        # ===== system prompt =====
        instructions = ""

        # ===== 当前用户输入 =====
        user_input = ""

        for m in messages:
            if m["role"] == "system":
                instructions = m["content"]

            elif m["role"] == "user":
                user_input = m["content"]

        payload = {
            "model": model,

            "input": user_input,

            # system prompt
            "instructions": instructions,

            # 最大输出
            "max_output_tokens": self.cfg.get("max_tokens", 512),

            # 保存上下文
            "store": True,


            

            # 自动上下文管理
            "context_management": {
                "edits": [
                    {
                        "type": "clear_thinking",
                        "keep": {
                            "type": "thinking_turns",
                            "value": 0
                        }
                    }
                ]
            }
        }

        # ===== 多轮对话 =====

        if self._previous_response_id:

            payload["previous_response_id"] = self._previous_response_id

        # ===== Thinking =====
        # 强制禁用 thinking，避免返回中间过程，确保只返回最终回复
        payload["thinking"] = {
            "type": "disabled"
        }

        # ===== 联网 =====

        if enable_search and self.enable_web_search:

            payload["tool_choice"] = "auto"
            payload["tools"] = [
                {
                    "type": "web_search",
                    "limit": 5,
                    "max_keyword": 3
                }
            ]

        print("=" * 80)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        print("=" * 80)

        res = self._post(
            f"{base_url}/responses",
            payload,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json"
            }
        )

        print(json.dumps(res, ensure_ascii=False, indent=2))

        # 保存 response_id
        if "id" in res:
            self._previous_response_id = res["id"]

        # output_text（新版）
        if "output_text" in res:
            return res["output_text"].strip()

        # output（兼容）
        if "output" in res:

            for item in res["output"]:

                if item.get("type") != "message":
                    continue

                for c in item.get("content", []):

                    if "text" in c:
                        return c["text"].strip()

        # OpenAI兼容
        if "choices" in res:
            return res["choices"][0]["message"]["content"].strip()

        return str(res)

    # ── AI Router ─────────────────────────────────────────
    def _ai_router(self, user_msg: str) -> bool:
        """
        AI Router：使用轻量级 DeepSeek 模型判断是否需要联网搜索
        返回 True 表示需要联网，False 表示不需要
        
        判断标准：
        - 需要联网：新闻、天气、股价、实时信息、官网、价格、政策、AI 最新动态等时效性内容
        - 不需要联网：编程、知识问答、写作、翻译、数学、历史等稳定知识
        """
        router_prompt = """你是一个智能路由器，判断用户问题是否需要联网搜索。

判断标准：
- 需要联网（YES）：新闻、天气、股价、实时信息、官网、价格、政策、AI 最新动态、今日/最新的比赛结果等时效性内容
- 不需要联网（NO）：编程、知识问答、写作、翻译、数学、历史、概念解释等稳定知识

用户问题：{user_msg}

请只回答 YES 或 NO（必须大写，不要包含任何其他文字）："""

        try:
            # 轻量级路由判断配置
            key = self.cfg.get("deepseek_api_key", "")
            if not key:
                raise ValueError("未设置 DeepSeek API Key")
                
            messages = [
                {"role": "system", "content": "你是智能路由器，只回答 YES 或 NO。"},
                {"role": "user", "content": router_prompt.format(user_msg=user_msg)}
            ]
            
            # 使用轻量级配置进行路由判断
            payload = {
                "model":       self.cfg.get("deepseek_model", "deepseek-chat"),
                "messages":    messages,
                "temperature": 0.1,  # 使用低温度确保确定性
                "max_tokens":  10,   # 只需要 YES 或 NO，最多 10 tokens
            }

            res = self._post(
                "https://api.deepseek.com/chat/completions",
                payload,
                headers={"Authorization": f"Bearer {key}"},
            )
            
            result = res["choices"][0]["message"]["content"].strip().upper()
            
            print(f"[AI Router] 判断结果: {result}")
            
            # 简单的容错：如果结果包含 YES 就返回 True
            if "YES" in result:
                return True
            elif "NO" in result:
                return False
            else:
                # 无法判断时默认为不需要联网
                print(f"[AI Router] 无法解析结果: {result}，默认为 NO")
                return False
                
        except Exception as e:
            # Router 失败时默认为不需要联网，避免影响服务稳定性
            print(f"[AI Router] 路由判断失败: {e}，默认为 NO")
            return False

    # ── 混合模式 ─────────────────────────────────────────
    def _hybrid(self, messages: list) -> str:
        """
        混合模式 - 使用 AI Router 智能路由
        
        优先：
            时效性内容 -> 豆包(WebSearch)
            稳定知识 -> DeepSeek

        自动降级：
            豆包失败 -> DeepSeek
            DeepSeek失败 -> 豆包（无联网）
        """
        user_msg = ""

        for m in reversed(messages):
            if m["role"] == "user":
                user_msg = m["content"]
                break

        # 使用 AI Router 判断是否需要联网
        need_search = self._ai_router(user_msg)

        # ========= 需要联网 =========

        if need_search:

            print(f"[Hybrid] WebSearch -> Doubao")

            try:
                return self._doubao(
                    messages,
                    enable_search=True
                )

            except Exception as e:

                print(f"[Hybrid] 豆包失败：{e}")

                print("[Hybrid] 回退到 DeepSeek")

                return self._deepseek(messages)

        # ========= 普通聊天 =========

        print("[Hybrid] Chat -> DeepSeek")

        try:

            return self._deepseek(messages)

        except Exception as e:

            print(f"[Hybrid] DeepSeek失败：{e}")

            print("[Hybrid] 回退到豆包")

            return self._doubao(
                messages,
                enable_search=False
            )

    # ── HTTP ──────────────────────────────────────────────
    def _post(
        self,
        url: str,
        payload: dict,
        headers: dict | None = None,
        timeout: int = 60,
    ) -> dict:

        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        req = urllib.request.Request(
            url=url,
            data=data,
            method="POST"
        )

        req.add_header("Content-Type", "application/json")

        if headers:
            for k, v in headers.items():
                req.add_header(k, v)

        print("\n" + "=" * 90)
        print("HTTP Request")
        print("URL :", url)
        print("Payload:")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        print("=" * 90)

        try:

            with urllib.request.urlopen(req, timeout=timeout) as r:

                text = r.read().decode("utf-8")

                print("\n" + "=" * 90)
                print("HTTP Response")
                print(text)
                print("=" * 90)

                return json.loads(text)

        except urllib.error.HTTPError as e:

            body = e.read().decode("utf-8", errors="ignore")

            print("\n" + "=" * 90)
            print("HTTP ERROR")
            print("Status :", e.code)
            print("Reason :", e.reason)
            print("Body :")
            print(body)
            print("=" * 90)

            raise RuntimeError(f"HTTP {e.code}: {body}")

        except urllib.error.URLError as e:

            print("\n" + "=" * 90)
            print("NETWORK ERROR")
            print(e)
            print("=" * 90)

            raise RuntimeError(f"Network Error: {e}")

        except Exception as e:

            print("\n" + "=" * 90)
            print("UNKNOWN ERROR")
            print(e)
            print("=" * 90)

            raise
