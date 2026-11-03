"""
core/knowledge.py — 知识库引擎 v2

支持两种模式并存：
  1. 对话对模式（know.json）：原有暧昧/日常话术库，用于 few-shot 风格注入
  2. 文档模式（kb_docs/）：业务文档，用于客服场景的精准问答检索

文档模式工作流：
  上传文件/粘贴文本 → 分块 → TF-IDF 向量化 → 余弦相似度检索 → 注入 prompt
"""
import json
import os
import re
import math
import random
from collections import Counter


# ── 场景关键词映射 ────────────────────────────────────────
_SCENE_KW: dict[str, list[str]] = {
    "深夜":       ["睡了", "失眠", "晚安", "困", "夜", "还醒", "还没睡"],
    "关心":       ["照顾", "感冒", "累", "辛苦", "身体", "保重", "喝水", "吃饭", "休息"],
    "暧昧":       ["想你", "心动", "喜欢", "分心", "上瘾", "特别", "在意", "忘不掉"],
    "高段位暧昧": ["期待", "依赖", "靠近", "越来越", "舒服", "缘分", "默契", "理解", "吸引"],
    "成熟男人":   ["坚持", "成长", "顺其自然", "人生", "时间", "放弃", "努力", "未来"],
    "长期关系":   ["到家", "路上", "周末", "计划", "一起", "以后", "还有我", "并肩"],
    "幽默":       ["魔法", "超能力", "读心术", "练过", "控制"],
    "日常":       ["吃饭", "上班", "下班", "早餐", "午饭", "天气", "忙什么"],
    "约会":       ["餐厅", "电影", "咖啡", "散步", "出来", "周末"],
    "调情":       ["脑子里", "分心", "容易", "危险", "依赖"],
}


# ══════════════════════════════════════════════════════════
#  文档知识库（TF-IDF 检索）
# ══════════════════════════════════════════════════════════

def _tokenize(text: str) -> list[str]:
    """
    中文字符级 bigram + 英文词，用于 TF-IDF 检索。
    bigram 比整词切割召回率更高，适合无分词库的场景。
    例：「退款政策」→ ['退款', '款政', '政策']
    """
    tokens = []
    # 英文词
    tokens.extend(w.lower() for w in re.findall(r'[A-Za-z]{2,}', text))
    # 中文 bigram
    chinese = re.findall(r'[\u4e00-\u9fa5]', text)
    for i in range(len(chinese) - 1):
        tokens.append(chinese[i] + chinese[i+1])
    # 中文 unigram（补充单字匹配能力）
    tokens.extend(chinese)
    return tokens


class DocStore:
    """
    文档存储与 TF-IDF 检索。
    每个文档被切成 chunk_size 字的块，检索返回最相关的块。
    """
    CHUNK_SIZE  = 300   # 每块字数
    CHUNK_OVER  = 50    # 块间重叠字数（保持上下文连贯）

    def __init__(self, store_dir: str):
        self.store_dir  = store_dir
        os.makedirs(store_dir, exist_ok=True)
        self._chunks:   list[dict]        = []   # [{text, source, chunk_id}]
        self._tf:       list[dict]        = []   # 每块的词频
        self._idf:      dict[str, float]  = {}   # 逆文档频率
        self._loaded:   bool              = False
        self._load_all()

    # ── 加载全部文档 ─────────────────────────────────────
    def _load_all(self):
        self._chunks = []
        index_path = os.path.join(self.store_dir, "index.json")
        if not os.path.exists(index_path):
            return
        try:
            with open(index_path, "r", encoding="utf-8") as f:
                index = json.load(f)
            for doc in index.get("docs", []):
                txt_path = os.path.join(self.store_dir, doc["file"])
                if os.path.exists(txt_path):
                    with open(txt_path, "r", encoding="utf-8") as f:
                        text = f.read()
                    chunks = self._split(text, doc["name"])
                    self._chunks.extend(chunks)
            self._build_index()
            self._loaded = len(self._chunks) > 0
        except Exception as e:
            print(f"⚠️ 文档知识库加载失败: {e}")

    def _split(self, text: str, source: str) -> list[dict]:
        """将文本切成带重叠的块"""
        text  = re.sub(r'\n{3,}', '\n\n', text.strip())
        step  = self.CHUNK_SIZE - self.CHUNK_OVER
        chunks = []
        i = 0
        while i < len(text):
            chunk_text = text[i: i + self.CHUNK_SIZE]
            if chunk_text.strip():
                chunks.append({
                    "text":     chunk_text,
                    "source":   source,
                    "chunk_id": len(chunks),
                })
            i += step
        return chunks

    def _build_index(self):
        """构建 TF-IDF 索引"""
        if not self._chunks:
            return
        N = len(self._chunks)
        self._tf = []
        df: dict[str, int] = {}
        for chunk in self._chunks:
            tokens = _tokenize(chunk["text"])
            freq   = Counter(tokens)
            total  = max(len(tokens), 1)
            tf     = {t: c / total for t, c in freq.items()}
            self._tf.append(tf)
            for t in freq:
                df[t] = df.get(t, 0) + 1
        self._idf = {
            t: math.log((N + 1) / (cnt + 1)) + 1
            for t, cnt in df.items()
        }

    def _vec(self, tokens: list[str]) -> dict[str, float]:
        freq  = Counter(tokens)
        total = max(len(tokens), 1)
        return {
            t: (c / total) * self._idf.get(t, 0)
            for t, c in freq.items()
        }

    @staticmethod
    def _cosine(a: dict, b: dict) -> float:
        keys  = set(a) & set(b)
        if not keys:
            return 0.0
        dot   = sum(a[k] * b[k] for k in keys)
        na    = math.sqrt(sum(v*v for v in a.values()))
        nb    = math.sqrt(sum(v*v for v in b.values()))
        return dot / (na * nb) if na * nb > 0 else 0.0

    # ── 检索 ─────────────────────────────────────────────
    def search(self, query: str, top_k: int = 3) -> list[dict]:
        """返回最相关的 top_k 个块，每项含 text/source/score"""
        if not self._chunks or not self._idf:
            return []
        q_tokens = _tokenize(query)
        if not q_tokens:
            return []
        q_vec = self._vec(q_tokens)
        scored = []
        for i, (chunk, tf) in enumerate(zip(self._chunks, self._tf)):
            chunk_vec = {t: tf.get(t, 0) * self._idf.get(t, 0) for t in tf}
            score     = self._cosine(q_vec, chunk_vec)
            if score > 0:
                scored.append((score, chunk))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            {**c, "score": s}
            for s, c in scored[:top_k]
        ]

    # ── 文档管理 ─────────────────────────────────────────
    def _get_index(self) -> dict:
        path = os.path.join(self.store_dir, "index.json")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"docs": []}

    def _save_index(self, index: dict):
        path = os.path.join(self.store_dir, "index.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, indent=2)

    def add_document(self, name: str, text: str) -> bool:
        """添加一份文档（文本内容），返回是否成功"""
        try:
            if not text.strip():
                return False
            index = self._get_index()
            # 检查同名文档，覆盖
            existing = [d for d in index["docs"] if d["name"] == name]
            safe_name = re.sub(r'[^\w\u4e00-\u9fa5.-]', '_', name)
            file_name = f"{safe_name}.txt"
            if existing:
                index["docs"] = [d for d in index["docs"] if d["name"] != name]
            index["docs"].append({"name": name, "file": file_name})
            txt_path = os.path.join(self.store_dir, file_name)
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(text)
            self._save_index(index)
            self._load_all()   # 重新加载索引
            return True
        except Exception as e:
            print(f"⚠️ 添加文档失败: {e}")
            return False

    def remove_document(self, name: str) -> bool:
        """删除一份文档"""
        try:
            index = self._get_index()
            doc   = next((d for d in index["docs"] if d["name"] == name), None)
            if not doc:
                return False
            txt_path = os.path.join(self.store_dir, doc["file"])
            if os.path.exists(txt_path):
                os.remove(txt_path)
            index["docs"] = [d for d in index["docs"] if d["name"] != name]
            self._save_index(index)
            self._load_all()
            return True
        except Exception as e:
            print(f"⚠️ 删除文档失败: {e}")
            return False

    def list_documents(self) -> list[dict]:
        """列出所有文档及其块数"""
        index = self._get_index()
        result = []
        chunk_counts = Counter(c["source"] for c in self._chunks)
        for doc in index.get("docs", []):
            result.append({
                "name":   doc["name"],
                "chunks": chunk_counts.get(doc["name"], 0),
            })
        return result

    @property
    def loaded(self) -> bool:
        return self._loaded

    @property
    def doc_count(self) -> int:
        return len(self._get_index().get("docs", []))

    @property
    def chunk_count(self) -> int:
        return len(self._chunks)


# ══════════════════════════════════════════════════════════
#  对话对知识库（原有逻辑，保持不变）
# ══════════════════════════════════════════════════════════

class KnowledgeBase:
    def __init__(self, path: str = "know.json"):
        self._entries: list[dict] = []
        self._by_scene: dict[str, list[dict]] = {}
        self._load(path)

    def _load(self, path: str):
        if not os.path.exists(path):
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            path = os.path.join(base, "know.json")
        if not os.path.exists(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = f.read()
            fixed = re.sub(r'\}\s*\n\s*\{', '},\n{', raw)
            stripped = fixed.strip()
            if not stripped.startswith('['):
                fixed = '[' + fixed + ']'
            entries = json.loads(fixed)
            self._entries = entries
            for e in entries:
                scene = e.get("scene", "日常")
                self._by_scene.setdefault(scene, []).append(e)
        except Exception as ex:
            print(f"⚠️ 对话知识库加载失败: {ex}")

    @property
    def loaded(self) -> bool:
        return len(self._entries) > 0

    def detect_scene(self, text: str) -> str:
        t = text.lower()
        scores: dict[str, int] = {}
        for scene, kws in _SCENE_KW.items():
            score = sum(1 for kw in kws if kw in t)
            if score:
                scores[scene] = score
        if not scores:
            import datetime
            h = datetime.datetime.now().hour
            return "深夜" if (22 <= h or h < 6) else "日常"
        return max(scores, key=scores.get)

    @staticmethod
    def _sim(a: str, b: str) -> float:
        sa, sb = set(a), set(b)
        if not sa and not sb:
            return 0.0
        return len(sa & sb) / len(sa | sb)

    def find_best(self, user_msg: str, top_n: int = 3) -> list[dict]:
        if not self._entries:
            return []
        scene = self.detect_scene(user_msg)
        pool  = self._by_scene.get(scene, []) + self._entries
        seen, candidates = set(), []
        for e in pool:
            if e["id"] not in seen:
                seen.add(e["id"])
                candidates.append(e)
        scored = []
        for e in candidates:
            s1 = self._sim(user_msg, e.get("a",  ""))
            s2 = self._sim(user_msg, e.get("a2", ""))
            scored.append((max(s1, s2), e))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in scored[:top_n]]

    def build_few_shot(self, user_msg: str,
                       n_match: int = 3, n_scene: int = 2) -> str:
        if not self._entries:
            return ""
        scene  = self.detect_scene(user_msg)
        best   = self.find_best(user_msg, top_n=n_match)
        pool   = [e for e in self._by_scene.get(scene, []) if e not in best]
        extra  = random.sample(pool, min(n_scene, len(pool)))
        all_ex = best + extra
        if not all_ex:
            return ""
        lines = ["【参考聊天风格示例，模仿语气但不要照抄】"]
        for e in all_ex:
            b_reply  = e.get("b", "")
            ta_said  = (e.get("a2", "") if self._sim(user_msg, e.get("a2",""))
                        > self._sim(user_msg, e.get("a","")) else e.get("a", ""))
            sc       = e.get("scene", "")
            lines.append(f"[{sc}] Ta说：「{ta_said}」→ 我说：「{b_reply}」")
        lines.append("（以上仅供风格参考，请结合实际对话内容自然回应，不要生搬硬套）")
        return "\n".join(lines)


# ══════════════════════════════════════════════════════════
#  统一入口
# ══════════════════════════════════════════════════════════

_kb_instance:   KnowledgeBase | None = None
_doc_instance:  DocStore       | None = None


def get_kb(path: str = "know.json") -> KnowledgeBase:
    global _kb_instance
    if _kb_instance is None:
        _kb_instance = KnowledgeBase(path)
    return _kb_instance


def get_doc_store(store_dir: str = "kb_docs") -> DocStore:
    global _doc_instance
    if _doc_instance is None:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        _doc_instance = DocStore(os.path.join(base, store_dir))
    return _doc_instance


def reload_doc_store():
    """UI 层上传/删除文档后调用，强制重新加载"""
    global _doc_instance
    if _doc_instance is not None:
        _doc_instance._load_all()
