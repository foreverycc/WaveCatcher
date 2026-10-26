import type { DayMarks } from '../components/MarketHeatmap';
// Market breadth: how many companies had a CD / MC signal each day, and the breadth score
// (that day's CD / MC Score times the share of companies with a signal).

export interface CompanyBreadthPoint {
    date: string;
    count: number;
    tickers?: string[];
    /** per ticker: indicator score sum by interval ('1h', ..., '1d') that day */
    scores?: Record<string, Record<string, number>>;
}
export interface ValuePoint { date: string; value: number }

/** % of stocks closing above their 20 / 50 / 200-day moving average (n = stocks with enough history) */
export interface DmaBreadthPoint {
    date: string;
    above20: number | null; above50: number | null; above200: number | null;
    n20: number; n50: number; n200: number;
}

type ScoreRow = { date: string; score_1h?: number; score_2h?: number; score_3h?: number; score_4h?: number; score_1d?: number };
type SignalRow = { date: string; count_1h?: number; count_2h?: number; count_3h?: number; count_4h?: number; count_1d?: number };

const KEYS = ['1h', '2h', '3h', '4h', '1d'] as const;

/** Stocks to divide by: a fixed count, or per day (stocks already trading that day). */
export type Denom = number | ((date: string) => number);
export const denomAt = (n: Denom, date: string) => (typeof n === 'number' ? n : n(date)) || 1;

/** first daily bar (YYYY-MM-DD) of tickers whose history starts late, e.g. recent IPOs */
export type FirstDates = Record<string, string>;

/** True when the ticker had data on `date` (listed by then). */
export const listedOn = (firstDates: FirstDates | undefined, ticker: string, date: string) =>
    !firstDates || !(firstDates[ticker.toUpperCase()] > date);

/**
 * Per-day stock count of a list: the stocks already trading that day. Without first dates (or
 * no late listings) this is the plain list size.
 */
export function listedCount(listTickers: string[], firstDates?: FirstDates): Denom {
    const n = listTickers.length;
    const late = firstDates ? listTickers.map(t => firstDates[t.toUpperCase()]).filter(Boolean) : [];
    if (late.length === 0) return n;
    return (date: string) => n - late.filter(f => f > date).length;
}

/**
 * Price of each ticker relative to its latest close, sampled every few trading days
 * (integers in 1/10000, null before the ticker had data). From the backend's cap history.
 */
export interface CapHistory { dates: string[]; ratios: Record<string, (number | null)[]> }

/** Weight of a ticker on a day. */
export type WeightOn = (ticker: string, date: string) => number;

/**
 * Weights at each day's market cap: today's weight times the stock's price then over its price
 * now (shares outstanding taken as constant), using the latest sample on or before the day.
 * Without weights every stock weighs 1; without a cap history today's weights are used.
 */
export function weightOnDay(weights: Record<string, number> | undefined, hist?: CapHistory): WeightOn {
    const base = (t: string) => weights ? (weights[t.toUpperCase()] || 0) : 1;
    if (!weights || !hist || hist.dates.length === 0) return t => base(t);
    const dates = hist.dates;
    const idxCache = new Map<string, number>();
    const idxOf = (date: string) => {
        let i = idxCache.get(date);
        if (i === undefined) {
            let lo = 0, hi = dates.length; // first sample after `date`
            while (lo < hi) { const m = (lo + hi) >> 1; if (dates[m] <= date) lo = m + 1; else hi = m; }
            i = Math.max(0, lo - 1);
            idxCache.set(date, i);
        }
        return i;
    };
    return (t: string, date: string) => {
        const b = base(t);
        if (!b) return 0;
        const r = hist.ratios[t.toUpperCase()];
        if (!r) return b;
        const v = r[idxOf(date)];
        return v == null ? 0 : b * v / 10000;
    };
}

/** Per-day total weight of the stocks of a list already trading that day. */
export function listedWeight(listTickers: string[], w: WeightOn, firstDates?: FirstDates): (date: string) => number {
    const cache = new Map<string, number>();
    return (date: string) => {
        let total = cache.get(date);
        if (total === undefined) {
            total = 0;
            for (const t of listTickers) if (listedOn(firstDates, t, date)) total += w(t, date);
            cache.set(date, total);
        }
        return total;
    };
}
const DEFAULT_WEIGHTS: Record<string, number> = { '1h': 1, '2h': 2, '3h': 4, '4h': 8, '1d': 32 };

/** For a single ticker: 1 on days with a signal on any interval. */
export function companiesFromSignalBreadth(rows: SignalRow[] = []): CompanyBreadthPoint[] {
    return rows
        .filter(r => KEYS.some(k => (r[`count_${k}`] || 0) > 0))
        .map(r => ({ date: r.date, count: 1 }));
}

/** CD / MC Score as shown in the breadth chart: interval-weighted score sum per stock. */
export function weightedScore(row: ScoreRow, weights: Record<string, number> | undefined, n: Denom): number {
    const w = weights || DEFAULT_WEIGHTS;
    return KEYS.reduce((sum, k) => sum + (row[`score_${k}`] || 0) * (w[k] ?? DEFAULT_WEIGHTS[k]), 0) / denomAt(n, row.date);
}

/** Share of the stock list with a signal each day (0-1). */
export function breadthShare(companies: CompanyBreadthPoint[] = [], n: Denom): ValuePoint[] {
    return companies.map(c => ({ date: c.date, value: c.count / denomAt(n, c.date) }));
}

/** Breadth score per day: Score x share of companies with a signal (always >= 0; MC is negated for display). */
export function breadthScore(
    companies: CompanyBreadthPoint[] = [], scores: ScoreRow[] = [],
    weights: Record<string, number> | undefined, n: Denom,
): ValuePoint[] {
    const share = new Map(companies.map(c => [c.date, c.count / denomAt(n, c.date)]));
    return scores
        .filter(s => share.has(s.date))
        .map(s => ({ date: s.date, value: weightedScore(s, weights, n) * (share.get(s.date) || 0) }));
}

/**
 * Weighted share of the stock list with a signal each day (0-1): the summed weight of the tickers
 * with a signal over the summed weight of the list. Tickers without a weight count as 0.
 */
export function weightedShare(companies: CompanyBreadthPoint[] = [], weights: Record<string, number>, listTickers: string[]): ValuePoint[] {
    const total = listTickers.reduce((s, t) => s + (weights[t.toUpperCase()] || 0), 0);
    if (total <= 0) return [];
    return companies.map(c => ({
        date: c.date,
        value: (c.tickers || []).reduce((s, t) => s + (weights[t.toUpperCase()] || 0), 0) / total,
    }));
}

/**
 * Cap-weighted score per day: each ticker's interval-weighted score times its share of the
 * list's total weight, summed over tickers (Weighted Breadth Score 2). Tickers without a signal add 0.
 * Without weights every ticker of the list counts equally (= the plain average score).
 * The total only counts stocks already trading that day (see firstDates); with a cap history
 * every day uses that day's market caps.
 */
export function capWeightedScore(
    companies: CompanyBreadthPoint[] = [],
    weights: Record<string, number> | undefined,
    listTickers: string[],
    intervalWeights: Record<string, number>,
    firstDates?: FirstDates,
    capHistory?: CapHistory,
): Map<string, number> {
    const w = weightOnDay(weights, capHistory);
    const totalOn = listedWeight(listTickers, w, firstDates);
    const out = new Map<string, number>();
    for (const c of companies) {
        if (!c.scores) continue;
        const total = totalOn(c.date);
        if (total <= 0) continue;
        let v = 0;
        for (const [t, byIntv] of Object.entries(c.scores)) {
            const tw = w(t, c.date);
            if (!tw) continue;
            let s = 0;
            for (const [intv, score] of Object.entries(byIntv)) s += score * (intervalWeights[intv] ?? 0);
            v += s * tw / total;
        }
        out.set(c.date, v);
    }
    return out;
}

/** Index CD / MC days (from its daily price history) and 1234 days, for the Market Trend markers */
export function indexMarks(
    history: { time?: string; cd_signal?: boolean; mc_signal?: boolean }[] | undefined,
    signals: { cd_dates?: string[]; mc_dates?: string[] } | undefined,
) {
    const marks: Record<string, DayMarks> = {};
    const at = (d: string) => (marks[d] ??= {});
    (history ?? []).forEach(r => {
        const d = String(r.time ?? '').split('T')[0];
        if (!d) return;
        if (r.cd_signal) at(d).cd = true;
        if (r.mc_signal) at(d).mc = true;
    });
    (signals?.cd_dates ?? []).forEach(d => { at(d).cd1234 = true; });
    (signals?.mc_dates ?? []).forEach(d => { at(d).mc1234 = true; });
    return marks;
}
