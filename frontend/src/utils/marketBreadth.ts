// Market breadth: how many companies had a CD / MC signal each day, and the breadth score
// (that day's CD / MC Score times the share of companies with a signal).

export interface CompanyBreadthPoint { date: string; count: number }
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
