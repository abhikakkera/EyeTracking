"""
src/tasks — structured eye-movement task protocols (v0.3).

⚠️ DISCLAIMER
This software is a research prototype for eye-tracking data collection.
It does not diagnose, treat, predict, or screen for Parkinson's disease or any
other medical condition. Clinical use would require validation, regulatory
review, and healthcare professional oversight.

Quick start:
    from src.tasks import make_task, TaskRunner
    from config import CONFIG

    task   = make_task("prosaccade", CONFIG)
    runner = TaskRunner(CONFIG)
    session = runner.run(camera, task)
"""
from __future__ import annotations

from config import AppConfig

from src.tasks.antisaccade_task import AntiSaccadeTask
from src.tasks.base_task import BaseTask
from src.tasks.gap_overlap_task import GapOverlapTask
from src.tasks.prosaccade_task import ProSaccadeTask
from src.tasks.smooth_pursuit_task import SmoothPursuitTask
from src.tasks.task_runner import TaskRunner
from src.tasks.task_schema import (
    PursuitTrialRecord,
    SaccadeTrialRecord,
    TaskContext,
    TaskPhase,
    TaskSession,
    TrialRecord,
)

__all__ = [
    "ProSaccadeTask",
    "AntiSaccadeTask",
    "GapOverlapTask",
    "SmoothPursuitTask",
    "BaseTask",
    "TaskRunner",
    "TaskContext",
    "TaskPhase",
    "TaskSession",
    "TrialRecord",
    "SaccadeTrialRecord",
    "PursuitTrialRecord",
    "make_task",
]

_TASK_REGISTRY = {
    "prosaccade":    ProSaccadeTask,
    "antisaccade":   AntiSaccadeTask,
    "gap_overlap":   GapOverlapTask,
    "smooth_pursuit": SmoothPursuitTask,
}


def make_task(name: str, config: AppConfig) -> BaseTask:
    """
    Instantiate a task by name string.

    Parameters
    ----------
    name   : "prosaccade" | "antisaccade" | "gap_overlap" | "smooth_pursuit"
    config : AppConfig (task parameters read from config.task)

    Returns
    -------
    Concrete BaseTask subclass instance.

    Raises
    ------
    ValueError if name is not recognised.
    """
    cls = _TASK_REGISTRY.get(name.lower())
    if cls is None:
        valid = ", ".join(sorted(_TASK_REGISTRY))
        raise ValueError(
            f"Unknown task name '{name}'. Valid options: {valid}"
        )
    return cls(config)
