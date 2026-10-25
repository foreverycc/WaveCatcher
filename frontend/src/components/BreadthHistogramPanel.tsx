import React, { useEffect, useMemo, useRef, useState } from 'react';
import { breadthShare, breadthScore, capWeightedScore, denomAt, listedCount, type CapHistory, type CompanyBreadthPoint, type FirstDates, type ValuePoint } from '../utils/marketBreadth';
import { Maximize2, Minimize2 } from 'lucide-react';
import { cn } from '../utils/cn';
import { pctBand } from './MarketTrendGrid';

interface HistogramData {
    label: string;
    values: number[];   // All daily values for the distribution
    today: number;      // Current / latest day's value
    color: 'green' | 'red';
    unit?: string;
}

// Share of days at or below a value (0-100)
const computePercentile = (value: number, sorted: number[]): number => {
    if (sorted.length === 0) return 0;
    const count = sorted.filter(v => v <= value).length;
    return (count / sorted.length) * 100;
};

const fmt = (v: number) => {
    const a = Math.abs(v);
    return a === 0 ? '0' : a < 1 ? v.toFixed(2) : a < 10 ? v.toFixed(1) : v.toFixed(0);
};

const SERIES = {
    green: { solid: '#16a34a', soft: 'fill-green-600/25 dark:fill-green-500/50', text: 'text-green-600 dark:text-green-400' },
    red: { solid: '#dc2626', soft: 'fill-red-600/20 dark:fill-red-500/45', text: 'text-red-600 dark:text-red-400' },
};

/** width of an element, kept up to date */
function useWidth<T extends HTMLElement>() {
    const ref = useRef<T>(null);
    const [w, setW] = useState(0);
    useEffect(() => {
        const el = ref.current;
        if (!el) return;
        const ro = new ResizeObserver(([e]) => setW(e.contentRect.width));
        ro.observe(el);
        return () => ro.disconnect();
    }, []);
    return [ref, w] as const;
}

/**
 * Histogram of the daily values in the range: bars on a square-root scale (the many quiet days do
 * not flatten the rest), the marked day as a solid bar with a pin at its exact value, median dashed.
 */
const MiniHistogram = ({ data, height = 140, isFullscreen = false }: { data: HistogramData; height?: number; isFullscreen?: boolean }) => {
    const [boxRef, width] = useWidth<HTMLDivElement>();
    const [hover, setHover] = useState<number | null>(null);
    const computed = useMemo(() => {
        const { values, today } = data;
        if (values.length === 0) return null;
        const sorted = [...values].sort((x, y) => x - y);
        const min = sorted[0];
        const max = Math.max(sorted[sorted.length - 1], today);
        const range = max - min || 1;
        const numBins = Math.min(24, Math.max(10, Math.ceil(Math.sqrt(values.length) * 1.3)));
        const binWidth = range / numBins;
        const bins = Array.from({ length: numBins }, (_, i) => ({ start: min + i * binWidth, end: min + (i + 1) * binWidth, count: 0 }));
        const binOf = (v: number) => Math.min(numBins - 1, Math.max(0, Math.floor((v - min) / binWidth)));
        values.forEach(v => { bins[binOf(v)].count++; });
        const avg = values.reduce((x, y) => x + y, 0) / values.length;
        const mid = sorted.length / 2;
        const median = sorted.length % 2 === 0 ? (sorted[mid - 1] + sorted[mid]) / 2 : sorted[Math.floor(mid)];
        return { bins, min, range, avg, median, todayBin: binOf(today), percentile: computePercentile(today, sorted), maxCount: Math.max(...bins.map(x => x.count), 1), n: values.length };
    }, [data]);

    const colors = SERIES[data.color];
    const u = data.unit ?? '';
    if (!computed) return <div className="text-xs text-muted-foreground text-center py-2">No data</div>;
    const { bins, min, range, avg, median, todayBin, percentile, maxCount, n } = computed;

    // geometry
    const padTop = 16, padBottom = 18, padX = 4;
    const plotW = Math.max(0, width - padX * 2);
    const plotH = height - padTop - padBottom;
    const xOf = (v: number) => padX + ((v - min) / range) * plotW;
    const bw = plotW / bins.length;
    const gap = Math.min(2, bw * 0.2);
    const hOf = (c: number) => c === 0 ? 0 : Math.max(2, Math.sqrt(c / maxCount) * plotH);
    const baseY = padTop + plotH;
    const ticks = [min, min + range / 2, min + range];
    const pinX = xOf(data.today);
    const medX = xOf(median);
    // badge in the Market Trend colors: a high CD percentile is the green end, a high MC percentile the red end
    const band = pctBand(data.color === 'green' ? Math.max(50, percentile) : Math.min(50, 100 - percentile));
    const neutral = band.max === 75;
    const extreme = band.max <= 1 || band.max === 100;
    const hb = hover != null ? bins[hover] : null;

    return (
        <div className="w-full">
            <div className="flex items-baseline justify-between gap-2 px-0.5 mb-0.5">
                <span className="flex items-baseline gap-2 min-w-0">
                    <span className={cn(isFullscreen ? "text-sm" : "text-xs", "font-semibold", colors.text)}>{data.label}</span>
                    <span className="text-[10px] text-muted-foreground tabular-nums truncate">avg {fmt(avg)}{u} · {n} days</span>
                </span>
                <span className="flex items-baseline gap-2 text-[11px] text-muted-foreground tabular-nums">
                    <span>marked <span className={cn("text-sm font-semibold", colors.text)}>{fmt(data.today)}{u}</span></span>
                    <span className={cn("rounded px-1.5 py-px text-[10px] font-semibold", neutral ? "bg-muted text-foreground" : band.max === 100 ? "text-black" : "text-white")}
                        style={neutral ? undefined : { background: band.color, boxShadow: extreme ? 'inset 0 2px 0 #fff' : undefined }}
                        title={`Share of days in the range at or below the marked day · ${neutral ? 'Neutral' : band.label}`}>
                        P{percentile.toFixed(0)}
                    </span>
                </span>
            </div>
            <div ref={boxRef} className="relative w-full" style={{ height }} onMouseLeave={() => setHover(null)}>
                {width > 0 && (
                    <svg width={width} height={height} className="block overflow-visible">
                        {/* bars */}
                        {bins.map((bin, i) => {
                            const h = hOf(bin.count);
                            const isMarked = i === todayBin;
                            return (
                                <g key={i} onMouseEnter={() => setHover(i)}>
                                    <rect x={padX + i * bw} y={padTop} width={bw} height={plotH} fill="transparent" />
                                    {h > 0 && (
                                        <rect x={padX + i * bw + gap / 2} y={baseY - h} width={Math.max(1, bw - gap)} height={h} rx={Math.min(3, bw / 4)}
                                            fill={isMarked ? colors.solid : undefined} className={isMarked ? undefined : colors.soft}
                                            opacity={hover != null && hover !== i && !isMarked ? 0.7 : 1} />
                                    )}
                                </g>
                            );
                        })}
                        {/* baseline */}
                        <line x1={padX} x2={padX + plotW} y1={baseY + 0.5} y2={baseY + 0.5} stroke="hsl(var(--border))" />
                        {/* median */}
                        <line x1={medX} x2={medX} y1={padTop - 2} y2={baseY} stroke="hsl(var(--muted-foreground))" strokeWidth={1} strokeDasharray="3 3" pointerEvents="none" />
                        <text x={medX} y={padTop - 5} textAnchor={medX > width - 40 ? 'end' : medX < 40 ? 'start' : 'middle'} fontSize={9} fill="hsl(var(--muted-foreground))" pointerEvents="none">med {fmt(median)}{u}</text>
                        {/* marked day pointer */}
                        <path d={`M${pinX - 4},${baseY + 6} L${pinX + 4},${baseY + 6} L${pinX},${baseY + 1} Z`} fill={colors.solid} pointerEvents="none" />
                        {/* x ticks */}
                        {ticks.map((t, i) => (
                            <text key={i} x={xOf(t)} y={height - 3} fontSize={10} fill="hsl(var(--muted-foreground))"
                                textAnchor={i === 0 ? 'start' : i === ticks.length - 1 ? 'end' : 'middle'}>{fmt(t)}{u}</text>
                        ))}
                    </svg>
                )}
                {hb && (
                    <div className="absolute z-10 pointer-events-none bg-popover text-popover-foreground border border-border rounded px-2 py-1 text-xs shadow-md whitespace-nowrap"
                        style={{ left: Math.min(Math.max(0, padX + (hover! + 0.5) * bw - 60), Math.max(0, width - 130)), top: 0 }}>
                        <div className="tabular-nums">{fmt(hb.start)}{u} – {fmt(hb.end)}{u}</div>
                        <div className="text-muted-foreground tabular-nums">{hb.count} day{hb.count === 1 ? '' : 's'} ({((hb.count / n) * 100).toFixed(0)}%)</div>
                        {hover === todayBin && <div className={cn("font-semibold", colors.text)}>marked day</div>}
                    </div>
                )}
            </div>
        </div>
    );
};

// Props match what IndexSummaryCard has available
interface BreadthHistogramPanelProps {
    title: string;
    cdSignalBreadth: { date: string; count_1h: number; count_2h: number; count_3h: number; count_4h: number; count_1d: number }[];
    mcSignalBreadth: { date: string; count_1h: number; count_2h: number; count_3h: number; count_4h: number; count_1d: number }[];
    cdScoreBreadth: { date: string; score_1h: number; score_2h: number; score_3h: number; score_4h: number; score_1d: number; total_score: number }[];
    mcScoreBreadth: { date: string; score_1h: number; score_2h: number; score_3h: number; score_4h: number; score_1d: number; total_score: number }[];
    cdCompanyBreadth?: CompanyBreadthPoint[];
    mcCompanyBreadth?: CompanyBreadthPoint[];
    intervalWeights?: Record<string, number>;
    tickers: string[];
    /** first trading day of recently listed stocks: they only count from then on */
    firstDates?: FirstDates;
    /** market caps of the list's stocks and their price history, for the weighted breadth score */
    tickerWeights?: Record<string, number>;
    capHistory?: CapHistory;
    filteredSpxData: any[];
    /** day to mark in each histogram (YYYY-MM-DD), e.g. the day picked in Market Trend; default = latest */
    focusDate?: string | null;
    onNavigateRight: () => void;
    onMaximize?: () => void;
    isFullscreen?: boolean;
}

export const BreadthHistogramPanel: React.FC<BreadthHistogramPanelProps> = ({
    title,
    cdSignalBreadth,
    mcSignalBreadth,
    cdScoreBreadth,
    mcScoreBreadth,
    cdCompanyBreadth = [],
    mcCompanyBreadth = [],
    intervalWeights,
    tickers,
    firstDates,
    filteredSpxData,
    tickerWeights,
    capHistory,
    focusDate,
    onNavigateRight,
    onMaximize,
    isFullscreen = false,
}) => {
    // stocks already trading each day (a recent listing does not dilute the days before it)
    const divisor = listedCount(tickers, firstDates);
    const effectiveWeights = intervalWeights || { '1h': 1, '2h': 2, '3h': 4, '4h': 8, '1d': 32 };

    const lastDay = filteredSpxData && filteredSpxData.length > 0
        ? filteredSpxData[filteredSpxData.length - 1]?.time?.split('T')[0] ?? ''
        : '';
    // the marked day: the picked one when it is inside the range, else the latest
    const latestDate = focusDate && focusDate <= lastDay
        && (filteredSpxData || []).some((d: any) => d.time?.split('T')[0] === focusDate) ? focusDate : lastDay;
    const totalDays = filteredSpxData ? filteredSpxData.length : 0;

    const countValues = (data: { count_1h: number; count_2h: number; count_3h: number; count_4h: number; count_1d: number; date: string }[]) => {
        const totalCount = (d: typeof data[0]) => ((d.count_1h || 0) + (d.count_2h || 0) + (d.count_3h || 0) + (d.count_4h || 0) + (d.count_1d || 0)) / denomAt(divisor, d.date);
        const vals = data.map(d => totalCount(d));
        const todayEntry = data.find(d => d.date === latestDate);
        const today = todayEntry ? totalCount(todayEntry) : 0;
        return { values: vals, today };
    };

    const scoreValues = (data: { score_1h: number; score_2h: number; score_3h: number; score_4h: number; score_1d: number; date: string }[]) => {
        const totalScore = (d: typeof data[0]) => {
            return ((d.score_1h || 0) * effectiveWeights['1h'] + (d.score_2h || 0) * effectiveWeights['2h']
                + (d.score_3h || 0) * effectiveWeights['3h'] + (d.score_4h || 0) * effectiveWeights['4h']
                + (d.score_1d || 0) * effectiveWeights['1d']) / denomAt(divisor, d.date);
        };
        const vals = data.map(d => totalScore(d));
        const todayEntry = data.find(d => d.date === latestDate);
        const today = todayEntry ? totalScore(todayEntry) : 0;
        return { values: vals, today };
    };

    const histograms = useMemo(() => {
        const cdSignal = countValues(cdSignalBreadth);
        const mcSignal = countValues(mcSignalBreadth);
        const cdScore = scoreValues(cdScoreBreadth);
        const mcScore = scoreValues(mcScoreBreadth);
        // Market breadth (% of companies with a signal) and breadth score (Score x share)
        const seriesValues = (rows: ValuePoint[], scale = 1) => {
            const today = rows.find(r => r.date === latestDate);
            return { values: rows.map(r => r.value * scale), today: today ? today.value * scale : 0 };
        };
        const cdBt = seriesValues(breadthShare(cdCompanyBreadth, divisor), 100);
        const mcBt = seriesValues(breadthShare(mcCompanyBreadth, divisor), 100);
        const cdBtScore = seriesValues(breadthScore(cdCompanyBreadth, cdScoreBreadth, effectiveWeights, divisor));
        const mcBtScore = seriesValues(breadthScore(mcCompanyBreadth, mcScoreBreadth, effectiveWeights, divisor));
        // Weighted breadth score: each stock's score x its market-cap share (as in the Market Breadth chart)
        const weighted = (rows: CompanyBreadthPoint[]) => {
            const m = capWeightedScore(rows, tickerWeights, tickers, effectiveWeights, firstDates, capHistory);
            return seriesValues(Array.from(m, ([date, value]) => ({ date, value })));
        };
        const cdW = weighted(cdCompanyBreadth);
        const mcW = weighted(mcCompanyBreadth);

        const pad = (vals: number[]) => {
            const zeroPadding = new Array(Math.max(0, totalDays - vals.length)).fill(0);
            return [...vals, ...zeroPadding];
        };

        return [
            {
                section: 'CD/MC', items: [
                    { label: 'CD', values: cdSignal.values, today: cdSignal.today, color: 'green' as const },
                    { label: 'MC', values: mcSignal.values, today: mcSignal.today, color: 'red' as const },
                ]
            },
            {
                section: 'CD/MC Score', items: [
                    { label: 'CD', values: cdScore.values, today: cdScore.today, color: 'green' as const },
                    { label: 'MC', values: mcScore.values, today: mcScore.today, color: 'red' as const },
                ]
            },
            {
                section: 'Market Breadth (% of companies)', items: [
                    { label: 'CD', values: pad(cdBt.values), today: cdBt.today, color: 'green' as const, unit: '%' },
                    { label: 'MC', values: pad(mcBt.values), today: mcBt.today, color: 'red' as const, unit: '%' },
                ]
            },
            {
                section: 'Breadth Score', items: [
                    { label: 'CD', values: pad(cdBtScore.values), today: cdBtScore.today, color: 'green' as const },
                    { label: 'MC', values: pad(mcBtScore.values), today: mcBtScore.today, color: 'red' as const },
                ]
            },
            {
                section: 'Weighted Breadth Score (market-cap weighted)', items: [
                    { label: 'CD', values: pad(cdW.values), today: cdW.today, color: 'green' as const },
                    { label: 'MC', values: pad(mcW.values), today: mcW.today, color: 'red' as const },
                ]
            },
        ];
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [cdSignalBreadth, mcSignalBreadth, cdScoreBreadth, mcScoreBreadth, cdCompanyBreadth, mcCompanyBreadth, tickers, firstDates, filteredSpxData, intervalWeights, latestDate, tickerWeights, capHistory]);

    const histogramHeight = isFullscreen ? 140 : 110;

    return (
        <div className="h-full flex flex-col overflow-hidden">
            {/* Header */}
            <div className="p-2 border-b bg-muted/30 flex justify-between items-center shrink-0">
                <span className="text-sm font-medium">{title} — Distributions
                    {latestDate && <span className={cn("ml-2 text-xs font-normal", latestDate !== lastDay ? "text-primary" : "text-muted-foreground")}>marked day: {latestDate}</span>}
                </span>
                <div className="flex items-center gap-2">
                    {onMaximize && (
                        <button
                            onClick={onMaximize}
                            className="p-2 text-muted-foreground hover:text-foreground rounded-md hover:bg-muted/50 transition-colors"
                            title={isFullscreen ? "Restore" : "Maximize"}
                        >
                            {isFullscreen ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
                        </button>
                    )}
                    <button
                        onClick={onNavigateRight}
                        className="text-xs text-muted-foreground hover:text-foreground transition-colors"
                    >
                        Market Breadth →
                    </button>
                </div>
            </div>

            {/* Histograms grid — 2 per row */}
            <div className="flex-1 overflow-y-auto p-3">
                <div className="grid grid-cols-2 gap-x-6 gap-y-2">
                    {histograms.map((section) => (
                        <React.Fragment key={section.section}>
                            <div className="col-span-2 text-xs font-semibold text-muted-foreground mt-2 mb-0.5 border-b border-border/40 pb-1">
                                {section.section}
                            </div>
                            {section.items.map((item) => (
                                <div key={item.label}>
                                    <MiniHistogram data={item} height={histogramHeight} isFullscreen={isFullscreen} />
                                </div>
                            ))}
                        </React.Fragment>
                    ))}
                </div>
            </div>
        </div>
    );
};
