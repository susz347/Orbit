"""Builder 工作区 git worktree 隔离。

- 每次 loop 在独立 worktree 运行 Builder，失败即弃，不污染主分支。
- 成功时把 worktree 的改动合并回主分支。
- 仅当 project_dir 是 git 仓库时启用；否则回退到直接落盘。
"""

import logging
import os
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

WORKTREE_DIRNAME = ".orbit-worktrees"


def _git(cmd: list[str], cwd: str, timeout: int = 30, check: bool = False) -> subprocess.CompletedProcess:
    """执行 git 命令。不使用 shell（安全规则 #2）。"""
    return subprocess.run(["git", "-C", cwd] + cmd, capture_output=True, text=True, timeout=timeout, shell=False,
                          check=check)


def is_git_repo(project_dir: str) -> bool:
    if not project_dir:
        return False
    try:
        res = _git(["rev-parse", "--is-inside-work-tree"], cwd=project_dir, timeout=5)
        return res.returncode == 0 and res.stdout.strip() == "true"
    except Exception:
        return False


def get_main_branch(project_dir: str) -> str:
    """获取默认分支名（main/master），否则返回当前分支。"""
    try:
        res = _git(["symbolic-ref", "--short", "HEAD"], cwd=project_dir, timeout=5)
        if res.returncode == 0:
            return res.stdout.strip() or "main"
    except Exception:
        pass
    return "main"


class Worktree:
    """一次 loop 的 worktree 上下文。"""

    def __init__(self, project_dir: str, loop_id: int, branch: Optional[str] = None):
        self.project_dir = os.path.realpath(project_dir)
        self.loop_id = loop_id
        self.branch = branch or f"orbit-loop-{loop_id}-{uuid.uuid4().hex[:8]}"
        self.worktree_path: Optional[str] = None
        self.merged = False

    def create(self) -> str:
        """基于主分支创建 worktree。返回 worktree 目录。"""
        base = Path(self.project_dir)
        wt_root = base.parent / WORKTREE_DIRNAME
        wt_root.mkdir(parents=True, exist_ok=True)
        wt_path = wt_root / f"loop-{self.loop_id}-{uuid.uuid4().hex[:8]}"
        wt_path.mkdir(parents=True, exist_ok=True)

        main = get_main_branch(self.project_dir)
        # 先创建临时分支
        _git(["branch", self.branch], cwd=self.project_dir, check=False)
        res = _git(["worktree", "add", "-B", self.branch, str(wt_path), main], cwd=self.project_dir,
                   timeout=30)
        if res.returncode != 0:
            # 回退：清理并抛错
            shutil.rmtree(wt_path, ignore_errors=True)
            _git(["branch", "-D", self.branch], cwd=self.project_dir, check=False)
            raise RuntimeError(f"创建 worktree 失败: {res.stderr}")

        self.worktree_path = str(wt_path)
        return self.worktree_path

    def commit(self, message: str = "Orbit agent loop changes"):
        """把 worktree 中的改动提交到临时分支。"""
        if not self.worktree_path:
            return
        try:
            _git(["add", "-A"], cwd=self.worktree_path, check=False)
            # 没有改动则跳过
            status = _git(["status", "--porcelain"], cwd=self.worktree_path, timeout=10)
            if not status.stdout.strip():
                logger.info("Worktree %s 无改动，跳过 commit", self.worktree_path)
                return
            _git(["commit", "-m", message, "--no-verify"], cwd=self.worktree_path, timeout=30)
        except Exception as e:
            logger.warning("Worktree commit 失败: %s", e)

    def apply_to_main(self, message: str = "Orbit agent loop changes") -> dict:
        """合并 worktree 分支到主分支。返回 {ok, output}。"""
        if not self.worktree_path:
            return {"ok": False, "output": "worktree 未创建"}
        main = get_main_branch(self.project_dir)
        try:
            self.commit(message)
            # 切回主仓库目录合并
            merge = _git(["merge", "--no-ff", "-m", message, self.branch], cwd=self.project_dir, timeout=60)
            self.merged = merge.returncode == 0
            return {"ok": merge.returncode == 0, "output": merge.stdout + merge.stderr}
        except Exception as e:
            return {"ok": False, "output": str(e)}

    def discard(self):
        """删除 worktree 与临时分支，失败不抛错。"""
        if not self.worktree_path or not os.path.exists(self.worktree_path):
            self.worktree_path = None
            return
        try:
            _git(["worktree", "remove", "--force", self.worktree_path], cwd=self.project_dir, timeout=30)
        except Exception as e:
            logger.warning("移除 worktree 失败: %s", e)
            shutil.rmtree(self.worktree_path, ignore_errors=True)
        try:
            _git(["branch", "-D", self.branch], cwd=self.project_dir, timeout=30)
        except Exception as e:
            logger.warning("删除临时分支失败: %s", e)
        self.worktree_path = None

    def __enter__(self):
        if is_git_repo(self.project_dir):
            self.create()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None and self.worktree_path and is_git_repo(self.project_dir):
            self.apply_to_main()
        self.discard()
        return False


def get_worktree_path(project_dir: str, loop_id: int) -> str:
    """返回 Builder 应写入的目录：git 仓库则返回 worktree，否则原目录。"""
    if not is_git_repo(project_dir):
        return project_dir
    wt = Worktree(project_dir, loop_id)
    return wt.create()
