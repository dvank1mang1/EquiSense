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
  const box =
    tone === "warning"
      ? "border-amber-700/50 bg-amber-950/30 text-amber-100/90"
      : "border-red-900/50 bg-red-950/30 text-red-100/90";
  const heading = tone === "warning" ? "text-amber-200" : "text-red-200";

  return (
    <div className={`rounded-lg border p-3 text-sm ${box}`}>
      <p className={`font-medium ${heading}`}>{title}</p>
      <p className="mt-1 text-slate-300">
        {ae?.message ?? "Проверьте сеть, ключи API и что backend запущен."}
      </p>
      {ae?.request_id ? (
        <p className="mt-2 font-mono text-xs text-slate-500">request_id: {ae.request_id}</p>
      ) : null}
    </div>
  );
}
