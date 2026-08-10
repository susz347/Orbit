"""File Memory（P6）单元测试：扫描 / 清单 / 选择后校验 / 过期警告 / 注入预算。"""

import json
import os
from datetime import datetime, timedelta

import pytest

from app.memory import file_memory as fm


def _write(tmp_path, rel, content, mtime=None):
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    if mtime:
        os.utime(p, (mtime.timestamp(), mtime.timestamp()))
    return p


class TestScan:
    def test_scans_headers_and_type(self, tmp_path):
        _write(tmp_path, "docs/config.md", "type: config\n# 配置说明\n")
        _write(tmp_path, "notes/known-issues.md", "tag: 注意事项\n# 已知问题\n")
        files = fm.scan_memory_files(str(tmp_path))
        by_rel = {f["rel_path"]: f for f in files}
        assert by_rel["docs/config.md"]["type"] == "config"
        assert by_rel["notes/known-issues.md"]["type"] == "注意事项"
        # 头部只读前 30 行（元数据被读取）
        assert "type: config" in by_rel["docs/config.md"]["header_text"]

    def test_ignores_dirs_and_exts(self, tmp_path):
        _write(tmp_path, "node_modules/a.js", "type: file\nx")
        _write(tmp_path, "dist/b.js", "type: file\nx")
        _write(tmp_path, "img.png", "type: file\nx")
        _write(tmp_path, "ok.md", "type: memo\nhello")
        files = fm.scan_memory_files(str(tmp_path))
        rels = [f["rel_path"] for f in files]
        assert rels == ["ok.md"]

    def test_caps_at_limit(self, tmp_path):
        for i in range(250):
            _write(tmp_path, f"m/{i}.md", f"type: memo\ncontent {i}")
        files = fm.scan_memory_files(str(tmp_path))
        assert len(files) <= fm.MAX_SCAN_FILES

    def test_fallback_type_from_dir(self, tmp_path):
        _write(tmp_path, "docs/foo.md", "# no meta header\n")
        files = fm.scan_memory_files(str(tmp_path))
        assert files[0]["type"] == "docs"


class TestListing:
    def test_listing_format(self, tmp_path):
        _write(tmp_path, "a.md", "type: memo\nhi")
        files = fm.scan_memory_files(str(tmp_path))
        listing = fm.build_listing(files)
        assert "[memo] a.md (" in listing
        assert "20" in listing  # 年份


class TestSelectValidation:
    def test_post_validate_drops_nonexistent(self, tmp_path):
        _write(tmp_path, "real.md", "type: memo\nhi")
        files = fm.scan_memory_files(str(tmp_path))
        files_by_rel = {f["rel_path"]: f for f in files}
        ok = fm._post_validate(["real.md", "fake.md", "../etc/passwd"], files_by_rel, str(tmp_path))
        rels = [f["rel_path"] for f in ok]
        assert rels == ["real.md"]  # fake 与越界路径被确定性剔除

    def test_select_relevant_none_selected(self, tmp_path, monkeypatch):
        _write(tmp_path, "a.md", "type: memo\nhi")
        monkeypatch.setattr(fm, "_chat", lambda *a, **k: ("[]", {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}))
        files = fm.scan_memory_files(str(tmp_path))
        selected, stats = fm.select_relevant("与记忆无关的问题", files, "sk-test", "deepseek-chat", str(tmp_path))
        assert selected == []
        assert stats["selected"] == 0


class TestStale:
    def test_stale_warning_returned(self):
        old = datetime.now() - timedelta(days=5)
        w = fm.check_stale(old)
        assert w is not None and "过期提醒" in w

    def test_fresh_no_warning(self):
        w = fm.check_stale(datetime.now())
        assert w is None

    def test_none_mtime_no_warning(self):
        assert fm.check_stale(None) is None


class TestInjectionBudget:
    def test_truncate_with_pointer(self, tmp_path):
        big = "type: memo\n" + "x" * 100_000
        p = _write(tmp_path, "big.md", big)
        f = {"path": str(p), "rel_path": "big.md", "header_text": "type: memo\n" + "x" * 100_000, "mtime": datetime.now()}
        content = fm.load_memory_content(f, item_budget=fm.ITEM_BUDGET_BYTES)
        assert len(content.encode("utf-8", "replace")) <= fm.ITEM_BUDGET_BYTES
        assert "内容已截断" in content

    def test_build_context_with_budget(self, tmp_path, monkeypatch):
        _write(tmp_path, "a.md", "type: memo\n" + "a" * 3000)
        _write(tmp_path, "b.md", "type: memo\n" + "b" * 3000)
        files = fm.scan_memory_files(str(tmp_path))
        selected = files[:2]
        sid = f"test-sess-{id(tmp_path)}"
        monkeypatch.setattr(fm, "select_relevant",
                            lambda q, fl, k, m, root="", on_usage=None: (selected, {"selected": 2, "usage": None}))
        ctx, stats = fm.build_file_memory_context("问题", str(tmp_path), "sk-test", "deepseek-chat", session_id=sid)
        assert "文件记忆" in ctx
        assert len(stats["selected"]) == 2
        assert stats["injected_bytes"] > 0
        # 会话预算持久化
        assert fm.get_session_usage(sid) == stats["injected_bytes"]

    def test_session_budget_exhausted(self, tmp_path, monkeypatch):
        _write(tmp_path, "a.md", "type: memo\n" + "a" * 3000)
        files = fm.scan_memory_files(str(tmp_path))
        monkeypatch.setattr(fm, "select_relevant",
                            lambda q, fl, k, m, root="", on_usage=None: (files, {"selected": 1, "usage": None}))
        fm.add_session_usage("exhaust-sess", fm.SESSION_BUDGET_BYTES - 1)
        _, stats = fm.build_file_memory_context("问题", str(tmp_path), "sk-test", "deepseek-chat", session_id="exhaust-sess")
        assert stats["exhausted"] is True
        assert stats["injected_bytes"] == 0
