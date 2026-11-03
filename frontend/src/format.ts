const inr = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
const inr2 = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2, minimumFractionDigits: 2 });
const when = new Intl.DateTimeFormat("en-IN", { timeZone: "Asia/Kolkata", day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
const day = new Intl.DateTimeFormat("en-IN", { timeZone: "Asia/Kolkata", weekday: "short", day: "numeric", month: "short" });

export const crore = (v: number | null | undefined) =>
  v == null ? "–" : Math.abs(v) >= 100 ? inr.format(v) : inr2.format(v);
export const price = (v: number | null | undefined) => (v == null ? "–" : "₹" + inr2.format(v));
export const pct = (v: number | null | undefined, digits = 1) =>
  v == null ? "–" : `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(digits)}%`;
export const signClass = (v: number | null | undefined) => (v == null || v === 0 ? "text-muted" : v > 0 ? "text-up" : "text-down");

export function istTime(iso: string | null | undefined) {
  if (!iso) return "–";
  return when.format(new Date(iso));
}
export function istDay(isoDate: string | null | undefined) {
  if (!isoDate) return "–";
  return day.format(new Date(isoDate.length === 10 ? isoDate + "T10:00:00Z" : isoDate));
}
export function ago(iso: string | null | undefined) {
  if (!iso) return "never";
  const m = (Date.now() - new Date(iso).getTime()) / 60000;
  if (m < 1) return "just now";
  if (m < 60) return `${Math.round(m)} min ago`;
  if (m < 60 * 24) return `${Math.round(m / 60)} h ago`;
  return `${Math.round(m / 1440)} d ago`;
}
export const metricValue = (value: number | null, unit: string) => {
  if (value == null) return "–";
  if (unit === "₹ cr") return `${value < 0 ? "−" : ""}₹${crore(Math.abs(value))} cr`;
  if (unit === "%") return `${value.toFixed(1)}%`;
  if (unit === "pp") return `${value > 0 ? "+" : ""}${value.toFixed(1)} pp`;
  if (unit === "x") return `${value.toFixed(2)}×`;
  if (unit === "days") return `${Math.round(value)} days`;
  return `${value}`;
};
export const windowLabel = (h: number) => (h <= 24 ? "24 hours" : h % 24 === 0 ? `${h / 24} days` : `${h} hours`);
