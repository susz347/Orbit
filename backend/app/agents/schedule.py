"""Loop 定时触发器（Schedule）。

支持 cron 表达式（简化子集）设定循环触发时间，模式：
- L1 report：只读分析 + 更新 STATE，不修改代码。
- L2 action：需要用户确认后 Builder 才会落盘。

提供轻量级内存调度器（每分钟检查一次），不引入 APScheduler 等重依赖。
"""

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from . import db

logger = logging.getLogger(__name__)

_SCHEDULER_TASK: Optional[asyncio.Task] = None


@dataclass(frozen=True)
class CronExpr:
    minute: set[int]
    hour: set[int]
    day_of_month: set[int]
    month: set[int]
    day_of_week: set[int]

    @classmethod
    def parse(cls, expr: str) -> "CronExpr":
        """解析简化 cron：m h dom mon dow。"""
        parts = expr.strip().split()
        if len(parts) != 5:
            raise ValueError(f"不支持的 cron 表达式: {expr}（需要 5 段 m h dom mon dow）")
        return cls(
            minute=_parse_field(parts[0], 0, 59),
            hour=_parse_field(parts[1], 0, 23),
            day_of_month=_parse_field(parts[2], 1, 31),
            month=_parse_field(parts[3], 1, 12),
            day_of_week=_parse_field(parts[4], 0, 7),
        )


def _parse_field(field: str, min_v: int, max_v: int) -> set[int]:
    """解析 cron 字段：支持 *、数字、逗号列表、/step。"""
    if field == "*":
        return set(range(min_v, max_v + 1))
    out: set[int] = set()
    for part in field.split(","):
        part = part.strip()
        if not part:
            continue
        m = re.match(r"^(?P<start>\d+)(?:-(?P<end>\d+))?(?:/(?P<step>\d+))?$", part)
        if not m:
            raise ValueError(f"无效 cron 字段: {part}")
        start = int(m.group("start"))
        end = int(m.group("end") or start)
        step = int(m.group("step") or 1)
        for v in range(start, end + 1, step):
            if min_v <= v <= max_v:
                out.add(v)
            elif v == 7 and min_v == 0 and max_v == 7:
                # 周日 7 映射为 0
                out.add(0)
    return out


def _matches(cron: CronExpr, dt: datetime) -> bool:
    return (
        dt.minute in cron.minute
        and dt.hour in cron.hour
        and dt.day in cron.day_of_month
        and dt.month in cron.month
        and dt.weekday() in cron.day_of_week
    )


def compute_next_run(cron_expr: str, after: Optional[datetime] = None) -> Optional[str]:
    """计算下一次触发时间（ISO 字符串）。"""
    try:
        cron = CronExpr.parse(cron_expr)
    except ValueError as e:
        logger.warning("计算 next_run 失败: %s", e)
        return None
    now = after or datetime.now()
    # 从下一分钟开始扫描（最多 4 年）
    dt = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
    end = dt + timedelta(days=366 * 4)
    while dt < end:
        if _matches(cron, dt):
            return dt.isoformat()
        dt += timedelta(minutes=1)
    return None


def validate_cron(expr: str) -> bool:
    try:
        CronExpr.parse(expr)
        return True
    except ValueError:
        return False


async def _scheduler_loop(trigger_fn):
    """后台调度循环：每分钟检查一次待触发 schedule。"""
    while True:
        try:
            now = datetime.now().isoformat()
            due = db.get_due_schedules(now)
            for sch in due:
                try:
                    logger.info("Schedule %s triggered", sch["id"])
                    trigger_fn(sch)
                    next_run = compute_next_run(sch["cron_expr"])
                    db.update_schedule(
                        sch["id"],
                        last_run_at=now,
                        next_run_at=next_run,
                        updated_at=now,
                    )
                except Exception as e:
                    logger.exception("Schedule %s 触发失败: %s", sch["id"], e)
        except Exception as e:
            logger.exception("调度循环异常: %s", e)
        await asyncio.sleep(60)


def start_scheduler(trigger_fn):
    """启动后台调度器（幂等）。"""
    global _SCHEDULER_TASK
    if _SCHEDULER_TASK is not None and not _SCHEDULER_TASK.done():
        return
    _SCHEDULER_TASK = asyncio.create_task(_scheduler_loop(trigger_fn))
    logger.info("Loop schedule scheduler started")


def stop_scheduler():
    global _SCHEDULER_TASK
    if _SCHEDULER_TASK and not _SCHEDULER_TASK.done():
        _SCHEDULER_TASK.cancel()
        _SCHEDULER_TASK = None
