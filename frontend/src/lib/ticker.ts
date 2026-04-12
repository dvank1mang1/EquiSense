/** US-style symbols: letters, digits, dot (BRK.B), hyphen (BF-B). */
const TICKER_PATTERN = /^[A-Z0-9][A-Z0-9.-]{0,14}$/;

export function normalizeTicker(raw: string): string | null {
  const s = raw.trim().toUpperCase();
  if (!s || s.length > 15) return null;
  return TICKER_PATTERN.test(s) ? s : null;
}
