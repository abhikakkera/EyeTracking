"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  DEFAULT_TASK_CONFIG,
  generateTrialPlan,
  totalRounds,
  type Condition,
  type Direction,
  type TrialPlanItem,
  type WebTaskConfig,
} from "@/lib/taskConfigs";
import { nowMs, pursuitTargetPosition } from "@/lib/taskTiming";
import type { TaskFrameContext, TaskType, WebEvent } from "@/lib/types";

const BG = "#fbfcfe";
const TARGET_COLOR = "#1b4fd1";
const FIXATION_COLOR = "#0b1320";

const DEFAULT_CTX: TaskFrameContext = {
  trial_id: "",
  trial_number: -1,
  task_phase: "waiting",
  target_visible: false,
  target_x: 0.5,
  target_y: 0.5,
  target_direction: "none",
  condition: "none",
  fixation_visible: false,
};

type Phase = "fixation" | "gap" | "target" | "iti";

interface Segment {
  start: number;
  end: number;
  phase: Phase;
  trialId: string;
  trialNumber: number;
  direction: Direction;
  condition: Condition;
  targetX: number;
  targetY: number;
  fixationVisible: boolean;
  targetVisible: boolean;
}

export interface TaskRunnerState {
  phase: string;
  trialNumber: number;
  totalRounds: number;
  running: boolean;
  done: boolean;
}

export interface UseTaskRunner {
  state: TaskRunnerState;
  getContext: () => TaskFrameContext;
  start: () => void;
  cancel: () => void;
}

export function useTaskRunner(args: {
  taskType: TaskType;
  canvasRef: React.RefObject<HTMLCanvasElement>;
  config?: Partial<WebTaskConfig>;
  onEvent: (ev: WebEvent) => void;
  onComplete: () => void;
}): UseTaskRunner {
  const { taskType, canvasRef, onEvent, onComplete } = args;
  const cfg: WebTaskConfig = { ...DEFAULT_TASK_CONFIG[taskType], ...args.config };

  const [state, setState] = useState<TaskRunnerState>({
    phase: "waiting",
    trialNumber: 0,
    totalRounds: totalRounds(taskType, cfg),
    running: false,
    done: false,
  });

  const rt = useRef({
    startMs: 0,
    raf: 0,
    plan: [] as TrialPlanItem[],
    segments: [] as Segment[],
    totalMs: 0,
    lastKey: "",
    lastCycle: -1,
    ctx: { ...DEFAULT_CTX } as TaskFrameContext,
    done: false,
  });

  const getContext = useCallback(() => rt.current.ctx, []);

  const emit = useCallback(
    (ev: Partial<WebEvent> & { type: string }) => {
      onEvent({ timestamp_ms: nowMs(), ...ev });
    },
    [onEvent],
  );

  // -------- Drawing --------
  const draw = useCallback((ctx2d: CanvasRenderingContext2D, c: TaskFrameContext) => {
    const cv = ctx2d.canvas;
    ctx2d.fillStyle = BG;
    ctx2d.fillRect(0, 0, cv.width, cv.height);
    const scale = cv.height / 720;

    if (c.fixation_visible) {
      const r = cfg.fixationSizePx * scale;
      const x = 0.5 * cv.width;
      const y = 0.5 * cv.height;
      ctx2d.fillStyle = FIXATION_COLOR;
      ctx2d.beginPath();
      ctx2d.arc(x, y, r, 0, Math.PI * 2);
      ctx2d.fill();
      ctx2d.strokeStyle = "#ffffff";
      ctx2d.lineWidth = 2;
      ctx2d.beginPath();
      ctx2d.arc(x, y, r * 0.45, 0, Math.PI * 2);
      ctx2d.stroke();
    }
    if (c.target_visible) {
      const r = cfg.targetSizePx * scale;
      const x = c.target_x * cv.width;
      const y = c.target_y * cv.height;
      ctx2d.fillStyle = TARGET_COLOR;
      ctx2d.beginPath();
      ctx2d.arc(x, y, r, 0, Math.PI * 2);
      ctx2d.fill();
    }
  }, [cfg.fixationSizePx, cfg.targetSizePx]);

  // -------- Schedule (saccade family) --------
  function buildSegments(plan: TrialPlanItem[]): Segment[] {
    const segs: Segment[] = [];
    let o = 0;
    const ecc = cfg.targetEccentricity;
    for (const t of plan) {
      const targetX = t.direction === "left" ? 0.5 - ecc : 0.5 + ecc;
      const base = {
        trialId: t.trialId,
        trialNumber: t.trialNumber,
        direction: t.direction,
        condition: t.condition,
        targetX,
        targetY: 0.5,
      };
      // fixation
      segs.push({ ...base, start: o, end: o + cfg.fixationMs, phase: "fixation",
        fixationVisible: true, targetVisible: false });
      o += cfg.fixationMs;
      // gap (gap condition only)
      if (t.condition === "gap") {
        segs.push({ ...base, start: o, end: o + cfg.gapMs, phase: "gap",
          fixationVisible: false, targetVisible: false });
        o += cfg.gapMs;
      }
      // target
      segs.push({ ...base, start: o, end: o + cfg.targetMs, phase: "target",
        fixationVisible: t.condition === "overlap", targetVisible: true });
      o += cfg.targetMs;
      // inter-trial
      segs.push({ ...base, start: o, end: o + cfg.itiMs, phase: "iti",
        fixationVisible: false, targetVisible: false });
      o += cfg.itiMs;
    }
    return segs;
  }

  // -------- Loop --------
  const tick = useCallback(() => {
    const r = rt.current;
    const canvas = canvasRef.current;
    const elapsed = nowMs() - r.startMs;

    if (taskType === "smooth_pursuit") {
      const periodMs = 1000 / Math.max(0.01, cfg.pursuitCyclesPerSec);
      const cycle = Math.min(cfg.pursuitCycles - 1, Math.floor(elapsed / periodMs));
      if (elapsed >= cfg.pursuitCycles * periodMs) {
        // finish
        const last = r.plan[r.plan.length - 1];
        if (last) emit({ type: "trial_ended", trial_id: last.trialId });
        finish();
        return;
      }
      if (cycle !== r.lastCycle) {
        if (r.lastCycle >= 0 && r.plan[r.lastCycle]) {
          emit({ type: "trial_ended", trial_id: r.plan[r.lastCycle].trialId });
        }
        const item = r.plan[cycle];
        emit({
          type: "trial_started", trial_id: item.trialId,
          trial_number: item.trialNumber, cycle_number: item.cycleNumber,
        });
        r.lastCycle = cycle;
        setState((s) => ({ ...s, phase: "target", trialNumber: cycle + 1 }));
      }
      const pos = pursuitTargetPosition(
        cfg.pursuitPattern, elapsed, cfg.pursuitCyclesPerSec, cfg.pursuitAmplitude,
      );
      const item = r.plan[cycle];
      r.ctx = {
        trial_id: item.trialId, trial_number: item.trialNumber,
        task_phase: "target", target_visible: true,
        target_x: pos.x, target_y: pos.y, target_direction: "none",
        condition: "none", fixation_visible: false,
      };
    } else {
      // saccade family
      const seg = r.segments.find((s) => elapsed >= s.start && elapsed < s.end);
      if (!seg) {
        if (elapsed >= r.totalMs) {
          finish();
          return;
        }
      } else {
        const key = `${seg.trialNumber}:${seg.phase}`;
        if (key !== r.lastKey) {
          r.lastKey = key;
          if (seg.phase === "fixation") {
            emit({ type: "trial_started", trial_id: seg.trialId, trial_number: seg.trialNumber,
              direction: seg.direction, condition: seg.condition });
            emit({ type: "fixation_shown", trial_id: seg.trialId });
          } else if (seg.phase === "gap") {
            emit({ type: "gap_started", trial_id: seg.trialId });
          } else if (seg.phase === "target") {
            emit({ type: "target_shown", trial_id: seg.trialId,
              target_x: seg.targetX, target_y: seg.targetY, direction: seg.direction });
          } else if (seg.phase === "iti") {
            emit({ type: "trial_ended", trial_id: seg.trialId });
          }
          setState((s) => ({ ...s, phase: seg.phase, trialNumber: seg.trialNumber }));
        }
        r.ctx = {
          trial_id: seg.trialId, trial_number: seg.trialNumber,
          task_phase: seg.phase, target_visible: seg.targetVisible,
          target_x: seg.targetX, target_y: seg.targetY,
          target_direction: seg.direction, condition: seg.condition,
          fixation_visible: seg.fixationVisible,
        };
      }
    }

    if (canvas) {
      const ctx2d = canvas.getContext("2d");
      if (ctx2d) draw(ctx2d, r.ctx);
    }
    if (!r.done) r.raf = requestAnimationFrame(tick);
  }, [taskType, cfg, canvasRef, draw, emit]);

  const finish = useCallback(() => {
    const r = rt.current;
    if (r.done) return;
    r.done = true;
    cancelAnimationFrame(r.raf);
    r.ctx = { ...DEFAULT_CTX, task_phase: "done" };
    emit({ type: "task_ended" });
    setState((s) => ({ ...s, running: false, done: true, phase: "done" }));
    onComplete();
  }, [emit, onComplete]);

  const start = useCallback(() => {
    const r = rt.current;
    const plan = generateTrialPlan(taskType, cfg);
    r.plan = plan;
    r.segments = taskType === "smooth_pursuit" ? [] : buildSegments(plan);
    r.totalMs =
      taskType === "smooth_pursuit"
        ? (cfg.pursuitCycles * 1000) / Math.max(0.01, cfg.pursuitCyclesPerSec)
        : (r.segments[r.segments.length - 1]?.end ?? 0);
    r.startMs = nowMs();
    r.lastKey = "";
    r.lastCycle = -1;
    r.done = false;
    emit({ type: "task_started", task_start_timestamp_ms: r.startMs });
    setState((s) => ({ ...s, running: true, done: false }));
    r.raf = requestAnimationFrame(tick);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [taskType, tick, emit]);

  const cancel = useCallback(() => {
    const r = rt.current;
    r.done = true;
    cancelAnimationFrame(r.raf);
    emit({ type: "cancelled" });
    setState((s) => ({ ...s, running: false }));
  }, [emit]);

  useEffect(() => () => cancelAnimationFrame(rt.current.raf), []);

  return { state, getContext, start, cancel };
}
