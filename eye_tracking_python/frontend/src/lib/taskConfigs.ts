// Task definitions + trial-plan generation for the in-browser runner.
// Pure functions (testable). Durations are in milliseconds.

import { shuffle, uid, type PursuitPattern } from "@/lib/taskTiming";
import type { TaskType } from "@/lib/types";

export interface WebTaskConfig {
  numTrials: number;
  fixationMs: number;
  targetMs: number;
  itiMs: number;
  responseWindowMs: number;
  gapMs: number;
  targetEccentricity: number; // fraction of half-width from center (0–0.5)
  targetSizePx: number;
  fixationSizePx: number;
  // smooth pursuit
  pursuitPattern: PursuitPattern;
  pursuitCyclesPerSec: number;
  pursuitAmplitude: number;
  pursuitCycles: number;
}

const BASE: WebTaskConfig = {
  numTrials: 12,
  fixationMs: 1000,
  targetMs: 1500,
  itiMs: 800,
  responseWindowMs: 1500,
  gapMs: 200,
  targetEccentricity: 0.35,
  targetSizePx: 22,
  fixationSizePx: 14,
  pursuitPattern: "horizontal",
  pursuitCyclesPerSec: 0.25,
  pursuitAmplitude: 0.35,
  pursuitCycles: 6,
};

export const DEFAULT_TASK_CONFIG: Record<TaskType, WebTaskConfig> = {
  prosaccade: { ...BASE },
  antisaccade: { ...BASE },
  gap_overlap: { ...BASE, numTrials: 12 },
  smooth_pursuit: { ...BASE },
};

export type Direction = "left" | "right" | "none";
export type Condition = "gap" | "overlap" | "none";

export interface TrialPlanItem {
  trialId: string;
  trialNumber: number;
  direction: Direction;
  condition: Condition;
  cycleNumber?: number;
}

/**
 * Generate the ordered trial plan for a task.
 * - pro/anti: balanced left/right, shuffled
 * - gap_overlap: balanced gap/overlap × left/right, shuffled
 * - smooth_pursuit: one item per cycle (no direction)
 */
export function generateTrialPlan(
  taskType: TaskType,
  cfg: WebTaskConfig,
  rng: () => number = Math.random,
): TrialPlanItem[] {
  if (taskType === "smooth_pursuit") {
    return Array.from({ length: cfg.pursuitCycles }, (_, i) => ({
      trialId: uid(),
      trialNumber: i + 1,
      direction: "none" as Direction,
      condition: "none" as Condition,
      cycleNumber: i + 1,
    }));
  }

  const n = cfg.numTrials;

  if (taskType === "gap_overlap") {
    const half = Math.floor(n / 2);
    const items: { direction: Direction; condition: Condition }[] = [];
    for (let i = 0; i < n; i++) {
      const condition: Condition = i < half ? "gap" : "overlap";
      const direction: Direction = i % 2 === 0 ? "left" : "right";
      items.push({ direction, condition });
    }
    return shuffle(items, rng).map((it, i) => ({
      trialId: uid(),
      trialNumber: i + 1,
      direction: it.direction,
      condition: it.condition,
    }));
  }

  // pro-saccade / anti-saccade: balanced left/right
  const half = Math.floor(n / 2);
  const dirs: Direction[] = [
    ...Array(half).fill("left"),
    ...Array(n - half).fill("right"),
  ];
  return shuffle(dirs, rng).map((direction, i) => ({
    trialId: uid(),
    trialNumber: i + 1,
    direction,
    condition: "none",
  }));
}

/** Total number of "rounds" shown in the progress UI. */
export function totalRounds(taskType: TaskType, cfg: WebTaskConfig): number {
  return taskType === "smooth_pursuit" ? cfg.pursuitCycles : cfg.numTrials;
}
