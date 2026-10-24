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
const DEFAULT_WEIGHTS: Record<string, number> = { '1h': 1, '2h': 2, '3h': 4, '4h': 8, '1d': 32 };

/** For a single ticker: 1 on days with a signal on any interval. */
export function companiesFromSignalBreadth(rows: SignalRow[] = []): CompanyBreadthPoint[] {
    return rows
        .filter(r => KEYS.some(k => (r[`count_${k}`] || 0) > 0))
        .map(r => ({ date: r.date, count: 1 }));
}

/** CD / MC Score as shown in the breadth chart: interval-weighted score sum per stock. */
export function weightedScore(row: ScoreRow, weights: Record<string, number> | undefined, n: number): number {
    const w = weights || DEFAULT_WEIGHTS;
    return KEYS.reduce((sum, k) => sum + (row[`score_${k}`] || 0) * (w[k] ?? DEFAULT_WEIGHTS[k]), 0) / n;
}

/** Share of the stock list with a signal each day (0-1). */
export function breadthShare(companies: CompanyBreadthPoint[] = [], n: number): ValuePoint[] {
    return companies.map(c => ({ date: c.date, value: c.count / n }));
}

/** Breadth score per day: Score x share of companies with a signal (always >= 0; MC is negated for display). */
export function breadthScore(
    companies: CompanyBreadthPoint[] = [], scores: ScoreRow[] = [],
    weights: Record<string, number> | undefined, n: number,
): ValuePoint[] {
    const share = new Map(companies.map(c => [c.date, c.count / n]));
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
export function signalCountSeries(rows: SignalRow[] = [], n: number): ValuePoint[] {
    return rows.map(r => ({ date: r.date, value: KEYS.reduce((s, k) => s + (r[`count_${k}`] || 0), 0) / n }));
}

/** CD / MC Score per day (interval-weighted, per stock). */
export function scoreSeries(rows: ScoreRow[] = [], weights: Record<string, number> | undefined, n: number): ValuePoint[] {
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
 */
export function capWeightedScore(
    companies: CompanyBreadthPoint[] = [],
    weights: Record<string, number> | undefined,
    listTickers: string[],
    intervalWeights: Record<string, number>,
): Map<string, number> {
    const w = (t: string) => weights ? (weights[t.toUpperCase()] || 0) : 1;
    const total = listTickers.reduce((s, t) => s + w(t), 0);
    const out = new Map<string, number>();
    if (total <= 0) return out;
    for (const c of companies) {
        if (!c.scores) continue;
        let v = 0;
        for (const [t, byIntv] of Object.entries(c.scores)) {
            const tw = w(t);
            if (!tw) continue;
            let s = 0;
            for (const [intv, score] of Object.entries(byIntv)) s += score * (intervalWeights[intv] ?? 0);
            v += s * tw / total;
        }
        out.set(c.date, v);
    }
    return out;
}
