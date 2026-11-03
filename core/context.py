"""
core/context.py — 每个联系人独立对话历史
"""


class Context:
    """
    以联系人姓名为 key，维护各自的对话 history。
    history 格式与 OpenAI / Ollama API 一致：
      [{"role": "user"|"assistant", "content": "..."}]
    """

    def __init__(self, max_turns: int = 12):
        self._store: dict[str, list] = {}
        self.max_turns = max_turns

    def get(self, name: str) -> list:
        return list(self._store.get(name, []))

    def add(self, name: str, role: str, content: str):
        if name not in self._store:
            self._store[name] = []
        self._store[name].append({"role": role, "content": content})
        # 保留最近 N 轮（每轮 = user + assistant）
        cap = self.max_turns * 2
        if len(self._store[name]) > cap:
            self._store[name] = self._store[name][-cap:]

    def clear(self, name: str | None = None):
        if name:
            self._store.pop(name, None)
        else:
            self._store.clear()

    def names(self) -> list[str]:
        return list(self._store.keys())

    def summary(self) -> dict[str, int]:
        """返回每个联系人的对话轮数"""
        return {n: len(v) // 2 for n, v in self._store.items()}
