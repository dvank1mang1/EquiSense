import ApiErrorNotice from "@/components/ApiErrorNotice";
import { usePrediction } from "@/hooks/usePrediction";
import { MODEL_LABELS, PREDICTION_MODEL_IDS } from "@/lib/models";
import clsx from "clsx";

const MODELS = PREDICTION_MODEL_IDS.map((id) => ({ id, label: MODEL_LABELS[id] ?? id }));

const SIGNAL_STYLES: Record<string, string> = {
  "Strong Buy": "border border-success/30 bg-success/15 text-success",
  "Buy": "border border-success/25 bg-success/12 text-success",
  "Hold": "border border-warning/25 bg-warning/12 text-warning",
  "Sell": "border border-danger/25 bg-danger/15 text-danger",
};

const CHIP_BASE =
  "text-xs font-medium px-3 py-1.5 rounded-lg border transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 focus-visible:ring-offset-surface-800 active:scale-[0.98]";
const CHIP_ON = "border-brand-500/80 bg-brand-600 text-white shadow-sm shadow-black/25";
const CHIP_OFF =
  "border-surface-600/80 bg-surface-900/30 text-slate-400 hover:border-surface-500 hover:bg-surface-800/60 hover:text-slate-200";

interface PredictionCardProps {
  ticker: string;
  model: string;
  onModelChange: (model: string) => void;
}

export default function PredictionCard({ ticker, model, onModelChange }: PredictionCardProps) {
  const { data, error, isLoading } = usePrediction(ticker, model);
  const toUnitInterval = (value: unknown): number | undefined => {
    if (typeof value !== "number" || !Number.isFinite(value)) return undefined;
    if (value < 0 || value > 1) return undefined;
    return value;
  };

  const probability = toUnitInterval(data?.probability);
  const confidence = toUnitInterval(data?.confidence);
  const signal = typeof data?.signal === "string" && data.signal.trim().length > 0 ? data.signal : undefined;
  const hasPrediction = signal != null || probability != null || confidence != null;

  return (
    <div className="card h-full flex flex-col gap-4">
      <div className="mb-0.5">
        <h3 className="text-base font-semibold tracking-tight text-white">Прогноз</h3>
        <p className="mt-1 text-xs leading-relaxed text-slate-500">
          Сигнал и вероятность роста по выбранной модели.
        </p>
      </div>

      {error ? <ApiErrorNotice error={error} title="Прогноз недоступен" /> : null}

      {/* Model selector */}
      <div className="flex flex-wrap gap-1.5" role="group" aria-label="Модель прогноза">
        {MODELS.map((m) => (
          <button
            key={m.id}
            type="button"
            onClick={() => onModelChange(m.id)}
            aria-pressed={model === m.id}
            className={clsx(CHIP_BASE, model === m.id ? CHIP_ON : CHIP_OFF)}
          >
            {m.label}
          </button>
        ))}
      </div>

      {isLoading ? (
        <div
          className="relative flex-1 min-h-[164px] overflow-hidden rounded-xl border border-surface-700/50 bg-surface-900/20"
          role="status"
          aria-live="polite"
        >
          <span className="sr-only">Загрузка прогноза…</span>
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-4 p-6">
            <div className="h-8 w-28 rounded-full bg-surface-700/90 animate-pulse" />
            <div className="h-10 w-24 rounded-lg bg-surface-700/80 animate-pulse" />
            <div className="w-full max-w-[200px] space-y-2">
              <div className="h-2 w-full rounded-md bg-surface-700/70 animate-pulse" />
              <div className="h-2 w-4/5 rounded-md bg-surface-600/50 animate-pulse [animation-delay:150ms]" />
            </div>
          </div>
        </div>
      ) : error ? (
        <div className="flex-1 flex items-center justify-center py-2">
          <p className="text-xs text-slate-500">Попробуйте другой тикер или модель.</p>
        </div>
      ) : !hasPrediction ? (
        <div className="flex-1 flex items-center justify-center py-6" role="status">
          <p className="text-sm text-slate-400 text-center">
            Недостаточно данных для прогноза по этому тикеру.
          </p>
        </div>
      ) : (
        <div className="flex flex-col items-center gap-3 py-4">
          {/* Signal */}
          <span
            className={clsx(
              "inline-flex items-center rounded-lg px-4 py-1.5 text-sm font-semibold transition-colors",
              SIGNAL_STYLES[signal ?? "Hold"]
            )}
            aria-label={signal ? `Сигнал: ${signal}` : "Сигнал не определён"}
          >
            {signal ?? "—"}
          </span>

          {/* Probability */}
          <div className="text-center">
            <p className="text-4xl font-bold text-white">
              {probability != null ? `${(probability * 100).toFixed(1)}%` : "—"}
            </p>
            <p className="text-xs text-slate-500 mt-1">Вероятность роста</p>
          </div>

          {/* Confidence */}
          <div className="w-full">
            <div className="flex justify-between text-xs text-slate-500 mb-1">
              <span>Confidence</span>
              <span>{confidence != null ? `${(confidence * 100).toFixed(0)}%` : "—"}</span>
            </div>
            <div className="w-full bg-surface-700/80 rounded-full h-1.5 overflow-hidden">
              <div
                className="bg-brand-500 h-1.5 rounded-full transition-all"
                style={{ width: `${((confidence ?? 0) * 100).toFixed(0)}%` }}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
