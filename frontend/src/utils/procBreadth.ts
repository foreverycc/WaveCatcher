// "Proc" breadth: each trading day's value is the previous trading day's plus today's,
// so a signal fired late in one session still counts on the next.
const KEYS = ['1h', '2h', '3h', '4h', '1d'] as const;

type Row = { date: string } & Record<string, any>;

export function procBreadth<T extends Row>(data: T[], tradingDates: string[], field: 'count' | 'score'): T[] {
    if (!data || data.length === 0) return [];
    const byDate = new Map(data.map(d => [d.date, d]));
    const dates = tradingDates.length > 0 ? tradingDates : data.map(d => d.date).sort();
    const out: T[] = [];
    let prev: Row | undefined;
    dates.forEach(date => {
        const cur = byDate.get(date);
        if (cur || prev) {
            const row: Row = { date };
            KEYS.forEach(k => {
                row[`${field}_${k}`] = (cur?.[`${field}_${k}`] || 0) + (prev?.[`${field}_${k}`] || 0);
            });
            out.push(row as T);
        }
        prev = cur;
    });
    return out;
}
