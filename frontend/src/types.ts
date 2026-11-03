export type Tier = "needs_you" | "worth_a_look" | "routine";

export interface ResultsRow {
  key: string; label: string;
  current: number | null; previous: number | null; year_ago: number | null;
  qoq_pct: number | null; yoy_pct: number | null;
}
export interface ResultsCard {
  type: "results"; basis: string; unit: string; periods: string[]; rows: ResultsRow[];
  ebitda_margin: (number | null)[]; source: string; source_url: string | null;
  check?: { status: string; note: string }; ebitda_note?: string | null;
  doc_id?: string; source_page?: number | null; is_lender?: boolean; unit_as_filed?: string;
}
export interface Person {
  name: string; role: string; change: string; effective_date?: string | null; reason?: string | null;
  profile?: string | null; previous_roles: string[]; page?: number | null; linkedin_search: string;
}
export interface MgmtCard { type: "management_change"; people: Person[]; is_top_role: boolean; doc_id?: string }

export interface DigestItem {
  id: string; symbol: string; company: string; published_at: string; category: string; category_label: string;
  classified_by: string; title: string; subject: string; summary: string | null; score: number; tier: Tier;
  reasons: string[]; attachment_url: string | null; exchange_url: string | null;
  enrichment: ResultsCard | MgmtCard | null; enrichment_status: string; alert: boolean;
  related?: RelatedFiling[];
}
export interface RelatedFiling { id: string; title: string; category_label: string; published_at: string; attachment_url: string | null; tier: Tier; summary?: string | null }
export interface Move {
  symbol: string; company: string; flags: string[]; text: string; date: string; close: number;
  pct: number | null; volume_multiple: number | null;
  nearby?: RelatedFiling[]; context_note?: string;
}
export interface Digest {
  window_hours: number; since: string;
  as_of: { announcements: string | null; prices: string | null; last_session: string | null; moves_from_session: string | null };
  counts: { total: number; needs_you: number; worth_a_look: number; routine: number; moves: number; companies: number; grouped?: number };
  alerts_evaluated_at?: string | null;
  triggered: DigestItem[]; moves: Move[]; tiers: Record<Tier, DigestItem[]>;
  ticks: { id: string; symbol: string; tier: Tier; published_at: string }[];
}
export interface Prefs {
  price_move_pct: number; volume_multiple: number; default_window_hours: number;
  alert_categories: string[]; category_weights: Record<string, number>; muted_symbols: string[];
}
export interface PriceSnap {
  date: string; close: number; pct: number | null; volume_multiple: number | null; flags: string[];
  spark: number[]; pct_1y: number | null; high_52w: number | null; low_52w: number | null;
}
export interface Metric { label: string; value: number | null; unit: string; formula: string; inputs: string[]; note: string | null }
export interface Series { label: string; periods: string[]; values: (number | null)[] }
export interface Metrics {
  basis: string; source: string; source_url: string; retrieved_at: string; stale: boolean; latest_fy?: string;
  top_ratios: Record<string, string>; snapshot: Metric[]; trajectory: Metric[]; balance: Metric[]; cash: Metric[];
  is_lender: boolean;
  watch?: { label: string; detail: string; inputs: string[] }[]; watch_checks?: string[];
  series: {
    margin?: { period: string; value: number }[]; revenue?: Series | null; pat?: Series | null;
    borrowings?: Series | null; quarterly_revenue?: Series | null; quarterly_margin?: Series | null;
    cash_conversion?: { period: string; cfo: number; pat: number; ratio: number }[];
  };
}
export interface Overview {
  symbol: string; name: string; basis: string; metrics: Metrics; results: ResultsCard | null;
  price: PriceSnap | null; in_portfolio: boolean;
  documents: {
    annual_reports: { title: string; year: number | null; url: string; doc_id: string }[];
    concalls: { period: string; quarter: string | null; transcript?: string; ppt?: string; recording?: string; doc_id: string | null }[];
  };
}
export type Verdict = "delivered" | "partly" | "missed" | "in_progress" | "too_early" | "unverifiable";
export interface Pledge {
  id: string; metric: string; metric_label: string; statement: string; quote: string; quote_verified: boolean;
  page: number; doc_id: string; speaker?: string | null; horizon: string; target: string; firmness: string;
  call_period: string; call_quarter: string; verdict: Verdict; explanation: string; judged_by: string;
  actual: { value: number; unit: string; period: string; formula: string; inputs: string[]; source_url?: string | null } | null;
  evidence?: { doc_id: string; page: number; quote: string }[];
  outcome?: string; variance?: number; variance_text?: string;
}
export interface Gate { status: string; note?: string; stale?: boolean; cached_at?: string }
export interface NarrativeClaim {
  id: string; statement: string; quote: string; page: number; doc_id: string; speaker?: string | null; metric: string; metric_label: string;
  direction: string; period: string; call_period: string; call_quarter: string;
  verdict: "supported" | "partly" | "divergent" | "not_measurable" | "insufficient"; interpretation: string;
  numbers: { value: number; unit: string; period: string; text: string; formula: string; inputs: string[]; source_url?: string | null } | null;
}
export interface NarrativeReport extends Gate {
  symbol?: string; headline?: string | null; claims?: NarrativeClaim[]; transcripts?: { doc_id: string; period: string; quarter: string; status: string }[];
}
export interface PromiseReport extends Gate {
  symbol: string; status: string; generated_at?: string; basis?: string;
  transcripts: { doc_id: string; period: string; quarter: string; status: string; pages_n: number; url: string }[];
  promises: Pledge[]; current_guidance: Pledge[];
  scorecard?: Record<Verdict, number> & { checkable: number; hit_rate: number | null; headline: string | null };
}
export interface Cite { doc_id: string; page: number }
export interface Claim { text: string; citations: Cite[]; verified: boolean; unsupported_numbers: string[] }
export interface Business extends Gate {
  status: string; one_liner?: string; facts?: Claim[];
  segments?: { name: string; description: string; revenue_share_pct: number | null; citations: Cite[] }[];
  sources?: { id: string; title: string }[];
}
export interface BullBear extends Gate {
  status: string;
  bull?: { point: string; citations: Cite[]; metric_refs: string[]; verified: boolean }[];
  bear?: { point: string; citations: Cite[]; metric_refs: string[]; verified: boolean }[];
}
export interface Answer {
  status: string; question: string; summary: string; claims: Claim[]; follow_ups: string[];
  sources: { id: string; title: string }[]; searched: { title: string; status: string; pages: number }[];
}
export interface Usage {
  llm_enabled: boolean; routing: { fast: string; reason: string };
  models: { model: string; calls: number; input_tokens: number; output_tokens: number; cache_hits: number }[];
  by_purpose: Record<string, number>; total_calls: number; total_cache_hits: number;
}
