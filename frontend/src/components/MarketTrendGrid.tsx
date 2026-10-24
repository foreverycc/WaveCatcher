import React, { useMemo, useState } from 'react';
import { cn } from '../utils/cn';
import type { CompanyBreadthPoint } from '../utils/marketBreadth';
import type { HeatmapGroup } from './MarketHeatmap';

/**
 * Market trend: one row per index / sector plus a "Market" row on top, one column per trading day.
 * Each cell is that day's net score, either the Breadth Score (CD Score x share of companies with CD
 * minus the same for MC, as in the Market Breadth chart) or the market-cap weighted score
 * (sum over stocks of interval-weighted CD - MC score x the stock's share of the row's market cap).
 * The Market row pools every stock of all rows (each counted once). Click a row to open its stock heatmap.
 */

interface Props {
    groups: HeatmapGroup[];
    intervalWeights: Record<string, number>;
    /** Date Filters range (YYYY-MM-DD): percentiles are taken against the days in it, like the gauges */
    minDate?: string;
    maxDate?: string;
    selected: string[];
    onToggle: (key: string) => void;
    onSelectAll: () => void;
    /** a day cell was clicked: open that row's heatmap for that day */
    onPickDay: (key: string, date: string) => void;
    /** day shown in the stock heatmap (highlighted column); null = latest */
    pickedDate?: string | null;
}

const SPANS = [{ label: '20D', days: 20 }, { label: '60D', days: 60 }, { label: '120D', days: 120 }, { label: '1Y', days: 252 }];
export const MARKET_ROW = '__market__';

// Percentile bands, finest at the tails: the app cares most about the extreme 5% / 1% days
const PCT_BANDS: { max: number; color: string; label: string; legend: string }[] = [
    { max: 1, color: '#ff2b2b', label: 'Extreme MC (bottom 1%)', legend: '≤1' },
    { max: 5, color: '#c93a40', label: 'Strong MC (bottom 5%)', legend: '1–5' },
    { max: 10, color: '#94424b', label: 'MC (bottom 10%)', legend: '5–10' },
    { max: 25, color: '#5f444f', label: 'Mild MC', legend: '10–25' },
    { max: 75, color: '#3b3e49', label: 'Neutral', legend: '25–75' },
    { max: 90, color: '#34584a', label: 'Mild CD', legend: '75–90' },
    { max: 95, color: '#2e7f4b', label: 'CD (top 10%)', legend: '90–95' },
    { max: 99, color: '#2bb052', label: 'Strong CD (top 5%)', legend: '95–99' },
    { max: 100, color: '#4dff7c', label: 'Extreme CD (top 1%)', legend: '≥99' },
];

type Metric = 'breadth' | 'weighted';
const METRICS: { key: Metric; label: string; desc: string }[] = [
    { key: 'breadth', label: 'Breadth Score', desc: 'CD Score × share of companies with CD − MC Score × share with MC' },
    { key: 'weighted', label: 'Weighted', desc: 'Σ (CD − MC score) × market-cap share per stock' },
];

/** date -> ticker -> interval-weighted score (a ticker present = it had a signal that day) */
type SideScores = Map<string, Map<string, number>>;

function addSide(out: SideScores, rows: CompanyBreadthPoint[], iw: Record<string, number>) {
    rows.forEach(c => {
        let day = out.get(c.date);
        if (!day) { day = new Map(); out.set(c.date, day); }
        (c.tickers || []).forEach(t => { if (!day!.has(t)) day!.set(t, 0); });
        Object.entries(c.scores || {}).forEach(([t, byIntv]) => {
            let s = 0;
            Object.entries(byIntv).forEach(([k, v]) => { s += v * (iw[k] ?? 0); });
            day!.set(t, s);
        });
    });
}

function rowSeries(metric: Metric, tickers: string[], weights: Record<string, number> | undefined,
                   cd: SideScores, mc: SideScores, days: string[]) {
    const n = tickers.length;
    if (n === 0) return days.map(() => 0);
    if (metric === 'breadth') {
        // same as the Breadth Score lane: average score x share of companies with a signal
        const side = (day?: Map<string, number>) => {
            if (!day) return 0;
            let sum = 0, cnt = 0;
            tickers.forEach(t => { const v = day.get(t); if (v !== undefined) { sum += v; cnt += 1; } });
            return (sum / n) * (cnt / n);
        };
        return days.map(d => side(cd.get(d)) - side(mc.get(d)));
    }
    const hasW = !!weights && Object.keys(weights).length > 0;
    const w = (t: string) => hasW ? (weights![t] || 0) : 1;
    const total = tickers.reduce((s, t) => s + w(t), 0);
    return days.map(d => {
        if (total <= 0) return 0;
        const c = cd.get(d), m = mc.get(d);
        let v = 0;
        tickers.forEach(t => { v += ((c?.get(t) || 0) - (m?.get(t) || 0)) * w(t); });
        return v / total;
    });
}

export const MarketTrendGrid: React.FC<Props> = ({ groups, intervalWeights, minDate, maxDate, selected, onToggle, onSelectAll, onPickDay, pickedDate }) => {
    const [span, setSpan] = useState(60);
    const [metric, setMetric] = useState<Metric>(() => {
        try { return localStorage.getItem('marketTrendMetric') === 'weighted' ? 'weighted' : 'breadth'; } catch { return 'breadth'; }
    });
    const chooseMetric = (m: Metric) => { setMetric(m); try { localStorage.setItem('marketTrendMetric', m); } catch { /* ignore */ } };
    const [hover, setHover] = useState<{ row: string; date: string; value: number; raw: number; x: number; y: number } | null>(null);

    const { days, rows } = useMemo(() => {
        const allDays = new Set<string>();
        groups.forEach(g => g.tradingDays.forEach(d => allDays.add(d)));
        if (allDays.size === 0) groups.forEach(g => [...g.cdCompanyBreadth, ...g.mcCompanyBreadth].forEach(c => allDays.add(c.date)));
        const fullDays = Array.from(allDays).filter(d => !maxDate || d <= maxDate).sort();
        const days = fullDays.slice(-span);
        // Reference days for the percentile: the Date Filters range, as the gauges use
        let refDays = fullDays.filter(d => !minDate || d >= minDate);
        if (refDays.length === 0) refDays = days;
        const calcDays = Array.from(new Set([...refDays, ...days])).sort();
        const shownAt = days.map(d => calcDays.indexOf(d));
        const refAt = refDays.map(d => calcDays.indexOf(d));
        // midrank percentile (0-100) of each shown day's value among the reference days (ties count half)
        const toRow = (r: { key: string; label: string; sub: string; values: number[] }) => {
            const ref = refAt.map(i => r.values[i]).sort((a, b) => a - b);
            const n = ref.length;
            const pctOf = (x: number) => {
                if (n === 0) return 50;
                let below = 0, equal = 0;
                for (const v of ref) { if (v < x) below++; else if (v === x) equal++; }
                return ((below + equal * 0.5) / n) * 100;
            };
            const raw = shownAt.map(i => r.values[i]);
            return { key: r.key, label: r.label, sub: r.sub, raw, values: raw.map(pctOf) };
        };

        // One score table per side for all rows: a stock's score is the same whichever index it is in
        const cd: SideScores = new Map(), mc: SideScores = new Map();
        groups.forEach(g => { addSide(cd, g.cdCompanyBreadth, intervalWeights); addSide(mc, g.mcCompanyBreadth, intervalWeights); });

        const perGroup = groups.map(g => {
            const tickers = Array.from(new Set(g.tickers.map(t => t.toUpperCase())));
            return { key: g.key, label: g.key, sub: g.symbol, tickers, values: rowSeries(metric, tickers, g.weights, cd, mc, calcDays) };
        });

        // Market row: every stock of all rows once, with the largest market cap seen for it
        const mTickers = new Set<string>();
        const mWeights: Record<string, number> = {};
        groups.forEach((g, i) => perGroup[i].tickers.forEach(t => {
            mTickers.add(t);
            const cap = g.weights?.[t];
            if (cap && cap > (mWeights[t] || 0)) mWeights[t] = cap;
        }));
        const allHaveWeights = groups.every(g => g.weights && Object.keys(g.weights).length > 0);
        const market = {
            key: MARKET_ROW, label: 'Market', sub: `${mTickers.size} stocks`,
            values: rowSeries(metric, Array.from(mTickers), allHaveWeights ? mWeights : undefined, cd, mc, calcDays),
        };
        return { days, rows: [toRow(market), ...perGroup.map(toRow)] };
    }, [groups, intervalWeights, minDate, maxDate, span, metric]);

    // color: percentile 50 = neutral grey, 100 = full green (CD), 0 = full red (MC)
    const band = (p: number) => PCT_BANDS.find(b => p <= b.max) ?? PCT_BANDS[PCT_BANDS.length - 1];
    const pctColor = (p: number) => band(p).color;
    const zoneOf = (p: number) => band(p).label;
    const isExtreme = (p: number) => p <= 1 || p >= 99;
    const fmtPct = (p: number) => (p >= 95 || p <= 5) ? p.toFixed(1) : String(Math.round(p));

    if (groups.length === 0) return null;
    const avg = (vals: number[], n: number) => { const s = vals.slice(-n); return s.length ? s.reduce((a, b) => a + b, 0) / s.length : 0; };
    const fmt = (v: number) => `${v > 0 ? '+' : ''}${v.toFixed(Math.abs(v) >= 10 ? 0 : 1)}`;
    const labelEvery = Math.max(1, Math.round(days.length / 8));

    return (
        <div className="rounded-lg border bg-card p-3">
            <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
                <div>
                    <h3 className="text-base font-semibold">Market Trend</h3>
                    <p className="text-xs text-muted-foreground">
                        <span title={METRICS.find(m => m.key === metric)!.desc}>{metric === 'breadth' ? 'Breadth Score' : 'Market-cap weighted score'} per day</span> as a percentile of the Date Filters range (like the gauges) · click a name for the latest stock heatmap, a day for that day's
                    </p>
                </div>
                <div className="flex items-center gap-3">
                    <div className="flex rounded-md border border-input overflow-hidden text-xs">
                        {METRICS.map(m => (
                            <button key={m.key} onClick={() => chooseMetric(m.key)} title={m.desc}
                                className={cn("px-2.5 py-1", metric === m.key ? "bg-primary text-primary-foreground" : "hover:bg-muted")}>{m.label}</button>
                        ))}
                    </div>
                    <div className="flex rounded-md border border-input overflow-hidden text-xs">
                        {SPANS.map(s => (
                            <button key={s.days} onClick={() => setSpan(s.days)}
                                className={cn("px-2.5 py-1", span === s.days ? "bg-primary text-primary-foreground" : "hover:bg-muted")}>{s.label}</button>
                        ))}
                    </div>
                    <div className="flex items-center text-[10px] font-medium">
                        {PCT_BANDS.map(b => (
                            <span key={b.max} title={b.label} className={cn("px-1.5 py-0.5", b.max === 100 ? "text-black" : "text-white")}
                                style={{ background: b.color, boxShadow: b.max <= 1 || b.max === 100 ? 'inset 0 2px 0 #fff' : undefined }}>{b.legend}</span>
                        ))}
                    </div>
                </div>
            </div>

            <div className="grid gap-y-[3px] items-center" style={{ gridTemplateColumns: 'minmax(90px, max-content) 1fr 56px 56px' }}>
                <span />
                <div className="relative h-4 text-[10px] text-muted-foreground">
                    {days.map((d, i) => (i % labelEvery === 0 || i === days.length - 1) && (
                        <span key={d} className="absolute -translate-x-1/2 whitespace-nowrap" style={{ left: `${((i + 0.5) / days.length) * 100}%` }}>{d.slice(5)}</span>
                    ))}
                </div>
                <span className="text-[10px] text-muted-foreground text-right">Last</span>
                <span className="text-[10px] text-muted-foreground text-right">5D avg</span>

                {rows.map(r => {
                    const isMarket = r.key === MARKET_ROW;
                    const open = isMarket ? selected.length === groups.length : selected.includes(r.key);
                    const last = r.values[r.values.length - 1] ?? 50;
                    const a5 = avg(r.values, 5);
                    return (
                        <React.Fragment key={r.key}>
                            <button
                                onClick={() => isMarket ? onSelectAll() : onToggle(r.key)}
                                className={cn("text-left pr-3 text-xs leading-tight rounded px-1 py-0.5",
                                    open ? "bg-primary/10 text-primary" : "hover:bg-muted", isMarket && "font-semibold")}
                            >
                                <span className={cn(isMarket ? "text-sm" : "font-medium")}>{r.label}</span>
                                <span className="block text-[10px] text-muted-foreground">{r.sub}</span>
                            </button>
                            <div
                                className={cn("flex cursor-pointer rounded-sm overflow-hidden", isMarket ? "h-9" : "h-6", open && "ring-2 ring-primary")}
                                onMouseLeave={() => setHover(null)}
                            >
                                {r.values.map((v, i) => (
                                    <div key={days[i]} className="flex-1 min-w-0 hover:brightness-125"
                                        style={{
                                            background: pctColor(v),
                                            // white top tick marks the extreme 1% days
                                            boxShadow: days[i] === pickedDate ? 'inset 0 0 0 2px #fff, inset 0 0 0 3px #000'
                                                : isExtreme(v) ? 'inset 0 3px 0 #fff, inset -0.5px 0 0 rgba(0,0,0,0.25)' : 'inset -0.5px 0 0 rgba(0,0,0,0.25)',
                                        }}
                                        onClick={() => onPickDay(r.key, days[i])}
                                        onMouseMove={e => setHover({ row: r.label, date: days[i], value: v, raw: r.raw[i], x: e.clientX, y: e.clientY })} />
                                ))}
                            </div>
                            <span className="text-xs font-semibold text-right tabular-nums" style={{ color: last >= 90 ? '#16a34a' : last <= 10 ? '#dc2626' : undefined }}>{fmtPct(last)}</span>
                            <span className="text-xs text-right tabular-nums" style={{ color: a5 >= 90 ? '#16a34a' : a5 <= 10 ? '#dc2626' : undefined }}>{fmtPct(a5)}</span>
                        </React.Fragment>
                    );
                })}
            </div>

            {hover && (
                <div className="fixed z-[200] pointer-events-none bg-background border border-border rounded shadow-lg px-2 py-1 text-xs"
                    style={{ left: hover.x + 14, top: hover.y + 14 }}>
                    <span className="font-semibold">{hover.row}</span> <span className="text-muted-foreground">{hover.date}</span>
                    <span className="ml-2 font-semibold" style={{ color: hover.value >= 90 ? '#16a34a' : hover.value <= 10 ? '#dc2626' : undefined }}>{fmtPct(hover.value)} · {zoneOf(hover.value)}</span>
                    <span className="ml-2 text-muted-foreground">(score {fmt(hover.raw)})</span>
                </div>
            )}
        </div>
    );
};

export default MarketTrendGrid;
