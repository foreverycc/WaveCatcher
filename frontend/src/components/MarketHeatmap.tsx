import React, { useMemo, useState } from 'react';
import { cn } from '../utils/cn';
import { denomAt, listedCount, listedOn, weightOnDay, type CapHistory, type CompanyBreadthPoint, type FirstDates } from '../utils/marketBreadth';

/**
 * Finviz-style market heatmap. One block per index / sector; inside it every stock is a tile
 * sized by market cap (equal size when no market caps are stored) and colored by its net signal
 * score over the chosen window: CD score - MC score, each interval-weighted. Green = CD, red = MC.
 * Clicking a block opens that index's card (Market Breadth / Distributions).
 */

export interface HeatmapGroup {
    key: string;
    symbol: string;
    tickers: string[];
    weights?: Record<string, number>;
    cdCompanyBreadth: CompanyBreadthPoint[];
    mcCompanyBreadth: CompanyBreadthPoint[];
    /** trading days of the index (YYYY-MM-DD), used for the lookback window */
    tradingDays: string[];
    /** first trading day of recently listed stocks: they only count from then on */
    firstDates?: FirstDates;
    /** price history for weights at each day's market cap */
    capHistory?: CapHistory;
    /** the index's own signals by day (YYYY-MM-DD): CD / MC on its daily chart and 1234 signals */
    marks?: Record<string, DayMarks>;
}

export interface DayMarks { cd?: boolean; mc?: boolean; cd1234?: boolean; mc1234?: boolean }

interface Props {
    groups: HeatmapGroup[];
    intervalWeights: Record<string, number>;
    /** last day to include (YYYY-MM-DD), from the date filter */
    maxDate?: string;
    /** show this day instead of the latest one (YYYY-MM-DD) */
    date?: string | null;
    onClearDate?: () => void;
    expanded: string[];
    onToggle: (key: string) => void;
    /** from Market Trend: 'breadth' sizes stocks equally and heads each block with its Breadth Score,
     *  'weighted' sizes by market cap and heads with the cap-weighted score */
    metrics?: ('breadth' | 'weighted')[];
}

const WINDOWS = [
    { label: '1D', days: 1 },
    { label: '5D', days: 5 },
    { label: '20D', days: 20 },
];

// Finviz palette: -3 .. 0 .. +3
const NEG = ['#414554', '#8b444e', '#bf4045', '#f63538'];
const POS = ['#414554', '#35764e', '#2f9e4f', '#30cc5a'];

function hexToRgb(h: string) {
    const n = parseInt(h.slice(1), 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

export function colorFor(v: number, scale: number) {
    const t = Math.max(-1, Math.min(1, scale > 0 ? v / scale : 0));
    const stops = t >= 0 ? POS : NEG;
    const x = Math.abs(t) * (stops.length - 1);
    const i = Math.min(stops.length - 2, Math.floor(x));
    const f = x - i;
    const a = hexToRgb(stops[i]), b = hexToRgb(stops[i + 1]);
    const c = a.map((ai, k) => Math.round(ai + (b[k] - ai) * f));
    return `rgb(${c[0]},${c[1]},${c[2]})`;
}

interface Rect { x: number; y: number; w: number; h: number }
type IntervalScores = Record<string, number>; // interval -> interval-weighted score in the window
interface Item {
    ticker: string; size: number; value: number; cd: number; mc: number; cap?: number;
    cdIntervals: IntervalScores; mcIntervals: IntervalScores;
}
const INTERVAL_ORDER = ['1h', '2h', '3h', '4h', '1d'];
const intervalList = (m: IntervalScores) => INTERVAL_ORDER.filter(k => k in m);

/** Squarified treemap layout (Bruls et al.) of items sorted by size, in a w x h box. */
function squarify<T extends { size: number }>(items: T[], w: number, h: number): (T & Rect)[] {
    const total = items.reduce((s, it) => s + it.size, 0);
    if (total <= 0 || w <= 0 || h <= 0) return [];
    const scale = (w * h) / total;
    const out: (T & Rect)[] = [];
    let box = { x: 0, y: 0, w, h };
    let row: T[] = [];
    const worst = (r: T[], side: number) => {
        const areas = r.map(it => it.size * scale);
        const s = areas.reduce((a, b) => a + b, 0);
        const max = Math.max(...areas), min = Math.min(...areas);
        return Math.max((side * side * max) / (s * s), (s * s) / (side * side * min));
    };
    const layoutRow = (r: T[]) => {
        const s = r.reduce((a, it) => a + it.size * scale, 0);
        if (box.w >= box.h) {
            const cw = s / box.h;
            let y = box.y;
            r.forEach(it => { const ch = (it.size * scale) / cw; out.push({ ...it, x: box.x, y, w: cw, h: ch }); y += ch; });
            box = { x: box.x + cw, y: box.y, w: box.w - cw, h: box.h };
        } else {
            const ch = s / box.w;
            let x = box.x;
            r.forEach(it => { const cw = (it.size * scale) / ch; out.push({ ...it, x, y: box.y, w: cw, h: ch }); x += cw; });
            box = { x: box.x, y: box.y + ch, w: box.w, h: box.h - ch };
        }
    };
    for (const it of items) {
        const side = Math.min(box.w, box.h);
        if (row.length === 0 || worst([...row, it], side) <= worst(row, side)) {
            row.push(it);
        } else {
            layoutRow(row);
            row = [it];
        }
    }
    if (row.length) layoutRow(row);
    return out;
}

const fmtCap = (v?: number) => v == null ? '–' : v >= 1e12 ? `$${(v / 1e12).toFixed(2)}T` : v >= 1e9 ? `$${(v / 1e9).toFixed(1)}B` : `$${(v / 1e6).toFixed(0)}M`;

const BLOCK_W = 1000; // layout units; tiles are positioned in % of the block
const BLOCK_H = 620;

export const MarketHeatmap: React.FC<Props> = ({ groups, intervalWeights, maxDate, date, onClearDate, expanded, onToggle, metrics = ['weighted'] }) => {
    const [windowDays, setWindowDays] = useState(1);
    const [hover, setHover] = useState<{ item: Item; group: string; x: number; y: number } | null>(null);

    const blocks = useMemo(() => {
        const maxStr = date || maxDate;
        return groups.map(g => {
            // window = last N trading days up to the filter end date
            let days = g.tradingDays.filter(d => !maxStr || d <= maxStr);
            if (days.length === 0) {
                days = Array.from(new Set([...g.cdCompanyBreadth, ...g.mcCompanyBreadth].map(c => c.date)))
                    .filter(d => !maxStr || d <= maxStr).sort();
            }
            const inWindow = new Set(days.slice(-windowDays));
            // per ticker: total interval-weighted score and the score of each interval that fired
            const sum = (rows: CompanyBreadthPoint[]) => {
                const m = new Map<string, number>();
                const byTicker = new Map<string, IntervalScores>();
                rows.forEach(c => {
                    if (!inWindow.has(c.date) || !c.scores) return;
                    Object.entries(c.scores).forEach(([t, byIntv]) => {
                        let s = 0;
                        const iv = byTicker.get(t) || {};
                        Object.entries(byIntv).forEach(([k, v]) => {
                            const ws = v * (intervalWeights[k] ?? 0);
                            s += ws;
                            iv[k] = (iv[k] || 0) + ws;
                        });
                        byTicker.set(t, iv);
                        m.set(t, (m.get(t) || 0) + s);
                    });
                });
                return { m, byTicker };
            };
            const { m: cd, byTicker: cdIv } = sum(g.cdCompanyBreadth);
            const { m: mc, byTicker: mcIv } = sum(g.mcCompanyBreadth);
            const hasWeights = !!g.weights && Object.keys(g.weights).length > 0;
            const byCap = metrics.includes('weighted') && hasWeights;
            const lastDay = days[days.length - 1];
            // market cap on the shown day (today's cap x price then / price now)
            const capOn = weightOnDay(hasWeights ? g.weights : undefined, g.capHistory);
            const items: Item[] = Array.from(new Set(g.tickers.map(t => t.toUpperCase())))
                // a stock listed after the shown day is left out of that day's map
                .filter(t => !lastDay || listedOn(g.firstDates, t, lastDay))
                .map(t => {
                    const cap = g.weights?.[t] == null ? undefined : lastDay ? capOn(t, lastDay) : g.weights[t];
                    return {
                        ticker: t, cap, size: byCap ? (cap || 0) : 1, cd: cd.get(t) || 0, mc: mc.get(t) || 0,
                        value: (cd.get(t) || 0) - (mc.get(t) || 0), cdIntervals: cdIv.get(t) || {}, mcIntervals: mcIv.get(t) || {},
                    };
                })
                .filter(it => it.size > 0)
                .sort((a, b) => b.size - a.size);
            // Weighted: cap-weighted net score; Breadth: daily CD Score x CD share - MC Score x MC share, summed over the window
            const capOf = (it: Item) => hasWeights ? (it.cap || 0) : 1;
            const capTotal = items.reduce((s, it) => s + capOf(it), 0);
            const weighted = capTotal > 0 ? items.reduce((s, it) => s + it.value * capOf(it), 0) / capTotal : 0;
            const listSet = new Set(items.map(it => it.ticker));
            const count = listedCount(Array.from(listSet), g.firstDates);
            const dailySide = (rows: CompanyBreadthPoint[]) => {
                let total = 0;
                rows.forEach(c => {
                    if (!inWindow.has(c.date)) return;
                    let sum = 0, cnt = 0;
                    (c.tickers || []).forEach(t => {
                        if (!listSet.has(t)) return;
                        cnt += 1;
                        Object.entries(c.scores?.[t] || {}).forEach(([k, v]) => { sum += v * (intervalWeights[k] ?? 0); });
                    });
                    const n = denomAt(count, c.date);
                    total += (sum / n) * (cnt / n);
                });
                return total;
            };
            const breadth = dailySide(g.cdCompanyBreadth) - dailySide(g.mcCompanyBreadth);
            const hasScores = [...g.cdCompanyBreadth, ...g.mcCompanyBreadth].some(c => c.scores);
            return { group: g, items, weighted, breadth, byCap, hasScores, hasWeights, lastDay, rects: squarify(items, BLOCK_W, BLOCK_H) };
        });
    }, [groups, intervalWeights, maxDate, date, windowDays, metrics]);

    // One color scale for all blocks: 90th percentile of |net score| among stocks with a signal
    const scale = useMemo(() => {
        const vals = blocks.flatMap(b => b.items.map(it => Math.abs(it.value))).filter(v => v > 0).sort((a, b) => a - b);
        return vals.length ? Math.max(1, vals[Math.floor(vals.length * 0.9)]) : 1;
    }, [blocks]);

    if (groups.length === 0) return null;
    const shownDay = blocks.map(b => b.lastDay).filter(Boolean).sort().pop();
    const missingScores = blocks.some(b => !b.hasScores);

    return (
        <div className="rounded-lg border bg-card p-3 relative">
            <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
                <div>
                    <h3 className="text-base font-semibold flex items-center gap-2">
                        Market Heatmap
                        <span className="text-xs font-normal text-muted-foreground">
                            {windowDays > 1 ? `${windowDays} trading days to ` : ''}{shownDay ?? '–'}{!date && ' (latest)'}
                        </span>
                        {date && onClearDate && (
                            <button onClick={onClearDate} className="text-[11px] font-normal px-1.5 py-0.5 rounded border border-input hover:bg-muted">Latest</button>
                        )}
                    </h3>
                    <p className="text-xs text-muted-foreground">
                        Size = {metrics.includes('weighted') ? 'market cap' : 'equal (Breadth Score)'} · Color = CD score − MC score per stock · Click an index to open its Market Breadth card
                    </p>
                </div>
                <div className="flex items-center gap-3">
                    <div className="flex rounded-md border border-input overflow-hidden text-xs">
                        {WINDOWS.map(w => (
                            <button
                                key={w.label}
                                onClick={() => setWindowDays(w.days)}
                                className={cn("px-2.5 py-1", windowDays === w.days ? "bg-primary text-primary-foreground" : "hover:bg-muted")}
                            >{w.label}</button>
                        ))}
                    </div>
                    <div className="flex items-center text-[10px] font-medium">
                        {[-1, -2 / 3, -1 / 3, 0, 1 / 3, 2 / 3, 1].map(f => (
                            <span key={f} className="px-1.5 py-0.5 text-white" style={{ background: colorFor(f * scale, scale) }}>
                                {f === 0 ? '0' : `${f > 0 ? '+' : ''}${Math.round(f * scale)}`}
                            </span>
                        ))}
                    </div>
                </div>
            </div>
            {missingScores && (
                <p className="text-xs text-amber-600 mb-2">Some indices have no per-stock scores yet; run the analysis again to color them.</p>
            )}

            <div className="grid gap-2 grid-cols-1 lg:grid-cols-2 xl:grid-cols-3">
                {blocks.map(b => {
                    const open = expanded.includes(b.group.key);
                    return (
                        <div
                            key={b.group.key}
                            className={cn("rounded-md overflow-hidden cursor-pointer border-2 transition-colors",
                                open ? "border-primary" : "border-transparent hover:border-muted-foreground/40")}
                            onClick={() => onToggle(b.group.key)}
                        >
                            <div className="flex items-center justify-between px-2 py-1 bg-[#262931] text-white text-xs">
                                <span className="font-semibold tracking-wide">
                                    {b.group.key} <span className="text-white/50 font-normal">{b.group.symbol} · {b.items.length} stocks</span>
                                </span>
                                <span className="flex items-center gap-2 font-semibold">
                                    {metrics.includes('breadth') && (
                                        <span title="Breadth Score (CD Score × CD share − MC Score × MC share)" style={{ color: b.breadth > 0 ? '#4ade80' : b.breadth < 0 ? '#f87171' : undefined }}>
                                            <span className="text-white/50 font-normal mr-1">B</span>{b.breadth >= 0 ? '+' : ''}{b.breadth.toFixed(2)}
                                        </span>
                                    )}
                                    {metrics.includes('weighted') && (
                                        <span title="Market-cap weighted score" style={{ color: b.weighted > 0 ? '#4ade80' : b.weighted < 0 ? '#f87171' : undefined }}>
                                            <span className="text-white/50 font-normal mr-1">W</span>{b.weighted >= 0 ? '+' : ''}{b.weighted.toFixed(1)}
                                        </span>
                                    )}
                                </span>
                            </div>
                            <div className="relative w-full bg-[#262931]" style={{ aspectRatio: `${BLOCK_W} / ${BLOCK_H}`, containerType: 'inline-size' }}>
                                {b.rects.map(r => {
                                    const minSide = Math.min(r.w, r.h);
                                    // font in container-width units so labels scale with the block
                                    const fontCqw = (Math.min(minSide / 3.2, r.w / (r.ticker.length * 0.75)) / BLOCK_W) * 100;
                                    return (
                                        <div
                                            key={r.ticker}
                                            className="absolute flex flex-col items-center justify-center text-white overflow-hidden leading-tight"
                                            style={{
                                                left: `${(r.x / BLOCK_W) * 100}%`, top: `${(r.y / BLOCK_H) * 100}%`,
                                                width: `${(r.w / BLOCK_W) * 100}%`, height: `${(r.h / BLOCK_H) * 100}%`,
                                                background: colorFor(r.value, scale),
                                                boxShadow: 'inset 0 0 0 0.5px #262931',
                                            }}
                                            onMouseMove={e => setHover({ item: r, group: b.group.key, x: e.clientX, y: e.clientY })}
                                            onMouseLeave={() => setHover(null)}
                                        >
                                            {fontCqw >= 1.3 && (
                                                <span className="font-bold" style={{ fontSize: `clamp(7px, ${fontCqw}cqw, 32px)` }}>{r.ticker}</span>
                                            )}
                                            {fontCqw >= 2.4 && (
                                                <span style={{ fontSize: `clamp(7px, ${fontCqw * 0.55}cqw, 18px)` }}>
                                                    {r.value === 0 ? '0' : `${r.value > 0 ? '+' : ''}${r.value.toFixed(0)}`}
                                                </span>
                                            )}
                                            {fontCqw >= 2.4 && (intervalList(r.cdIntervals).length > 0 || intervalList(r.mcIntervals).length > 0) && (
                                                <span className="opacity-90 whitespace-nowrap" style={{ fontSize: `clamp(7px, ${fontCqw * 0.42}cqw, 13px)` }}>
                                                    {intervalList(r.cdIntervals).length > 0 && <>CD {intervalList(r.cdIntervals).join(' ')}</>}
                                                    {intervalList(r.cdIntervals).length > 0 && intervalList(r.mcIntervals).length > 0 && ' · '}
                                                    {intervalList(r.mcIntervals).length > 0 && <>MC {intervalList(r.mcIntervals).join(' ')}</>}
                                                </span>
                                            )}
                                        </div>
                                    );
                                })}
                                {metrics.includes('weighted') && !b.hasWeights && (
                                    <span className="absolute bottom-1 right-1 text-[9px] text-white/60 pointer-events-none">equal size (no market caps yet)</span>
                                )}
                            </div>
                        </div>
                    );
                })}
            </div>

            {hover && (
                <div
                    className="fixed z-[200] pointer-events-none bg-background border border-border rounded shadow-lg p-2 text-xs min-w-[160px]"
                    style={{ left: hover.x + 14, top: hover.y + 14 }}
                >
                    <div className="font-semibold mb-1">{hover.item.ticker} <span className="text-muted-foreground font-normal">({hover.group})</span></div>
                    <div className="grid grid-cols-2 gap-x-3">
                        <span className="text-muted-foreground">Market cap</span><span className="text-right">{fmtCap(hover.item.cap)}</span>
                        <span className="text-muted-foreground">CD score</span><span className="text-right text-green-500">{hover.item.cd.toFixed(1)}</span>
                        <span className="text-muted-foreground">MC score</span><span className="text-right text-red-500">{hover.item.mc.toFixed(1)}</span>
                        <span className="text-muted-foreground font-semibold">Net</span><span className="text-right font-semibold">{hover.item.value.toFixed(1)}</span>
                    </div>
                    {(['cd', 'mc'] as const).map(side => {
                        const iv = side === 'cd' ? hover.item.cdIntervals : hover.item.mcIntervals;
                        const list = intervalList(iv);
                        if (list.length === 0) return null;
                        return (
                            <div key={side} className="mt-1.5">
                                <div className={cn("font-semibold", side === 'cd' ? "text-green-500" : "text-red-500")}>{side.toUpperCase()} intervals</div>
                                <div className="grid grid-cols-2 gap-x-3">
                                    {list.map(k => (
                                        <React.Fragment key={k}>
                                            <span className="text-muted-foreground">{k}</span><span className="text-right">{iv[k].toFixed(1)}</span>
                                        </React.Fragment>
                                    ))}
                                </div>
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );
};

export default MarketHeatmap;
