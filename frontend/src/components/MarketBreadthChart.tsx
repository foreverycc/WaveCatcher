import React, { useMemo, useRef, useState, useCallback, useEffect } from 'react';
import {
    ComposedChart,
    Bar,
    Cell,
    Line,
    Scatter,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,

    ResponsiveContainer,
    ReferenceArea
} from 'recharts';
import { format } from 'date-fns';

interface BreadthDataPoint {
    date: string;
    count_1h: number;
    count_2h: number;
    count_3h: number;
    count_4h: number;
    count_1d: number;
}

interface SignalBreadthDataPoint {
    date: string;
    count_1h: number;
    count_2h: number;
    count_3h: number;
    count_4h: number;
    count_1d: number;
}

const CandleShape = (props: any) => {
    const { x, y, width, height } = props;
    const { payload } = props;
    if (!payload || !payload.open || !payload.close || !payload.high || !payload.low) return null;

    const { open: openVal, close: closeVal, high: highVal, low: lowVal } = payload;

    const isUp = closeVal >= openVal;
    const color = isUp ? '#22c55e' : '#ef4444';

    const range = highVal - lowVal;
    const scale = range === 0 ? 0 : height / range;

    const openOffset = (highVal - openVal) * scale;
    const closeOffset = (highVal - closeVal) * scale;

    const bodyTop = Math.min(openOffset, closeOffset);
    const bodyHeight = Math.max(1, Math.abs(openOffset - closeOffset));

    const wickX = x + width / 2;

    return (
        <g>
            <line x1={wickX} y1={y} x2={wickX} y2={y + height} stroke={color} strokeWidth={1} />
            <rect
                x={x}
                y={y + bodyTop}
                width={width}
                height={bodyHeight}
                fill={color}
                stroke={color}
            />
        </g>
    );
};

interface MarketBreadthChartProps {
    title: string;
    spxData: any[];
    cdBreadth?: BreadthDataPoint[];
    mcBreadth?: BreadthDataPoint[];
    cdSignalBreadth?: SignalBreadthDataPoint[];
    mcSignalBreadth?: SignalBreadthDataPoint[];
    cdScoreBreadth?: { date: string, score_1h: number, score_2h: number, score_3h: number, score_4h: number, score_1d: number, total_score: number }[];
    mcScoreBreadth?: { date: string, score_1h: number, score_2h: number, score_3h: number, score_4h: number, score_1d: number, total_score: number }[];
    cdBreakthroughScoreBreadth?: { date: string, score_1h: number, score_2h: number, score_3h: number, score_4h: number, score_1d: number, total_score: number }[];
    mcBreakthroughScoreBreadth?: { date: string, score_1h: number, score_2h: number, score_3h: number, score_4h: number, score_1d: number, total_score: number }[];
    intervalWeights?: Record<string, number>;
    minDate?: Date;
    maxDate?: Date;
    signals1234?: { cd_dates: string[], mc_dates: string[] };
    tickers?: string[];
    selectedTicker?: string;
    onTickerChange?: (ticker: string) => void;
    indexTitle?: string;
}

// Colors for each interval in stacked bar charts
const INTERVAL_COLORS: Record<string, string> = {
    '1h': '#60a5fa', // blue-400
    '2h': '#34d399', // emerald-400
    '3h': '#fbbf24', // amber-400
    '4h': '#f87171', // red-400
    '1d': '#a78bfa', // violet-400
};

const INTERVALS = ['1h', '2h', '3h', '4h', '1d'] as const;

// Score weights per interval: super-exponential scaling (backtest-optimized)
const SCORE_WEIGHTS: Record<string, number> = {
    '1h': 1,
    '2h': 2,
    '3h': 4,
    '4h': 8,
    '1d': 32,
};

// Searchable ticker selector dropdown
const TickerSelector = ({ tickers, selectedTicker, onSelect, indexLabel }: {
    tickers: string[],
    selectedTicker: string,
    onSelect: (ticker: string) => void,
    indexLabel: string
}) => {
    const [open, setOpen] = useState(false);
    const [search, setSearch] = useState('');
    const dropdownRef = useRef<HTMLDivElement>(null);
    const inputRef = useRef<HTMLInputElement>(null);

    // Close on click outside
    useEffect(() => {
        const handler = (e: MouseEvent) => {
            if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
                setOpen(false);
                setSearch('');
            }
        };
        document.addEventListener('mousedown', handler);
        return () => document.removeEventListener('mousedown', handler);
    }, []);

    const filtered = useMemo(() => {
        if (!search) return tickers;
        const s = search.toUpperCase();
        return tickers.filter(t => t.toUpperCase().includes(s));
    }, [tickers, search]);

    return (
        <div ref={dropdownRef} className="relative" style={{ zIndex: 9999 }}>
            <button
                onClick={() => { setOpen(!open); setTimeout(() => inputRef.current?.focus(), 50); }}
                className="px-2 py-1 text-xs font-medium rounded-md border border-border text-muted-foreground hover:bg-muted flex items-center gap-1 min-w-[100px]"
            >
                <span className="truncate">{selectedTicker || indexLabel}</span>
                <span className="text-[10px] opacity-60">▼</span>
            </button>
            {open && (
                <div
                    className="absolute right-0 top-full mt-1 border border-border rounded-md shadow-lg w-48 max-h-64 flex flex-col overflow-hidden"
                    style={{ zIndex: 9999, backgroundColor: 'hsl(var(--card))', isolation: 'isolate' }}
                >
                    <div className="p-1.5 border-b border-border/50" style={{ backgroundColor: 'hsl(var(--card))' }}>
                        <input
                            ref={inputRef}
                            type="text"
                            placeholder="Search ticker..."
                            value={search}
                            onChange={(e) => setSearch(e.target.value)}
                            className="w-full px-2 py-1 text-xs rounded border border-input bg-background focus:outline-none focus:ring-1 focus:ring-primary/50"
                            onClick={(e) => e.stopPropagation()}
                        />
                    </div>
                    <div className="overflow-y-auto flex-1" style={{ backgroundColor: 'hsl(var(--card))' }}>
                        {/* Index option */}
                        <button
                            onClick={() => { onSelect(''); setOpen(false); setSearch(''); }}
                            className={`w-full px-3 py-1.5 text-xs text-left hover:bg-muted transition-colors flex items-center gap-1 ${!selectedTicker ? 'bg-primary/10 text-primary font-medium' : ''}`}
                        >
                            📊 {indexLabel} (Index)
                        </button>
                        <div className="border-t border-border/30" />
                        {/* Ticker list */}
                        {filtered.map(t => (
                            <button
                                key={t}
                                onClick={() => { onSelect(t); setOpen(false); setSearch(''); }}
                                className={`w-full px-3 py-1 text-xs text-left hover:bg-muted transition-colors ${selectedTicker === t ? 'bg-primary/10 text-primary font-medium' : ''}`}
                            >
                                {t}
                            </button>
                        ))}
                        {filtered.length === 0 && (
                            <div className="px-3 py-2 text-xs text-muted-foreground text-center">No matches</div>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
};

// --- Per-panel Tooltip Components (matching CandleChart style) ---
const formatVol = (v: number) => v >= 1e9 ? (v / 1e9).toFixed(1) + 'B' : v >= 1e6 ? (v / 1e6).toFixed(1) + 'M' : v >= 1e3 ? (v / 1e3).toFixed(0) + 'K' : String(v);

const PriceTooltip = ({ active, payload }: any) => {
    if (!active || !payload?.length) return null;
    const d = payload[0].payload;
    if (d.close == null) return null;
    const isUp = d.close >= d.open;
    return (
        <div className="bg-background border border-border p-2 rounded shadow text-xs z-50">
            <p className="font-semibold mb-1">{d.date}</p>
            <div className="grid grid-cols-2 gap-x-4">
                <span className="text-muted-foreground">Open:</span> <span className={`text-right ${isUp ? 'text-green-400' : 'text-red-400'}`}>{d.open?.toFixed(2)}</span>
                <span className="text-muted-foreground">High:</span> <span className="text-right text-foreground">{d.high?.toFixed(2)}</span>
                <span className="text-muted-foreground">Low:</span> <span className="text-right text-foreground">{d.low?.toFixed(2)}</span>
                <span className="text-muted-foreground">Close:</span> <span className={`text-right ${isUp ? 'text-green-400' : 'text-red-400'}`}>{d.close?.toFixed(2)}</span>
            </div>
            {(d.ema_20 != null || d.sma_50 != null || d.sma_100 != null || d.sma_200 != null) && (
                <div className="mt-1 pt-1 border-t border-border/50 grid grid-cols-2 gap-x-4">
                    {d.ema_20 != null && <><span className="text-muted-foreground">EMA 20:</span> <span className="text-right" style={{ color: '#3b82f6' }}>{d.ema_20.toFixed(2)}</span></>}
                    {d.sma_50 != null && <><span className="text-muted-foreground">SMA 50:</span> <span className="text-right" style={{ color: '#f59e0b' }}>{d.sma_50.toFixed(2)}</span></>}
                    {d.sma_100 != null && <><span className="text-muted-foreground">SMA 100:</span> <span className="text-right" style={{ color: '#a855f7' }}>{d.sma_100.toFixed(2)}</span></>}
                    {d.sma_200 != null && <><span className="text-muted-foreground">SMA 200:</span> <span className="text-right" style={{ color: '#ef4444' }}>{d.sma_200.toFixed(2)}</span></>}
                </div>
            )}
            {(d.cd_1234_signal || d.mc_1234_signal) && (
                <div className="mt-1 pt-1 border-t border-border/50 flex gap-2">
                    {d.cd_1234_signal && <span className="text-green-500 font-bold">↑ CD 1234</span>}
                    {d.mc_1234_signal && <span className="text-red-500 font-bold">↓ MC 1234</span>}
                </div>
            )}
        </div>
    );
};

const VolumeTooltip = ({ active, payload }: any) => {
    if (!active || !payload?.length) return null;
    const d = payload[0].payload;
    return (
        <div className="bg-background border border-border p-2 rounded shadow text-xs z-50">
            <div className="grid grid-cols-2 gap-x-4">
                <span className="text-muted-foreground">Volume:</span>
                <span className="text-right text-foreground">{d.spxVolume ? formatVol(d.spxVolume) : '-'}</span>
            </div>
        </div>
    );
};

const INTERVAL_KEYS = ['1h', '2h', '3h', '4h', '1d'] as const;

const SignalTooltip = ({ active, payload, signalType }: any) => {
    if (!active || !payload?.length) return null;
    const d = payload[0].payload;
    const prefix = signalType === 'cd' ? 'cd_' : 'mc_';
    const label = signalType === 'cd' ? 'CD' : 'MC';
    const color = signalType === 'cd' ? 'text-green-400' : 'text-red-400';
    const intervals = INTERVAL_KEYS.map(k => ({ key: k, val: d[`${prefix}${k}`] || 0 }));
    const total = intervals.reduce((sum, i) => sum + i.val, 0);
    if (total === 0) return (
        <div className="bg-background border border-border p-2 rounded shadow text-xs z-50">
            <p className="text-muted-foreground mt-1">No {label} signals</p>
        </div>
    );
    return (
        <div className="bg-background border border-border p-2 rounded shadow text-xs z-50">
            <div className="grid grid-cols-2 gap-x-4">
                {intervals.filter(i => i.val > 0).map(i => (
                    <React.Fragment key={i.key}>
                        <span className="text-muted-foreground">{i.key}:</span>
                        <span className={`text-right ${color}`}>{i.val}</span>
                    </React.Fragment>
                ))}
                <span className="text-muted-foreground font-semibold border-t border-border/50 pt-0.5 mt-0.5">Total:</span>
                <span className={`text-right font-semibold border-t border-border/50 pt-0.5 mt-0.5 ${color}`}>{total}</span>
            </div>
        </div>
    );
};

const ScoreTooltip = ({ active, payload, scoreKey, label, color }: any) => {
    if (!active || !payload?.length) return null;
    const d = payload[0].payload;
    const val = d[scoreKey];
    return (
        <div className="bg-background border border-border p-2 rounded shadow text-xs z-50">
            <div className="grid grid-cols-2 gap-x-4">
                <span className="text-muted-foreground">{label}:</span>
                <span className={`text-right ${color}`}>{val != null && val > 0 ? val.toFixed(1) : '0'}</span>
            </div>
        </div>
    );
};

const BreakthroughTooltip = ({ active, payload, signalType }: any) => {
    if (!active || !payload?.length) return null;
    const d = payload[0].payload;
    const prefix = signalType === 'cd' ? 'cd_buy_' : 'mc_sell_';
    const label = signalType === 'cd' ? 'CD BT' : 'MC BT';
    const color = signalType === 'cd' ? 'text-green-400' : 'text-red-400';
    const intervals = INTERVAL_KEYS.map(k => ({ key: k, val: d[`${prefix}${k}`] || 0 }));
    const total = intervals.reduce((sum, i) => sum + i.val, 0);
    if (total === 0) return (
        <div className="bg-background border border-border p-2 rounded shadow text-xs z-50">
            <p className="text-muted-foreground mt-1">No {label} signals</p>
        </div>
    );
    return (
        <div className="bg-background border border-border p-2 rounded shadow text-xs z-50">
            <div className="grid grid-cols-2 gap-x-4">
                {intervals.filter(i => i.val > 0).map(i => (
                    <React.Fragment key={i.key}>
                        <span className="text-muted-foreground">{i.key}:</span>
                        <span className={`text-right ${color}`}>{i.val}</span>
                    </React.Fragment>
                ))}
                <span className="text-muted-foreground font-semibold border-t border-border/50 pt-0.5 mt-0.5">Total:</span>
                <span className={`text-right font-semibold border-t border-border/50 pt-0.5 mt-0.5 ${color}`}>{total}</span>
            </div>
        </div>
    );
};

export const MarketBreadthChart: React.FC<MarketBreadthChartProps> = ({
    title,
    spxData,
    cdBreadth = [],
    mcBreadth = [],
    cdSignalBreadth = [],
    mcSignalBreadth = [],
    cdScoreBreadth = [],
    mcScoreBreadth = [],
    cdBreakthroughScoreBreadth = [],
    mcBreakthroughScoreBreadth = [],
    intervalWeights,
    minDate,
    maxDate,
    signals1234,
    tickers = [],
    selectedTicker = '',
    onTickerChange,
    indexTitle
}) => {
    // Effective interval weights: use prop if provided, else fall back to SCORE_WEIGHTS constant
    const effectiveWeights = intervalWeights || SCORE_WEIGHTS;
    // --- Zoom State & Logic (Adapted from CandleChart) ---
    const [zoomState, setZoomState] = useState<{ start: number, end: number } | null>(null);
    const [selection, setSelection] = useState<{ start: number, end: number } | null>(null);
    const isSelectingRef = useRef(false);


    // We only need one ref to track mouse movement for all synchronized charts
    // But we need to attach listeners to a wrapper
    const wrapperRef = useRef<HTMLDivElement>(null);

    // Merge data by date
    const mergedData = useMemo(() => {
        // Debug: Log signals1234 prop with actual dates
        console.log(`[MarketBreadthChart] ${title} signals1234:`, {
            cd_dates: signals1234?.cd_dates ?? [],
            mc_dates: signals1234?.mc_dates ?? [],
            cd_count: signals1234?.cd_dates?.length ?? 0,
            mc_count: signals1234?.mc_dates?.length ?? 0
        });

        const dataMap = new Map<string, any>();

        // Process SPX Data
        spxData.forEach(p => {
            const dateStr = p.time.split('T')[0]; // Extract YYYY-MM-DD
            if (!dataMap.has(dateStr)) {
                dataMap.set(dateStr, { date: dateStr });
            }
            const d = dataMap.get(dateStr);
            d.open = p.open;
            d.high = p.high;
            d.low = p.low;
            d.close = p.close;
            d.spxVolume = p.volume;

            // Indicators
            d.ema_20 = p.ema_20;
            d.sma_50 = p.sma_50;
            d.sma_100 = p.sma_100;
            d.sma_200 = p.sma_200;
            d.cd_signal = p.cd_signal;
            d.mc_signal = p.mc_signal;

            // Signal Markers (triangles for raw CD/MC from price history)
            d.buySignal = p.cd_signal ? p.low * 0.995 : null;
            d.sellSignal = p.mc_signal ? p.high * 1.005 : null;

            // 1234 markers will be computed below after signal breadth data is merged
        });

        // Process CD Breadth (1234 signals per-interval, same format as signal breadth)
        cdBreadth.forEach(b => {
            const dateStr = b.date;
            if (!dataMap.has(dateStr)) dataMap.set(dateStr, { date: dateStr });
            const d = dataMap.get(dateStr);
            d.cd_buy_1h = b.count_1h || 0;
            d.cd_buy_2h = b.count_2h || 0;
            d.cd_buy_3h = b.count_3h || 0;
            d.cd_buy_4h = b.count_4h || 0;
            d.cd_buy_1d = b.count_1d || 0;
        });

        // Process MC Breadth (1234 signals per-interval)
        mcBreadth.forEach(b => {
            const dateStr = b.date;
            if (!dataMap.has(dateStr)) dataMap.set(dateStr, { date: dateStr });
            const d = dataMap.get(dateStr);
            d.mc_sell_1h = b.count_1h || 0;
            d.mc_sell_2h = b.count_2h || 0;
            d.mc_sell_3h = b.count_3h || 0;
            d.mc_sell_4h = b.count_4h || 0;
            d.mc_sell_1d = b.count_1d || 0;
        });

        // Only normalize by total stock count when viewing index-level (aggregate) data.
        // For individual ticker views, the scores are already for a single stock.
        const divisor = !selectedTicker && tickers && tickers.length > 0 ? tickers.length : 1;

        // Process CD Signal Breadth (per-interval) + compute CD Score
        cdSignalBreadth.forEach(b => {
            const dateStr = b.date;
            if (!dataMap.has(dateStr)) dataMap.set(dateStr, { date: dateStr });
            const d = dataMap.get(dateStr);
            d.cd_1h = b.count_1h || 0;
            d.cd_2h = b.count_2h || 0;
            d.cd_3h = b.count_3h || 0;
            d.cd_4h = b.count_4h || 0;
            d.cd_1d = b.count_1d || 0;
            // CD Score = weighted sum using configurable interval weights
            d.cdScore = (d.cd_1h * effectiveWeights['1h'] + d.cd_2h * effectiveWeights['2h']
                + d.cd_3h * effectiveWeights['3h'] + d.cd_4h * effectiveWeights['4h']
                + d.cd_1d * effectiveWeights['1d']) / divisor;
        });

        // Process MC Signal Breadth (per-interval) + compute MC Score
        mcSignalBreadth.forEach(b => {
            const dateStr = b.date;
            if (!dataMap.has(dateStr)) dataMap.set(dateStr, { date: dateStr });
            const d = dataMap.get(dateStr);
            d.mc_1h = b.count_1h || 0;
            d.mc_2h = b.count_2h || 0;
            d.mc_3h = b.count_3h || 0;
            d.mc_4h = b.count_4h || 0;
            d.mc_1d = b.count_1d || 0;
            // MC Score = weighted sum using configurable interval weights
            d.mcScore = (d.mc_1h * effectiveWeights['1h'] + d.mc_2h * effectiveWeights['2h']
                + d.mc_3h * effectiveWeights['3h'] + d.mc_4h * effectiveWeights['4h']
                + d.mc_1d * effectiveWeights['1d']) / divisor;
        });

        // Process CD Score Breadth (indicator-score weighted) — recompute from per-interval raw sums
        cdScoreBreadth.forEach(b => {
            const dateStr = b.date;
            if (!dataMap.has(dateStr)) dataMap.set(dateStr, { date: dateStr });
            const d = dataMap.get(dateStr);
            d.cdNewScore = ((b.score_1h || 0) * effectiveWeights['1h']
                + (b.score_2h || 0) * effectiveWeights['2h']
                + (b.score_3h || 0) * effectiveWeights['3h']
                + (b.score_4h || 0) * effectiveWeights['4h']
                + (b.score_1d || 0) * effectiveWeights['1d']) / divisor;
        });

        // Process MC Score Breadth (indicator-score weighted) — recompute from per-interval raw sums
        mcScoreBreadth.forEach(b => {
            const dateStr = b.date;
            if (!dataMap.has(dateStr)) dataMap.set(dateStr, { date: dateStr });
            const d = dataMap.get(dateStr);
            d.mcNewScore = ((b.score_1h || 0) * effectiveWeights['1h']
                + (b.score_2h || 0) * effectiveWeights['2h']
                + (b.score_3h || 0) * effectiveWeights['3h']
                + (b.score_4h || 0) * effectiveWeights['4h']
                + (b.score_1d || 0) * effectiveWeights['1d']) / divisor;
        });

        // Process CD HQ Score Breadth (indicator-score weighted, HQ only)
        cdBreakthroughScoreBreadth.forEach(b => {
            const dateStr = b.date;
            if (!dataMap.has(dateStr)) dataMap.set(dateStr, { date: dateStr });
            const d = dataMap.get(dateStr);
            d.cdBtScore = ((b.score_1h || 0) * effectiveWeights['1h']
                + (b.score_2h || 0) * effectiveWeights['2h']
                + (b.score_3h || 0) * effectiveWeights['3h']
                + (b.score_4h || 0) * effectiveWeights['4h']
                + (b.score_1d || 0) * effectiveWeights['1d']) / divisor;
        });

        // Process MC HQ Score Breadth (indicator-score weighted, HQ only)
        mcBreakthroughScoreBreadth.forEach(b => {
            const dateStr = b.date;
            if (!dataMap.has(dateStr)) dataMap.set(dateStr, { date: dateStr });
            const d = dataMap.get(dateStr);
            d.mcBtScore = ((b.score_1h || 0) * effectiveWeights['1h']
                + (b.score_2h || 0) * effectiveWeights['2h']
                + (b.score_3h || 0) * effectiveWeights['3h']
                + (b.score_4h || 0) * effectiveWeights['4h']
                + (b.score_1d || 0) * effectiveWeights['1d']) / divisor;
        });

        // Derive 1234 markers
        // If explicit signals1234 provided (e.g. for Index view), use those dates.
        // Otherwise derive from signal breadth data (e.g. for individual stock view).
        const cdDatesSet = signals1234?.cd_dates ? new Set(signals1234.cd_dates) : null;
        const mcDatesSet = signals1234?.mc_dates ? new Set(signals1234.mc_dates) : null;

        dataMap.forEach((d) => {
            let is1234CD = false;
            let is1234MC = false;

            if (cdDatesSet && mcDatesSet) {
                // Use explicit signals (Index View)
                is1234CD = cdDatesSet.has(d.date);
                is1234MC = mcDatesSet.has(d.date);
            } else {
                // Fallback: derive from breadth counts (Component/Stock View)
                const cdIntervals = [d.cd_1h, d.cd_2h, d.cd_3h, d.cd_4h, d.cd_1d]
                    .filter(v => v && v > 0).length;
                const mcIntervals = [d.mc_1h, d.mc_2h, d.mc_3h, d.mc_4h, d.mc_1d]
                    .filter(v => v && v > 0).length;
                is1234CD = cdIntervals >= 3;
                is1234MC = mcIntervals >= 3;
            }

            d.cd_1234_signal = is1234CD;
            d.mc_1234_signal = is1234MC;
            if (d.low != null) {
                d.buySignal1234 = is1234CD ? d.low * 0.98 : null;
            }
            if (d.high != null) {
                d.sellSignal1234 = is1234MC ? d.high * 1.02 : null;
            }
        });

        // Convert to array and sort
        let result = Array.from(dataMap.values())
            .sort((a, b) => a.date.localeCompare(b.date));

        if (minDate) {
            const minStr = format(minDate, 'yyyy-MM-dd');
            result = result.filter(d => d.date >= minStr);
        }
        if (maxDate) {
            const maxStr = format(maxDate, 'yyyy-MM-dd');
            result = result.filter(d => d.date <= maxStr);
        }

        // Filter to generally available days (mostly SPX days) for cleaner chart
        result = result.filter(d => d.close !== undefined);

        return result;
    }, [spxData, cdBreadth, mcBreadth, cdSignalBreadth, mcSignalBreadth, cdScoreBreadth, mcScoreBreadth, cdBreakthroughScoreBreadth, mcBreakthroughScoreBreadth, effectiveWeights, minDate, maxDate, selectedTicker, tickers]);

    // Visible slice
    const visibleData = useMemo(() => {
        if (mergedData.length === 0) return [];
        if (!zoomState) return mergedData;
        return mergedData.slice(zoomState.start, zoomState.end + 1);
    }, [mergedData, zoomState]);

    // Calculate unified volume scale based on max volume in visible data
    const volumeScale = useMemo(() => {
        const maxVol = Math.max(...visibleData.map(d => d.spxVolume || 0));
        if (maxVol >= 1e9) {
            return { divisor: 1e9, suffix: 'B', maxVol };
        } else if (maxVol >= 1e6) {
            return { divisor: 1e6, suffix: 'M', maxVol };
        } else if (maxVol >= 1e3) {
            return { divisor: 1e3, suffix: 'K', maxVol };
        }
        return { divisor: 1, suffix: '', maxVol };
    }, [visibleData]);

    // Calculate explicit tick values for volume to ensure consistent grid lines
    const volumeTicks = useMemo(() => {
        const max = volumeScale.maxVol || 1;
        return [0, max / 2, max];
    }, [volumeScale.maxVol]);


    // Helpers
    const getChartArea = (container: HTMLElement) => {
        const width = container.clientWidth;
        // Approximation: Recharts uses responsive width.
        // We assume generic margins for calculation: left 0, right 50-ish?
        // Actually we need to be careful. Let's assume standard full width for index calculation.
        const chartWidth = width - 20;
        if (chartWidth <= 0) return null;
        return { width: chartWidth, left: 10 };
    };

    const pixelToIndex = (x: number, chartArea: { width: number, left: number }, currentCount: number) => {
        const relativeX = x - chartArea.left;
        const fraction = relativeX / chartArea.width;
        const index = Math.floor(fraction * currentCount);
        return Math.max(0, Math.min(currentCount - 1, index));
    };

    // Handlers
    const handleMouseDown = (e: React.MouseEvent<HTMLDivElement>) => {
        isSelectingRef.current = true;
        const chartArea = getChartArea(e.currentTarget);
        if (!chartArea) return;
        const count = visibleData.length;
        const clickIndex = pixelToIndex(e.nativeEvent.offsetX, chartArea, count);
        setSelection({ start: clickIndex, end: clickIndex });
    };

    const handleMouseMove = useCallback((e: MouseEvent) => {
        if (!isSelectingRef.current || !wrapperRef.current) return;
        // Use wrapper width estimation or the target element?
        // Ideally we track the element that fired mousedown, but all charts share width.
        // We can just use the wrapper's first child dimensions if uniform.
        // Simply reusing logic on the event target if it's within our wrapper is okay.

        // Simpler: assume the mouse X relative to the wrapper is consistent for all stacked charts.
        const rect = wrapperRef.current.getBoundingClientRect();
        const offsetX = e.clientX - rect.left;
        const width = rect.width;

        // Margins need to match chart margins. Recharts usually has some side padding.
        // Let's assume 10px padding for now.
        const chartWidth = width - 20;
        const left = 10;

        const relativeX = offsetX - left;
        const fraction = relativeX / chartWidth;
        const moveIndex = Math.max(0, Math.min(visibleData.length - 1, Math.floor(fraction * visibleData.length)));

        setSelection(prev => prev ? { ...prev, end: moveIndex } : null);
    }, [visibleData.length]);

    const handleMouseUp = useCallback(() => {
        if (!isSelectingRef.current) return;
        isSelectingRef.current = false;
        setSelection(prev => {
            if (prev && Math.abs(prev.end - prev.start) > 1) {
                const currentStart = zoomState ? zoomState.start : 0;
                const localMin = Math.min(prev.start, prev.end);
                const localMax = Math.max(prev.start, prev.end);
                const newStart = currentStart + localMin;
                const newEnd = currentStart + localMax;
                setZoomState({ start: newStart, end: newEnd });
            }
            return null;
        });
    }, [zoomState]);

    const handleWheel = (e: React.WheelEvent) => {
        if (visibleData.length === 0) return;
        const currentStart = zoomState ? zoomState.start : 0;
        const currentEnd = zoomState ? zoomState.end : mergedData.length - 1;
        const currentLength = currentEnd - currentStart + 1;
        const zoomFactor = 0.1;
        const delta = e.deltaY > 0 ? 1 : -1;
        const change = Math.max(2, Math.floor(currentLength * zoomFactor));

        let newStart = currentStart;
        let newEnd = currentEnd;

        if (delta > 0) { // Zoom Out
            newStart = Math.max(0, currentStart - Math.ceil(change / 2));
            newEnd = Math.min(mergedData.length - 1, currentEnd + Math.ceil(change / 2));
        } else { // Zoom In
            newStart = Math.min(newEnd - 5, currentStart + Math.ceil(change / 2));
            newEnd = Math.max(newStart + 5, currentEnd - Math.ceil(change / 2));
        }
        setZoomState({ start: newStart, end: newEnd });
    };

    // Global listeners
    useEffect(() => {
        if (wrapperRef.current) {
            window.addEventListener('mousemove', handleMouseMove);
            window.addEventListener('mouseup', handleMouseUp);
        }
        return () => {
            window.removeEventListener('mousemove', handleMouseMove);
            window.removeEventListener('mouseup', handleMouseUp);
        };
    }, [handleMouseMove, handleMouseUp]);


    if (mergedData.length === 0) {
        return (
            <div className="h-64 flex items-center justify-center border rounded-lg bg-card/50 text-muted-foreground">
                No data available
            </div>
        );
    }

    const commonXAxis = (hide: boolean = true) => (
        <XAxis
            dataKey="date"
            tickFormatter={(str) => str.substring(5)}
            minTickGap={30}
            axisLine={!hide}
            tickLine={!hide}
            hide={hide}
            fontSize={12}
        />
    );

    // Calculate Y Domains
    const spxMin = Math.min(...visibleData.map(d => d.low - 0.1 || Infinity)); // small buffer if undefined?
    const spxMax = Math.max(...visibleData.map(d => d.high + 0.1 || -Infinity));

    // Safety check
    const validMin = spxMin === Infinity ? 0 : spxMin;
    const validMax = spxMax === -Infinity ? 100 : spxMax;

    const spxPadding = (validMax - validMin) * 0.25; // 50% padding for signals visibility
    const spxDomain = [validMin - spxPadding, validMax + spxPadding];

    const ReferenceBlock = () => (
        selection && visibleData[Math.min(selection.start, selection.end)] && visibleData[Math.max(selection.start, selection.end)] ? (
            <ReferenceArea
                x1={visibleData[Math.min(selection.start, selection.end)].date}
                x2={visibleData[Math.max(selection.start, selection.end)].date}
                strokeOpacity={0}
                fill="hsl(var(--primary))"
                fillOpacity={0.1}
            />
        ) : <></>
    );


    return (
        <div className="flex flex-col h-[828px] border rounded-lg bg-card p-4">
            <div className="flex justify-between items-center mb-2 gap-2">
                <h3 className="text-lg font-semibold text-foreground shrink-0">
                    {selectedTicker ? `${selectedTicker} (${indexTitle || title})` : title}
                </h3>
                <div className="flex items-center gap-2">
                    {tickers.length > 0 && (
                        <TickerSelector
                            tickers={tickers}
                            selectedTicker={selectedTicker}
                            onSelect={(t) => onTickerChange?.(t)}
                            indexLabel={indexTitle || title}
                        />
                    )}
                    <button
                        onClick={() => setZoomState(null)}
                        className="px-2 py-1 text-xs font-medium rounded-md border border-border text-muted-foreground hover:bg-muted shrink-0"
                    >
                        Reset Zoom
                    </button>
                </div>
            </div>

            <div
                ref={wrapperRef}
                className="flex-1 flex flex-col min-h-0 select-none pb-2"
                onWheel={handleWheel}
                onMouseDown={handleMouseDown}
            >
                {/* 1. Price History (Candle) */}
                <div className="flex-[2] min-h-0 border-b border-border/0 relative" style={{ zIndex: 100 }}>
                    <span className="absolute top-5 left-2 text-[10px] font-medium text-[#8884d8] z-10">Price</span>
                    <ResponsiveContainer width="100%" height="100%">
                        <ComposedChart data={visibleData} syncId="breadthSync" margin={{ left: 5, right: 5, top: 5, bottom: 5 }}>
                            <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={1} />
                            {commonXAxis(true)}
                            <YAxis
                                orientation="left"
                                mirror={true}
                                domain={spxDomain}
                                tickFormatter={(val) => val.toFixed(0)}
                                width={38}
                                tick={{ fontSize: 10 }}
                            />
                            <Tooltip content={<PriceTooltip />} cursor={{ stroke: 'rgba(150,150,150,0.5)', strokeDasharray: '3 3' }} wrapperStyle={{ zIndex: 100 }} />
                            <Bar
                                dataKey={d => [d.low, d.high]}
                                shape={<CandleShape />}
                                isAnimationActive={false}
                                name="Price"
                            />

                            {/* Moving Averages */}
                            <Line type="monotone" dataKey="ema_20" stroke="#3b82f6" strokeWidth={1} dot={false} name="EMA 20" isAnimationActive={false} />
                            <Line type="monotone" dataKey="sma_50" stroke="#f59e0b" strokeWidth={1} dot={false} name="SMA 50" isAnimationActive={false} />
                            <Line type="monotone" dataKey="sma_100" stroke="#a855f7" strokeWidth={1} dot={false} name="SMA 100" isAnimationActive={false} />
                            <Line type="monotone" dataKey="sma_200" stroke="#ef4444" strokeWidth={1} dot={false} name="SMA 200" isAnimationActive={false} />

                            {/* Buy Signals (CD) */}
                            <Scatter
                                name="CD Buy Signal"
                                dataKey="buySignal"
                                shape={(props: any) => {
                                    const { cx, cy } = props;
                                    if (!cx || !cy) return <g />;
                                    return (
                                        <path
                                            d={`M${cx},${cy} l-5,8 l10,0 z`}
                                            fill="none"
                                            stroke="#22c55e"
                                            strokeWidth={2}
                                            transform={`translate(0, 8)`}
                                        />
                                    );
                                }}
                                isAnimationActive={false}
                                fill="#22c55e"
                            />

                            {/* Buy Signals 1234 (Diamond) */}
                            <Scatter
                                name="CD 1234 Buy Signal"
                                dataKey="buySignal1234"
                                shape={(props: any) => {
                                    const { cx, cy } = props;
                                    if (!cx || !cy) return <g />;
                                    return (
                                        <path
                                            d={`M${cx},${cy} l5,5 l-5,5 l-5,-5 z`}
                                            fill="none"
                                            stroke="#15803d"
                                            strokeWidth={2}
                                            transform={`translate(0, 22)`}
                                        />
                                    );
                                }}
                                isAnimationActive={false}
                                fill="#15803d"
                            />

                            {/* Sell Signals (MC) */}
                            <Scatter
                                name="MC Sell Signal"
                                dataKey="sellSignal"
                                shape={(props: any) => {
                                    const { cx, cy } = props;
                                    if (!cx || !cy) return <g />;
                                    return (
                                        <path
                                            d={`M${cx},${cy} l-5,-8 l10,0 z`}
                                            fill="none"
                                            stroke="#ef4444"
                                            strokeWidth={2}
                                            transform={`translate(0, -8)`}
                                        />
                                    );
                                }}
                                isAnimationActive={false}
                                fill="#ef4444"
                            />

                            {/* Sell Signals 1234 (Diamond) */}
                            <Scatter
                                name="MC 1234 Sell Signal"
                                dataKey="sellSignal1234"
                                shape={(props: any) => {
                                    const { cx, cy } = props;
                                    if (!cx || !cy) return <g />;
                                    return (
                                        <path
                                            d={`M${cx},${cy} l5,5 l-5,5 l-5,-5 z`}
                                            fill="none"
                                            stroke="#b91c1c"
                                            strokeWidth={2}
                                            transform={`translate(0, -22)`}
                                        />
                                    );
                                }}
                                isAnimationActive={false}
                                fill="#b91c1c"
                            />
                            <ReferenceBlock />
                        </ComposedChart>
                    </ResponsiveContainer>
                </div>

                {/* 2. SPX Volume */}
                <div className="flex-[0.4] min-h-0 border-b border-border/50 relative" style={{ zIndex: 90 }}>
                    <span className="absolute top-3 left-2 text-[10px] font-medium text-[#00A5E3] z-10">Vol</span>
                    <span className="absolute bottom-1 left-2 text-[10px] text-muted-foreground z-10">{volumeScale.suffix}</span>
                    <ResponsiveContainer width="100%" height="100%">
                        <ComposedChart data={visibleData} syncId="breadthSync" margin={{ left: 5, right: 5, top: 5, bottom: 5 }}>
                            <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={1} />
                            {commonXAxis(true)}
                            <YAxis
                                orientation="left"
                                mirror={true}
                                domain={[0, volumeScale.maxVol]}
                                ticks={volumeTicks}
                                tickFormatter={(val) => val === 0 ? '' : (val / volumeScale.divisor).toFixed(1)}
                                width={38}
                                tick={{ fontSize: 10 }}
                                tickCount={3}
                            />
                            <Tooltip content={<VolumeTooltip />} cursor={{ stroke: 'rgba(150,150,150,0.5)', strokeDasharray: '3 3' }} wrapperStyle={{ zIndex: 100 }} />
                            <Bar dataKey="spxVolume" opacity={0.6} name="Volume">
                                {visibleData.map((entry, index) => (
                                    <Cell
                                        key={`vol-${index}`}
                                        fill={entry.close >= entry.open ? '#22c55e' : '#ef4444'}
                                    />
                                ))}
                            </Bar>
                            <ReferenceBlock />
                        </ComposedChart>
                    </ResponsiveContainer>
                </div>

                {/* 3. CD Signals by Interval (stacked bar) */}
                <div className="flex-[0.4] min-h-0 border-b border-border/50 relative" style={{ zIndex: 80 }}>
                    <span className="absolute top-3 left-2 text-[10px] font-medium text-[#22c55e] z-10">CD</span>
                    <div className="absolute top-3 right-2 flex gap-1 z-10">
                        {INTERVALS.map(intv => (
                            <span key={intv} className="text-[8px] font-medium" style={{ color: INTERVAL_COLORS[intv] }}>{intv}</span>
                        ))}
                    </div>
                    <ResponsiveContainer width="100%" height="100%">
                        <ComposedChart data={visibleData} syncId="breadthSync" margin={{ left: 5, right: 5, top: 5, bottom: 5 }}>
                            <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={1} />
                            {commonXAxis(true)}
                            <YAxis
                                orientation="left"
                                mirror={true}
                                domain={[0, 'auto']}
                                tickFormatter={(val) => val === 0 ? '' : val}
                                width={38}
                                tick={{ fontSize: 10 }}
                                tickCount={3}
                            />
                            <Tooltip content={<SignalTooltip signalType="cd" />} cursor={{ stroke: 'rgba(150,150,150,0.5)', strokeDasharray: '3 3' }} wrapperStyle={{ zIndex: 100 }} />
                            {INTERVALS.map(intv => (
                                <Bar
                                    key={`cd_${intv}`}
                                    dataKey={`cd_${intv}`}
                                    stackId="cd_stack"
                                    fill={INTERVAL_COLORS[intv]}
                                    name={`CD ${intv}`}
                                    isAnimationActive={false}
                                />
                            ))}
                            <ReferenceBlock />
                        </ComposedChart>
                    </ResponsiveContainer>
                </div>

                {/* 4. MC Signals by Interval (stacked bar) */}
                <div className="flex-[0.4] min-h-0 border-b border-border/50 relative" style={{ zIndex: 70 }}>
                    <span className="absolute top-3 left-2 text-[10px] font-medium text-[#f87171] z-10">MC</span>
                    <div className="absolute top-3 right-2 flex gap-1 z-10">
                        {INTERVALS.map(intv => (
                            <span key={intv} className="text-[8px] font-medium" style={{ color: INTERVAL_COLORS[intv] }}>{intv}</span>
                        ))}
                    </div>
                    <ResponsiveContainer width="100%" height="100%">
                        <ComposedChart data={visibleData} syncId="breadthSync" margin={{ left: 5, right: 5, top: 5, bottom: 5 }}>
                            <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={1} />
                            {commonXAxis(true)}
                            <YAxis
                                orientation="left"
                                mirror={true}
                                domain={[0, 'auto']}
                                tickFormatter={(val) => val === 0 ? '' : val}
                                width={38}
                                tick={{ fontSize: 10 }}
                                tickCount={3}
                            />
                            <Tooltip content={<SignalTooltip signalType="mc" />} cursor={{ stroke: 'rgba(150,150,150,0.5)', strokeDasharray: '3 3' }} wrapperStyle={{ zIndex: 100 }} />
                            {INTERVALS.map(intv => (
                                <Bar
                                    key={`mc_${intv}`}
                                    dataKey={`mc_${intv}`}
                                    stackId="mc_stack"
                                    fill={INTERVAL_COLORS[intv]}
                                    name={`MC ${intv}`}
                                    isAnimationActive={false}
                                />
                            ))}
                            <ReferenceBlock />
                        </ComposedChart>
                    </ResponsiveContainer>
                </div>

                {/* 7. CD Score (indicator-weighted) */}
                <div className="flex-[0.4] min-h-0 border-b border-border/50 relative" style={{ zIndex: 60 }}>
                    <span className="absolute top-3 left-2 text-[10px] font-medium text-[#22c55e] z-10">CD Score</span>
                    <ResponsiveContainer width="100%" height="100%">
                        <ComposedChart data={visibleData} syncId="breadthSync" margin={{ left: 5, right: 5, top: 5, bottom: 5 }}>
                            <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={1} />
                            {commonXAxis(true)}
                            <YAxis
                                orientation="left"
                                mirror={true}
                                domain={[0, 'auto']}
                                tickFormatter={(val) => val === 0 ? '' : Number.isInteger(val) ? val : val.toFixed(2)}
                                width={38}
                                tick={{ fontSize: 10 }}
                                tickCount={3}
                            />
                            <Tooltip content={<ScoreTooltip scoreKey="cdNewScore" label="CD Score" color="text-green-400" />} cursor={{ stroke: 'rgba(150,150,150,0.5)', strokeDasharray: '3 3' }} wrapperStyle={{ zIndex: 100 }} />
                            <Bar
                                dataKey="cdNewScore"
                                fill="#22c55e"
                                name="CD Score"
                                isAnimationActive={false}
                            />
                            <ReferenceBlock />
                        </ComposedChart>
                    </ResponsiveContainer>
                </div>

                {/* 8. MC Score (indicator-weighted) */}
                <div className="flex-[0.4] min-h-0 border-b border-border/50 relative" style={{ zIndex: 50 }}>
                    <span className="absolute top-3 left-2 text-[10px] font-medium text-[#ef4444] z-10">MC Score</span>
                    <ResponsiveContainer width="100%" height="100%">
                        <ComposedChart data={visibleData} syncId="breadthSync" margin={{ left: 5, right: 5, top: 5, bottom: 5 }}>
                            <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={1} />
                            {commonXAxis(true)}
                            <YAxis
                                orientation="left"
                                mirror={true}
                                domain={[0, 'auto']}
                                tickFormatter={(val) => val === 0 ? '' : Number.isInteger(val) ? val : val.toFixed(2)}
                                width={38}
                                tick={{ fontSize: 10 }}
                                tickCount={3}
                            />
                            <Tooltip content={<ScoreTooltip scoreKey="mcNewScore" label="MC Score" color="text-red-400" />} cursor={{ stroke: 'rgba(150,150,150,0.5)', strokeDasharray: '3 3' }} wrapperStyle={{ zIndex: 100 }} />
                            <Bar
                                dataKey="mcNewScore"
                                fill="#ef4444"
                                name="MC Score"
                                isAnimationActive={false}
                            />
                            <ReferenceBlock />
                        </ComposedChart>
                    </ResponsiveContainer>
                </div>

                {/* 9. CD HQ Counts (Buy) — stacked by interval */}
                <div className="flex-[0.4] min-h-0 border-b border-border/50 relative" style={{ zIndex: 40 }}>
                    <span className="absolute top-3 left-2 text-[10px] font-medium text-[#22c55e] z-10">CD HQ</span>
                    <div className="absolute top-3 right-2 flex gap-1 z-10">
                        {INTERVALS.map(intv => (
                            <span key={intv} className="text-[8px] font-medium" style={{ color: INTERVAL_COLORS[intv] }}>{intv}</span>
                        ))}
                    </div>
                    <ResponsiveContainer width="100%" height="100%">
                        <ComposedChart data={visibleData} syncId="breadthSync" margin={{ left: 5, right: 5, top: 5, bottom: 5 }}>
                            <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={1} />
                            {commonXAxis(true)}
                            <YAxis
                                orientation="left"
                                mirror={true}
                                domain={[0, 'auto']}
                                tickFormatter={(val) => val === 0 ? '' : Number.isInteger(val) ? val : val.toFixed(2)}
                                width={38}
                                tick={{ fontSize: 10 }}
                                tickCount={3}
                            />
                            <Tooltip content={<BreakthroughTooltip signalType="cd" />} cursor={{ stroke: 'rgba(150,150,150,0.5)', strokeDasharray: '3 3' }} wrapperStyle={{ zIndex: 100 }} />
                            {INTERVALS.map(intv => (
                                <Bar
                                    key={`cd_buy_${intv}`}
                                    dataKey={`cd_buy_${intv}`}
                                    stackId="cd_buy_stack"
                                    fill={INTERVAL_COLORS[intv]}
                                    name={`CD HQ ${intv}`}
                                    isAnimationActive={false}
                                />
                            ))}
                            <ReferenceBlock />
                        </ComposedChart>
                    </ResponsiveContainer>
                </div>

                {/* 10. MC HQ Counts (Sell) — stacked by interval */}
                <div className="flex-[0.4] min-h-0 border-b border-border/50 relative" style={{ zIndex: 30 }}>
                    <span className="absolute top-3 left-2 text-[10px] font-medium text-[#ef4444] z-10">MC HQ</span>
                    <div className="absolute top-3 right-2 flex gap-1 z-10">
                        {INTERVALS.map(intv => (
                            <span key={intv} className="text-[8px] font-medium" style={{ color: INTERVAL_COLORS[intv] }}>{intv}</span>
                        ))}
                    </div>
                    <ResponsiveContainer width="100%" height="100%">
                        <ComposedChart data={visibleData} syncId="breadthSync" margin={{ left: 5, right: 5, top: 5, bottom: 5 }}>
                            <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={1} />
                            {commonXAxis(true)}
                            <YAxis
                                orientation="left"
                                mirror={true}
                                domain={[0, 'auto']}
                                tickFormatter={(val) => val === 0 ? '' : Number.isInteger(val) ? val : val.toFixed(2)}
                                width={38}
                                tick={{ fontSize: 10 }}
                                tickCount={3}
                            />
                            <Tooltip content={<BreakthroughTooltip signalType="mc" />} cursor={{ stroke: 'rgba(150,150,150,0.5)', strokeDasharray: '3 3' }} wrapperStyle={{ zIndex: 100 }} />
                            {INTERVALS.map(intv => (
                                <Bar
                                    key={`mc_sell_${intv}`}
                                    dataKey={`mc_sell_${intv}`}
                                    stackId="mc_sell_stack"
                                    fill={INTERVAL_COLORS[intv]}
                                    name={`MC HQ ${intv}`}
                                    isAnimationActive={false}
                                />
                            ))}
                            <ReferenceBlock />
                        </ComposedChart>
                    </ResponsiveContainer>
                </div>

                {/* 11. CD HQ Score (indicator-weighted, HQ only) */}
                <div className="flex-[0.4] min-h-0 border-b border-border/50 relative" style={{ zIndex: 20 }}>
                    <span className="absolute top-3 left-2 text-[10px] font-medium text-[#22c55e] z-10">CD HQ Score</span>
                    <ResponsiveContainer width="100%" height="100%">
                        <ComposedChart data={visibleData} syncId="breadthSync" margin={{ left: 5, right: 5, top: 5, bottom: 5 }}>
                            <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={1} />
                            {commonXAxis(true)}
                            <YAxis
                                orientation="left"
                                mirror={true}
                                domain={[0, 'auto']}
                                tickFormatter={(val) => val === 0 ? '' : Number.isInteger(val) ? val : val.toFixed(2)}
                                width={38}
                                tick={{ fontSize: 10 }}
                                tickCount={3}
                            />
                            <Tooltip content={<ScoreTooltip scoreKey="cdBtScore" label="CD HQ Score" color="text-[#22c55e]" />} cursor={{ stroke: 'rgba(150,150,150,0.5)', strokeDasharray: '3 3' }} wrapperStyle={{ zIndex: 100 }} />
                            <Bar
                                dataKey="cdBtScore"
                                fill="#22c55e"
                                name="CD HQ Score"
                                isAnimationActive={false}
                            />
                            <ReferenceBlock />
                        </ComposedChart>
                    </ResponsiveContainer>
                </div>

                {/* 12. MC HQ Score (indicator-weighted, HQ only) */}
                <div className="flex-[0.6] min-h-0 border-b border-border/50 relative" style={{ zIndex: 10 }}>
                    <span className="absolute top-3 left-2 text-[10px] font-medium text-[#ef4444] z-10">MC HQ Score</span>
                    <ResponsiveContainer width="100%" height="100%">
                        <ComposedChart data={visibleData} syncId="breadthSync" margin={{ left: 5, right: 5, top: 5, bottom: 5 }}>
                            <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={1} />
                            {commonXAxis(false)}
                            <YAxis
                                orientation="left"
                                mirror={true}
                                domain={[0, 'auto']}
                                tickFormatter={(val) => val === 0 ? '' : Number.isInteger(val) ? val : val.toFixed(2)}
                                width={38}
                                tick={{ fontSize: 10 }}
                                tickCount={3}
                            />
                            <Tooltip content={<ScoreTooltip scoreKey="mcBtScore" label="MC HQ Score" color="text-[#ef4444]" />} cursor={{ stroke: 'rgba(150,150,150,0.5)', strokeDasharray: '3 3' }} wrapperStyle={{ zIndex: 100 }} />
                            <Bar
                                dataKey="mcBtScore"
                                fill="#ef4444"
                                name="MC HQ Score"
                                isAnimationActive={false}
                            />
                            <ReferenceBlock />
                        </ComposedChart>
                    </ResponsiveContainer>
                </div>
            </div>
        </div>
    );
};
