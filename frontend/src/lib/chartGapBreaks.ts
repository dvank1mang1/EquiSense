/**
 * Insert null (x,y) pairs so Plotly "lines" trace does not draw through long gaps
 * in daily (or irregular) series — missing OHLCV days otherwise look like one segment.
 */
export function lineSeriesWithGapBreaks(
  xs: string[],
  ys: Array<number | null | undefined>,
  maxGapCalendarDays = 10
): { x: Array<string | null>; y: Array<number | null> } {
  const x: Array<string | null> = [];
  const y: Array<number | null> = [];
  const gapMs = maxGapCalendarDays * 86400000;
  for (let i = 0; i < xs.length; i++) {
    if (i > 0) {
      const prev = new Date(xs[i - 1]!).getTime();
      const cur = new Date(xs[i]!).getTime();
      if (Number.isFinite(prev) && Number.isFinite(cur) && cur - prev > gapMs) {
        x.push(null);
        y.push(null);
      }
    }
    const v = ys[i];
    x.push(xs[i]!);
    y.push(typeof v === "number" && Number.isFinite(v) ? v : null);
  }
  return { x, y };
}

/** Same calendar gaps, null inserted into every Y column (shared X for equity vs benchmark). */
export function pairedLineSeriesWithGapBreaks(
  dates: string[],
  maxGapCalendarDays: number,
  ...yColumns: number[][]
): { x: Array<string | null>; ys: Array<Array<number | null>> } {
  const gapMs = maxGapCalendarDays * 86400000;
  const nSeries = yColumns.length;
  const x: Array<string | null> = [];
  const ys: Array<Array<number | null>> = yColumns.map(() => []);

  for (let i = 0; i < dates.length; i++) {
    if (i > 0) {
      const prev = new Date(dates[i - 1]!).getTime();
      const cur = new Date(dates[i]!).getTime();
      if (Number.isFinite(prev) && Number.isFinite(cur) && cur - prev > gapMs) {
        x.push(null);
        for (let s = 0; s < nSeries; s++) {
          ys[s].push(null);
        }
      }
    }
    x.push(dates[i]!);
    for (let s = 0; s < nSeries; s++) {
      const v = yColumns[s]![i];
      ys[s].push(typeof v === "number" && Number.isFinite(v) ? v : null);
    }
  }
  return { x, ys };
}
