"""检索结果格式化输出"""

from typing import Optional

from .core import search


def search_formatted(query: str, top_k: int = None, user_id: Optional[int] = None) -> str:
    """
    搜索并返回格式化文本，可直接注入 Agent 上下文。
    """
    items = search(query, top_k, user_id)
    if not items:
        return "（知识库中未找到相关内容）"

    lines = ["## 知识库检索结果\n"]
    for i, item in enumerate(items, 1):
        source = item["metadata"].get("source_path") or item["metadata"].get("source", "未知")
        lines.append(f"### 结果 {i}（相关度: {item['score']:.0%} | 来源: {source}）")
        lines.append(item["text"])
        lines.append("")

    return "\n".join(lines)
