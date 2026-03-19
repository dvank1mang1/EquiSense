import { usePrediction } from "@/hooks/usePrediction";
import clsx from "clsx";

const MODELS = [
  { id: "model_a", label: "A: Tech" },
  { id: "model_b", label: "B: Tech+Fund" },
  { id: "model_c", label: "C: Tech+News" },
  { id: "model_d", label: "D: All" },
];

const SIGNAL_STYLES: Record<string, string> = {
  "Strong Buy": "badge-buy border border-success/40",
  "Buy": "badge-buy",
  "Hold": "badge-hold",
  "Sell": "badge-sell",
};

interface PredictionCardProps {
  ticker: string;
  model: string;
  onModelChange: (model: string) => void;
}

export default function PredictionCard({ ticker, model, onModelChange }: PredictionCardProps) {
  const { data, isLoading } = usePrediction(ticker, model);

  return (
    <div className="card h-full flex flex-col gap-4">
      <h3>Прогноз</h3>

      {/* Model selector */}
      <div className="flex flex-wrap gap-1">
        {MODELS.map((m) => (
          <button
            key={m.id}
            onClick={() => onModelChange(m.id)}
            className={clsx(
              "text-xs px-2 py-1 rounded border transition-colors",
              model === m.id
                ? "bg-brand-600 border-brand-600 text-white"
                : "border-surface-600 text-slate-400 hover:text-white"
            )}
          >
            {m.label}
          </button>
        ))}
      </div>

      {isLoading ? (
        <div className="flex-1 animate-pulse bg-surface-700 rounded-lg" />
      ) : (
        <div className="flex flex-col items-center gap-3 py-4">
          {/* Signal */}
          <span className={clsx("text-sm font-semibold px-4 py-1.5 rounded-full", SIGNAL_STYLES[data?.signal ?? "Hold"])}>
            {data?.signal ?? "—"}
          </span>

          {/* Probability */}
          <div className="text-center">
            <p className="text-4xl font-bold text-white">
              {data?.probability != null ? `${(data.probability * 100).toFixed(1)}%` : "—"}
            </p>
            <p className="text-xs text-slate-500 mt-1">Вероятность роста</p>
          </div>

          {/* Confidence */}
          <div className="w-full">
            <div className="flex justify-between text-xs text-slate-500 mb-1">
              <span>Confidence</span>
              <span>{data?.confidence != null ? `${(data.confidence * 100).toFixed(0)}%` : "—"}</span>
            </div>
            <div className="w-full bg-surface-700 rounded-full h-1.5">
              <div
                className="bg-brand-500 h-1.5 rounded-full transition-all"
                style={{ width: `${((data?.confidence ?? 0) * 100).toFixed(0)}%` }}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
