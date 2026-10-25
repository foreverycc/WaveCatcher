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

/** Value of a daily series on each of `days` (0 where the series has no entry). */
export function onDays(series: ValuePoint[], days: string[]): number[] {
    const byDate = new Map(series.map(p => [p.date, p.value]));
    return days.map(d => byDate.get(d) ?? 0);
}

/**
 * CD vs MC balance index (0-100) for each day: the percentile of that day's CD - MC among all days
 * (ties count half), so 50 is a typical day, near 100 CD dominates as rarely before, near 0 MC does.
 */
export function balanceIndex(cd: ValuePoint[], mc: ValuePoint[], days: string[]): number[] {
    const cdv = onDays(cd, days), mcv = onDays(mc, days);
    const net = days.map((_, i) => cdv[i] - mcv[i]);
    const sorted = [...net].sort((a, b) => a - b);
    const n = sorted.length;
    const below = (x: number) => { let lo = 0, hi = n; while (lo < hi) { const m = (lo + hi) >> 1; if (sorted[m] < x) lo = m + 1; else hi = m; } return lo; };
    const atOrBelow = (x: number) => { let lo = 0, hi = n; while (lo < hi) { const m = (lo + hi) >> 1; if (sorted[m] <= x) lo = m + 1; else hi = m; } return lo; };
    return net.map(x => n === 0 ? 50 : ((below(x) + (atOrBelow(x) - below(x)) * 0.5) / n) * 100);
}

/** Signal count per stock per day (all intervals). */
export function signalCountSeries(rows: SignalRow[] = [], n: Denom): ValuePoint[] {
    return rows.map(r => ({ date: r.date, value: KEYS.reduce((s, k) => s + (r[`count_${k}`] || 0), 0) / denomAt(n, r.date) }));
}

/** CD / MC Score per day (interval-weighted, per stock). */
export function scoreSeries(rows: ScoreRow[] = [], weights: Record<string, number> | undefined, n: Denom): ValuePoint[] {
    return rows.map(r => ({ date: r.date, value: weightedScore(r, weights, n) }));
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
