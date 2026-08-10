"""文件记忆（File Memory）— 面向文件的专门记忆处理。

设计目标（用户方案）：
1. 扫描   记忆目录最多扫描 200 个文件；递归扫描；每文件只读前 30 行（文件固定格式，前 30 行即元数据）。
          不调用 LLM，成本极低（只有几千行文本）。
2. 摘要   扫描完成后把所有记忆元数据列成一个清单：类型标签 + 文件名 + 最后修改时间。
3. 选择   把用户 query 和记忆清单一起发送，用**小模型**选择最相关的 5 条。
          - "宁缺毋滥"：若无关可以返回空列表。
          - 不要选择正在使用的工具的说明文档，可以选择它们的已知问题和注意事项。
          - 后校验：逐一检查文件是否真的存在（确定性代码兜底，不信任模型输出）。
4. 注入   将选中的记忆注入，每条记忆有 4kb 空间，如果超过则截断 + 指针（指向文件路径便于按需读取）。
          注入预算：单条上限 4kb，单轮上限 20kb，会话累计上限 60kb（超过就停止注入）。
5. 过期警告 每条记忆如果超过 2 天附加过期提醒（不是实时状态）；基于这条记忆做决策之前先验证代码的实际状态。

本模块不依赖 agents.*（避免循环导入）；LLM 选择调用复用 app/llm/client.py 的 OpenAI 兼容链路。
"""

import json
import logging
import os
import re
import sqlite3
from datetime import datetime
from typing import Callable, Optional

from .db import DB_PATH, _get_db, init_memory_db

logger = logging.getLogger(__name__)

# ── 配置常量 ──────────────────────────────────────────────────────

MAX_SCAN_FILES = 200          # 扫描上限
HEADER_LINES = 30             # 每文件只读前 30 行（元数据）
MAX_SELECT = 5                # 最多选择条数
ITEM_BUDGET_BYTES = 4 * 1024      # 单条 4kb
ROUND_BUDGET_BYTES = 20 * 1024    # 单轮 20kb
SESSION_BUDGET_BYTES = 60 * 1024  # 会话累计 60kb
STALE_DAYS = 2                # 过期阈值（天）

_IGNORE_DIRS = {
    "node_modules", ".git", "dist", "build", "__pycache__",
    ".next", ".venv", "venv", "coverage", ".cache", ".pytest_cache",
}
_IGNORE_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".pdf",
    ".zip", ".gz", ".tar", ".mp4", ".mp3", ".wav", ".woff", ".woff2",
    ".ico", ".pyc", ".db", ".sqlite", ".sqlite3", ".exe", ".dll", ".so",
}
_META_KEYS = ("type", "tag", "kind", "category")

_SELECT_SYSTEM_PROMPT = """你是记忆检索器。给定用户的问题和一个记忆文件清单，选择与问题最相关的文件。

清单每行格式: [类型标签] 文件名 (最后修改时间)
文件名是完整的相对路径。

规则：
1. 最多选择 {max_select} 个文件。
2. 宁缺毋滥：如果清单与问题无关，返回空数组 []，不要硬选。
3. 不要选择"正在使用的工具的说明文档"（如 README、使用说明、安装指南），
   可以选择它们的"已知问题 / 注意事项 / 排障"类文件。
4. 优先选择最近修改的、类型标签与问题领域匹配的文件。

只输出 JSON 数组，元素为完整文件名，不要输出任何解释或其他文字。"""

_POINTER_SUFFIX = "\n…(内容已截断，如需完整内容请读取该文件路径)"
_STALE_WARNING_TEMPLATE = (
    "⚠ 过期提醒：该记忆文件已超过 {days} 天未修改，可能已过期。\n"
    "基于此记忆做决策前，请先验证代码/文件的实际状态，勿直接采信。"
)


# ── 会话注入预算（持久化到 memory.db）────────────────────────────

_SESSION_USAGE_TABLE = """
CREATE TABLE IF NOT EXISTS file_memory_usage (
    session_id     TEXT PRIMARY KEY,
    injected_bytes INTEGER NOT NULL DEFAULT 0,
    updated_at     TEXT DEFAULT (datetime('now'))
);
"""


def _ensure_usage_table():
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(_SESSION_USAGE_TABLE)
        conn.commit()
    finally:
        conn.close()


def get_session_usage(session_id: str) -> int:
    """读取某会话已累计注入的字节数。"""
    _ensure_usage_table()
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute(
            "SELECT injected_bytes FROM file_memory_usage WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return row[0] if row else 0
    finally:
        conn.close()


def add_session_usage(session_id: str, bytes_injected: int):
    """累加会话注入字节数。"""
    _ensure_usage_table()
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            """INSERT INTO file_memory_usage (session_id, injected_bytes, updated_at)
               VALUES (?, ?, datetime('now'))
               ON CONFLICT(session_id) DO UPDATE SET
                 injected_bytes = injected_bytes + excluded.injected_bytes,
                 updated_at = datetime('now')""",
            (session_id, bytes_injected),
        )
        conn.commit()
    finally:
        conn.close()


# ── 1. 扫描 ──────────────────────────────────────────────────────

def _is_ignored(path: str, rel_path: str) -> bool:
    ext = os.path.splitext(path)[1].lower()
    if ext in _IGNORE_EXTS:
        return True
    parts = rel_path.split(os.sep)
    return any(p in _IGNORE_DIRS for p in parts)


def _read_header(path: str, max_lines: int = HEADER_LINES) -> str:
    """只读前 max_lines 行（固定格式：前 30 行即元数据），成本极低。"""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fp:
            lines = []
            for _ in range(max_lines):
                line = fp.readline()
                if not line:
                    break
                lines.append(line.rstrip("\n"))
            return "\n".join(lines)
    except OSError as e:
        logger.warning("读取文件头部失败 %s: %s", path, e)
        return ""


def _extract_type(header_text: str, rel_path: str) -> str:
    """从头部元数据（type/tag/kind/category）提取类型标签；失败则按目录推断。"""
    for key in _META_KEYS:
        m = re.search(rf"^\s*{key}\s*[:：]\s*(\S.+)$", header_text, re.M | re.I)
        if m:
            return m.group(1).strip()
    parts = rel_path.split(os.sep)
    if len(parts) > 1:
        return parts[0]
    return "file"


def scan_memory_files(root: str, limit: int = MAX_SCAN_FILES) -> list[dict]:
    """递归扫描记忆目录，最多 limit 个文件，每文件只读前 30 行。不调用 LLM。"""
    if not root or not os.path.isdir(root):
        return []
    found: list[dict] = []
    root = os.path.realpath(root)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _IGNORE_DIRS]
        for name in filenames:
            if len(found) >= limit:
                break
            abs_path = os.path.join(dirpath, name)
            rel_path = os.path.relpath(abs_path, root)
            if _is_ignored(abs_path, rel_path):
                continue
            header_text = _read_header(abs_path)
            if not header_text.strip():
                continue
            try:
                mtime = datetime.fromtimestamp(os.path.getmtime(abs_path))
            except OSError:
                mtime = None
            found.append({
                "path": abs_path,
                "rel_path": rel_path,
                "name": name,
                "mtime": mtime,
                "type": _extract_type(header_text, rel_path),
                "header_text": header_text,
            })
        if len(found) >= limit:
            break
    # 最近修改的优先
    found.sort(key=lambda f: f["mtime"] or datetime.min, reverse=True)
    return found[:limit]


# ── 2. 摘要：元数据清单 ──────────────────────────────────────────

def build_listing(files: list[dict]) -> str:
    """把所有记忆元数据列成清单：类型标签 + 文件名 + 最后修改时间。"""
    lines = []
    for f in files:
        mtime = f["mtime"].strftime("%Y-%m-%d %H:%M") if f["mtime"] else "unknown"
        lines.append(f"[{f['type']}] {f['rel_path']} ({mtime})")
    return "\n".join(lines)


# ── 3. 选择：小模型 + 确定性后校验 ───────────────────────────────

def _chat(prompt: str, user_content: str, api_key: str, model: str) -> tuple[str, dict]:
    """OpenAI 兼容 chat/completions 调用，返回 (content, usage)。"""
    import urllib.request
    from ..llm.client import get_llm_config, resolve_api_key, build_chat_request
    _, base_url, model_name = get_llm_config(model)
    api_key = resolve_api_key(api_key)
    req = build_chat_request(base_url, api_key, {
        "model": model_name,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.0,
        "max_tokens": 300,
        "stream": False,
    })
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read())
    content = data["choices"][0]["message"]["content"]
    usage = data.get("usage") or {}
    return content, {
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "total_tokens": usage.get("total_tokens", 0),
    }


def _parse_json_list(text: str) -> list:
    """容错解析 JSON 数组；提取 ```json 块或第一个 [...]。"""
    text = text.strip()
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return [str(x) for x in data if isinstance(x, (str, int))]
    except json.JSONDecodeError:
        pass
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if m:
        try:
            data = json.loads(m.group(1).strip())
            if isinstance(data, list):
                return [str(x) for x in data if isinstance(x, (str, int))]
        except json.JSONDecodeError:
            pass
    start, end = text.find("["), text.rfind("]")
    if start != -1 and end > start:
        try:
            data = json.loads(text[start:end + 1])
            if isinstance(data, list):
                return [str(x) for x in data if isinstance(x, (str, int))]
        except json.JSONDecodeError:
            pass
    return []


def _post_validate(selected: list[str], files_by_rel: dict[str, dict],
                   root: str) -> list[dict]:
    """确定性后校验：只保留真实存在且属于扫描结果的文件（不信任模型路径）。"""
    ok: list[dict] = []
    for name in selected:
        rel = name.strip().lstrip("/")
        f = files_by_rel.get(rel)
        if f is None:
            # 兜底：按磁盘实存校验
            abs_candidate = os.path.realpath(os.path.join(root, rel))
            if not os.path.isfile(abs_candidate) or os.path.commonpath([root, abs_candidate]) != root:
                logger.warning("文件记忆后校验剔除不存在文件: %s", name)
                continue
            f = {
                "path": abs_candidate,
                "rel_path": rel,
                "name": os.path.basename(abs_candidate),
                "mtime": None,
                "type": "file",
                "header_text": _read_header(abs_candidate),
            }
        ok.append(f)
    return ok[:MAX_SELECT]


def select_relevant(
    query: str,
    files: list[dict],
    api_key: str,
    model: str,
    root: str = "",
    on_usage: Optional[Callable[[dict], None]] = None,
) -> tuple[list[dict], dict]:
    """小模型选择最相关记忆 + 后校验。返回 (选中文件列表, stats)。

    - 宁缺毋滥：模型可返回空数组。
    - 后校验：逐一确认文件真实存在（确定性兜底）。
    """
    if not files:
        return [], {"scanned": 0, "selected": 0, "usage": None}
    listing = build_listing(files)
    user_prompt = f"## 用户问题\n{query}\n\n## 记忆清单\n{listing}\n\n请选择最相关的文件。"
    raw, usage = _chat(
        _SELECT_SYSTEM_PROMPT.format(max_select=MAX_SELECT),
        user_prompt,
        api_key,
        model,
    )
    if on_usage:
        try:
            on_usage(usage)
        except Exception:
            logger.warning("记录 memory 选择 usage 失败", exc_info=True)
    names = _parse_json_list(raw)
    files_by_rel = {f["rel_path"]: f for f in files}
    selected = _post_validate(names, files_by_rel, root)
    return selected, {"scanned": len(files), "selected": len(selected), "usage": usage}


# ── 4. 注入：预算控制 + 截断指针 ─────────────────────────────────

def check_stale(mtime: Optional[datetime]) -> Optional[str]:
    """超过 STALE_DAYS 天未修改 → 返回过期警告文本；否则 None。"""
    if not mtime:
        return None
    days = (datetime.now() - mtime).days
    if days > STALE_DAYS:
        return _STALE_WARNING_TEMPLATE.format(days=days)
    return None


def load_memory_content(f: dict, item_budget: int = ITEM_BUDGET_BYTES) -> str:
    """读取单条记忆（头部 + 尽可能多的正文），超预算截断 + 指针。"""
    header = f.get("header_text") or _read_header(f["path"])
    body = ""
    if len(header.encode("utf-8", "replace")) < item_budget:
        try:
            with open(f["path"], "r", encoding="utf-8", errors="replace") as fp:
                body = fp.read()
        except OSError:
            body = ""
    content = header
    if body:
        content += "\n" + body
    if len(content.encode("utf-8", "replace")) > item_budget:
        budget = max(item_budget - len(_POINTER_SUFFIX.encode("utf-8")), 256)
        content = content.encode("utf-8", "replace")[:budget].decode("utf-8", "replace")
        content += _POINTER_SUFFIX
    return content


def build_file_memory_context(
    query: str,
    root: str,
    api_key: str,
    model: str,
    session_id: str = "",
    on_usage: Optional[Callable[[dict], None]] = None,
) -> tuple[str, dict]:
    """顶层入口：扫描 → 选择 → 注入（带单轮/会话预算 + 过期警告）。

    返回 (注入文本, stats)。若无需注入返回 ("", stats)。
    """
    stats = {
        "root": root,
        "scanned": 0,
        "listing_len": 0,
        "selected": [],
        "injected_bytes": 0,
        "round_bytes": 0,
        "session_bytes": 0,
        "stale": [],
        "exhausted": False,
        "usage": None,
    }
    files = scan_memory_files(root)
    stats["scanned"] = len(files)
    stats["listing_len"] = len(build_listing(files))
    if not files:
        return "", stats

    selected, sel_stats = select_relevant(query, files, api_key, model, root, on_usage)
    stats["usage"] = sel_stats.get("usage")
    stats["selected"] = [f["rel_path"] for f in selected]
    if not selected:
        return "", stats

    session_used = get_session_usage(session_id) if session_id else 0
    round_used = 0
    parts: list[str] = []
    for f in selected:
        if round_used >= ROUND_BUDGET_BYTES:
            stats["exhausted"] = True
            break
        stale = check_stale(f.get("mtime"))
        content = load_memory_content(f, ITEM_BUDGET_BYTES)
        block = f"## 记忆: {f['rel_path']}\n"
        if stale:
            block += stale + "\n\n"
            stats["stale"].append(f["rel_path"])
        block += content
        block_bytes = len(block.encode("utf-8", "replace"))

        # 单轮 + 会话双重预算
        if round_used + block_bytes > ROUND_BUDGET_BYTES:
            stats["exhausted"] = True
            break
        if session_id and session_used + block_bytes > SESSION_BUDGET_BYTES:
            stats["exhausted"] = True
            break

        parts.append(block)
        round_used += block_bytes
        session_used += block_bytes
        stats["injected_bytes"] += block_bytes

    if session_id and stats["injected_bytes"] > 0:
        add_session_usage(session_id, stats["injected_bytes"])
    stats["round_bytes"] = round_used
    stats["session_bytes"] = session_used

    if not parts:
        return "", stats
    injected = "\n\n".join(parts)
    header = (
        f"## 文件记忆（File Memory）\n"
        f"以下是从记忆目录检索到的相关文件记忆（已按预算注入，每条 ≤{ITEM_BUDGET_BYTES // 1024}kb）。\n"
        f"若含过期提醒，使用前请先验证文件实际状态。\n\n"
    )
    return header + injected, stats


__all__ = [
    "MAX_SCAN_FILES", "HEADER_LINES", "MAX_SELECT",
    "ITEM_BUDGET_BYTES", "ROUND_BUDGET_BYTES", "SESSION_BUDGET_BYTES", "STALE_DAYS",
    "scan_memory_files", "build_listing", "select_relevant",
    "check_stale", "load_memory_content", "build_file_memory_context",
    "get_session_usage", "add_session_usage",
]
