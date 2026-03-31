/** Mirrors backend ROLLOUT_MODEL_IDS (no baseline). */
export const ROLLOUT_MODEL_IDS = [
  "model_a",
  "model_b",
  "model_c",
  "model_d",
  "model_e",
  "model_f",
] as const;

export type RolloutModelId = (typeof ROLLOUT_MODEL_IDS)[number];

/** All selectable prediction models in the UI (baseline + rollout). */
export const PREDICTION_MODEL_IDS = ["baseline_lr", ...ROLLOUT_MODEL_IDS] as const;

export const MODEL_LABELS: Record<string, string> = {
  baseline_lr: "LR: Baseline",
  model_a: "A: Tech",
  model_b: "B: Tech+Fund",
  model_c: "C: Tech+News",
  model_d: "D: All",
  model_e: "E: HGBoost (all)",
  model_f: "F: Vote XGB+LGB",
};

export const MODEL_LABELS_LONG: Record<string, string> = {
  baseline_lr: "LR: Baseline (linear)",
  model_a: "A: Technical Only",
  model_b: "B: Tech + Fundamental",
  model_c: "C: Tech + News",
  model_d: "D: All Features",
  model_e: "E: HistGradientBoosting (all features)",
  model_f: "F: Voting XGB + LightGBM (all features)",
};
