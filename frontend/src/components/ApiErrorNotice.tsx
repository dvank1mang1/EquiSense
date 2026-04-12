import { getApiError } from "@/lib/api";

type Props = {
  error: unknown;
  title?: string;
  /** amber = softer (e.g. backtest); red = default */
  tone?: "danger" | "warning";
};

export default function ApiErrorNotice({
  error,
  title = "Ошибка",
  tone = "danger",
}: Props) {
  const ae = getApiError(error);
  const shell =
    tone === "warning"
      ? "border border-amber-500/20 border-l-4 border-l-amber-400/30 bg-amber-950/20 text-slate-200 shadow-sm shadow-black/10"
      : "border border-red-500/15 border-l-4 border-l-red-400/30 bg-red-950/20 text-slate-200 shadow-sm shadow-black/10";
  const titleCls = tone === "warning" ? "text-amber-100/95" : "text-red-100/95";

  return (
    <div
      className={`rounded-xl p-4 text-sm ${shell}`}
      role="status"
      aria-live="polite"
      aria-atomic="true"
    >
      <p className={`text-sm font-medium tracking-tight ${titleCls}`}>{title}</p>
      <p className="mt-2 text-sm leading-relaxed text-slate-400">
        {ae?.message ?? "Проверьте сеть, ключи API и что backend запущен."}
      </p>
      {ae?.request_id ? (
        <p className="mt-3 rounded-md bg-black/20 px-2 py-1.5 font-mono text-[11px] text-slate-500">
          request_id: {ae.request_id}
        </p>
      ) : null}
    </div>
  );
}
