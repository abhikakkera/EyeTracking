import { describe, it, expect } from "vitest";
import {
  DEFAULT_TASK_CONFIG,
  generateTrialPlan,
  totalRounds,
} from "@/lib/taskConfigs";
import { mulberry32 } from "@/lib/taskTiming";

describe("generateTrialPlan", () => {
  it("pro-saccade is balanced left/right", () => {
    const cfg = DEFAULT_TASK_CONFIG.prosaccade;
    const plan = generateTrialPlan("prosaccade", cfg, mulberry32(1));
    expect(plan).toHaveLength(cfg.numTrials);
    const left = plan.filter((p) => p.direction === "left").length;
    const right = plan.filter((p) => p.direction === "right").length;
    expect(Math.abs(left - right)).toBeLessThanOrEqual(1);
    expect(plan.every((p) => p.condition === "none")).toBe(true);
    expect(plan.every((p) => p.trialId.length === 8)).toBe(true);
  });

  it("gap-overlap splits conditions evenly", () => {
    const cfg = DEFAULT_TASK_CONFIG.gap_overlap;
    const plan = generateTrialPlan("gap_overlap", cfg, mulberry32(2));
    const gap = plan.filter((p) => p.condition === "gap").length;
    const overlap = plan.filter((p) => p.condition === "overlap").length;
    expect(gap).toBe(Math.floor(cfg.numTrials / 2));
    expect(overlap).toBe(cfg.numTrials - gap);
  });

  it("smooth pursuit yields one item per cycle with cycle numbers", () => {
    const cfg = DEFAULT_TASK_CONFIG.smooth_pursuit;
    const plan = generateTrialPlan("smooth_pursuit", cfg, mulberry32(3));
    expect(plan).toHaveLength(cfg.pursuitCycles);
    expect(plan[0].cycleNumber).toBe(1);
    expect(plan.every((p) => p.direction === "none")).toBe(true);
  });

  it("trial numbers are sequential", () => {
    const cfg = DEFAULT_TASK_CONFIG.antisaccade;
    const plan = generateTrialPlan("antisaccade", cfg, mulberry32(4));
    plan.forEach((p, i) => expect(p.trialNumber).toBe(i + 1));
  });

  it("totalRounds matches task type", () => {
    expect(totalRounds("prosaccade", DEFAULT_TASK_CONFIG.prosaccade)).toBe(
      DEFAULT_TASK_CONFIG.prosaccade.numTrials,
    );
    expect(totalRounds("smooth_pursuit", DEFAULT_TASK_CONFIG.smooth_pursuit)).toBe(
      DEFAULT_TASK_CONFIG.smooth_pursuit.pursuitCycles,
    );
  });
});
