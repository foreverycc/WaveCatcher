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
    ReferenceLine,
    ResponsiveContainer,
    ReferenceArea,
    Area
} from 'recharts';
import { format } from 'date-fns';
import { useQuery } from '@tanstack/react-query';
import { analysisApi, type QuarterlyFundamentals } from '../services/api';
import { capWeightedScore, denomAt, listedCount, type CompanyBreadthPoint, type CapHistory, type Denom, type DmaBreadthPoint, type FirstDates } from '../utils/marketBreadth';

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
    fundamentals?: QuarterlyFundamentals[];
    cdCompanyBreadth?: CompanyBreadthPoint[];
    mcCompanyBreadth?: CompanyBreadthPoint[];
    tickerWeights?: Record<string, number>;
    /** first trading day of recently listed stocks: they only count from then on */
    firstDates?: FirstDates;
    /** price history for weights at each day's market cap */
    capHistory?: CapHistory;
    /** % of stocks above their 20 / 50 / 200-day moving average */
    dmaBreadth?: DmaBreadthPoint[];
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

const HiddenTooltip = () => null;

// With tooltips off, the price lane still shows the hovered date (synced across lanes)
const DateOnlyTooltip = ({ active, payload }: any) => {
    if (!active || !payload?.length) return null;
    const d = payload[0].payload;
    if (!d?.date) return null;
    return <div className="bg-background/90 border border-border px-1.5 py-0.5 rounded shadow text-[11px] font-medium">{d.date}</div>;
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

const formatMoney = (v: number | null | undefined) => {
    if (v == null) return '-';
    const a = Math.abs(v);
    const sign = v < 0 ? '-' : '';
    return a >= 1e12 ? `${sign}$${(a / 1e12).toFixed(2)}T` : a >= 1e9 ? `${sign}$${(a / 1e9).toFixed(2)}B`
        : a >= 1e6 ? `${sign}$${(a / 1e6).toFixed(1)}M` : `${sign}$${a.toFixed(0)}`;
};

/** Quarterly fundamentals tooltip; each lane shows only its own figures (the lanes' tooltips appear together) */
const FundamentalsTooltip = ({ active, payload, part }: any) => {
    if (!active || !payload?.length) return null;
    const d = payload[0].payload;
    if (!d.fin_period) return null;
    const row = (label: string, value: string, color: string) => (
        <><span className="text-muted-foreground">{label}:</span><span className={`text-right ${color}`}>{value}</span></>
    );
    return (
        <div className="bg-background border border-border p-2 rounded shadow text-xs z-50">
            {part === 'income' && <p className="font-semibold mb-1">Quarter ending {d.fin_period}{d.fin_companies ? ` (${d.fin_companies} companies)` : ''}</p>}
            <div className="grid grid-cols-2 gap-x-4">
                {part === 'income' && <>
                    {row('Revenue', formatMoney(d.fin_revenue), 'text-[#60a5fa]')}
                    {row('Gross Margin', d.fin_gross_margin != null ? `${d.fin_gross_margin.toFixed(1)}%` : '-', 'text-[#fbbf24]')}
                    {row('Net Income', formatMoney(d.fin_net), 'text-[#34d399]')}
                </>}
                {part === 'cash' && <>
                    {d.fin_ocf != null && row('Operating Cash Flow', formatMoney(d.fin_ocf), 'text-[#22d3ee]')}
                    {d.fin_capex != null && row('Capex', formatMoney(d.fin_capex), 'text-[#fb923c]')}
                    {row('Free Cash Flow', formatMoney(d.fin_fcf), 'text-[#f472b6]')}
                    {d.fin_fcf_conv != null && row('FCF Conversion', `${d.fin_fcf_conv.toFixed(0)}%`, 'text-foreground')}
                </>}
                {part === 'eps' && <>
                    {d.fin_eps != null && row('EPS', d.fin_eps.toFixed(2), 'text-[#a78bfa]')}
                    {d.fin_eps_up != null && row('EPS up vs prev Q', `${d.fin_eps_up.toFixed(0)}%`, 'text-[#a78bfa]')}
                    {d.fin_fcf_pos != null && row('FCF positive', `${d.fin_fcf_pos.toFixed(0)}%`, 'text-[#f472b6]')}
                </>}
            </div>
        </div>
    );
};

const CombinedSignalTooltip = ({ active, payload }: any) => {
    if (!active || !payload?.length) return null;
    const d = payload[0].payload;
    const rows = INTERVAL_KEYS.map(k => ({ key: k, cd: d[`cd_${k}`] || 0, mc: d[`mc_${k}`] || 0 }));
    const cdTotal = rows.reduce((s, r) => s + r.cd, 0);
    const mcTotal = rows.reduce((s, r) => s + r.mc, 0);
    if (cdTotal === 0 && mcTotal === 0) return (
        <div className="bg-background border border-border p-2 rounded shadow text-xs z-50">
            <p className="text-muted-foreground mt-1">No CD / MC signals</p>
        </div>
    );
    return (
        <div className="bg-background border border-border p-2 rounded shadow text-xs z-50">
            <div className="grid grid-cols-3 gap-x-4">
                <span></span><span className="text-right text-green-400">CD</span><span className="text-right text-red-400">MC</span>
                {rows.filter(r => r.cd > 0 || r.mc > 0).map(r => (
                    <React.Fragment key={r.key}>
                        <span className="text-muted-foreground">{r.key}:</span>
                        <span className="text-right text-green-400">{r.cd}</span>
                        <span className="text-right text-red-400">{r.mc}</span>
                    </React.Fragment>
                ))}
                <span className="text-muted-foreground font-semibold border-t border-border/50 pt-0.5 mt-0.5">Total:</span>
                <span className="text-right font-semibold border-t border-border/50 pt-0.5 mt-0.5 text-green-400">{cdTotal}</span>
                <span className="text-right font-semibold border-t border-border/50 pt-0.5 mt-0.5 text-red-400">{mcTotal}</span>
            </div>
        </div>
    );
};

const CombinedScoreTooltip = ({ active, payload }: any) => {
    if (!active || !payload?.length) return null;
    const d = payload[0].payload;
    return (
        <div className="bg-background border border-border p-2 rounded shadow text-xs z-50">
            <div className="grid grid-cols-2 gap-x-4">
                <span className="text-muted-foreground">CD Score:</span><span className="text-right text-green-400">{(d.cdNewScore || 0).toFixed(1)}</span>
                <span className="text-muted-foreground">MC Score:</span><span className="text-right text-red-400">{(d.mcNewScore || 0).toFixed(1)}</span>
            </div>
        </div>
    );
};

const DmaTooltip = ({ active, payload }: any) => {
    if (!active || !payload?.length) return null;
    const d = payload[0].payload;
    const fmt = (v: number | null | undefined) => v == null ? '–' : `${v.toFixed(1)}%`;
    return (
        <div className="bg-background border border-border p-2 rounded shadow text-xs z-50">
            <div className="grid grid-cols-2 gap-x-4">
                <span className="text-muted-foreground">Above 20DMA:</span><span className="text-right text-[#38bdf8]">{fmt(d.dma20)}</span>
                <span className="text-muted-foreground">Above 50DMA:</span><span className="text-right text-[#f59e0b]">{fmt(d.dma50)}</span>
                <span className="text-muted-foreground">Above 200DMA:</span><span className="text-right text-[#a78bfa]">{fmt(d.dma200)}</span>
            </div>
        </div>
    );
};

const BondYieldTooltip = ({ active, payload }: any) => {
    if (!active || !payload?.length) return null;
    const d = payload[0].payload;
    const fmt = (v: number | null | undefined) => v == null ? '–' : `${v.toFixed(2)}%`;
    const spread = d.yieldSpread == null ? '–' : `${d.yieldSpread >= 0 ? '+' : ''}${d.yieldSpread.toFixed(2)}%`;
    return (
        <div className="bg-background border border-border p-2 rounded shadow text-xs z-50">
            <div className="grid grid-cols-2 gap-x-4">
                <span className="text-muted-foreground">10-year:</span><span className="text-right text-[#f87171]">{fmt(d.y10y)}</span>
                <span className="text-muted-foreground">2-year:</span><span className="text-right text-[#fbbf24]">{fmt(d.y2y)}</span>
                <span className="text-muted-foreground">3-month:</span><span className="text-right text-[#60a5fa]">{fmt(d.y3m)}</span>
                <span className="text-muted-foreground">10y − 2y:</span><span className={`text-right ${d.yieldSpread != null && d.yieldSpread < 0 ? 'text-red-400' : 'text-green-400'}`}>{spread}</span>
            </div>
        </div>
    );
};

const MarketBreadthTooltip = ({ active, payload, kind }: any) => {
    if (!active || !payload?.length) return null;
    const d = payload[0].payload;
    const pct = (v: number | undefined) => v != null ? ` (${(v * 100).toFixed(1)}%)` : '';
    return (
        <div className="bg-background border border-border p-2 rounded shadow text-xs z-50">
            <div className="grid grid-cols-2 gap-x-4">
                {kind === 'weighted' ? <>
                    <span className="text-muted-foreground">CD:</span><span className="text-right text-green-400">{(d.cdWBreadthScore || 0).toFixed(2)}</span>
                    <span className="text-muted-foreground">MC:</span><span className="text-right text-red-400">{(d.mcWBreadthScore || 0).toFixed(2)}</span>
                </> : kind === 'count' ? <>
                    <span className="text-muted-foreground">CD companies:</span><span className="text-right text-green-400">{d.cdCompanies || 0}{pct(d.cdShare)}</span>
                    <span className="text-muted-foreground">MC companies:</span><span className="text-right text-red-400">{d.mcCompanies || 0}{pct(d.mcShare)}</span>
                </> : <>
                    <span className="text-muted-foreground">CD:</span><span className="text-right text-green-400">{(d.cdBreadthScore || 0).toFixed(2)}</span>
                    <span className="text-muted-foreground">MC:</span><span className="text-right text-red-400">{(d.mcBreadthScore || 0).toFixed(2)}</span>
                    <span className="text-muted-foreground font-semibold border-t border-border/50 pt-0.5 mt-0.5">Net:</span>
                    <span className={`text-right font-semibold border-t border-border/50 pt-0.5 mt-0.5 ${(d.netBreadthScore || 0) >= 0 ? 'text-green-400' : 'text-red-400'}`}>{(d.netBreadthScore || 0).toFixed(2)}</span>
                </>}
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
    indexTitle,
    fundamentals = [],
    cdCompanyBreadth = [],
    mcCompanyBreadth = [],
    tickerWeights,
    firstDates,
    capHistory,
    dmaBreadth = []
}) => {
    // Effective interval weights: use prop if provided, else fall back to SCORE_WEIGHTS constant
    const effectiveWeights = intervalWeights || SCORE_WEIGHTS;
    // US Treasury yields, shared by every chart (FRED daily data)
    const { data: bondYields = [] } = useQuery({
        queryKey: ['bondYields'],
        queryFn: analysisApi.getBondYields,
        staleTime: 1000 * 60 * 60,
    });
    // --- Zoom State & Logic (Adapted from CandleChart) ---
    const [zoomState, setZoomState] = useState<{ start: number, end: number } | null>(null);
    // Hover info boxes are off by default (they get crowded): only the date shows; the toggle turns them on
    const [showTooltips, setShowTooltips] = useState(false);
    const toggleTooltips = () => setShowTooltips(v => !v);
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
        // Stocks already trading that day: a recent listing does not dilute the days before it
        const divisorN: Denom = !selectedTicker && tickers && tickers.length > 0 ? listedCount(tickers, firstDates) : 1;
        const div = (date: string) => denomAt(divisorN, date);

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
                + d.cd_1d * effectiveWeights['1d']) / div(dateStr);
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
                + d.mc_1d * effectiveWeights['1d']) / div(dateStr);
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
                + (b.score_1d || 0) * effectiveWeights['1d']) / div(dateStr);
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
                + (b.score_1d || 0) * effectiveWeights['1d']) / div(dateStr);
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
                + (b.score_1d || 0) * effectiveWeights['1d']) / div(dateStr);
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
                + (b.score_1d || 0) * effectiveWeights['1d']) / div(dateStr);
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

        // Quarterly fundamentals: each day shows the latest quarter that had ended by then
        const quarters = [...(fundamentals || [])].sort((a, b) => a.period_end.localeCompare(b.period_end));
        let qi = -1;
        result.forEach(d => {
            while (qi + 1 < quarters.length && quarters[qi + 1].period_end <= d.date) qi++;
            if (qi < 0) return;
            const q = quarters[qi];
            d.fin_period = q.period_end;
            d.fin_companies = q.companies;
            d.fin_revenue = q.revenue;
            d.fin_gross_margin = q.gross_profit != null && q.revenue ? (q.gross_profit / q.revenue) * 100 : null;
            d.fin_net = q.net_income;
            d.fin_eps = q.eps ?? null;
            d.fin_eps_up = q.eps_up_pct ?? null;
            d.fin_ocf = q.operating_cash_flow ?? null;
            d.fin_fcf = q.free_cash_flow ?? null;
            d.fin_fcf_pos = q.fcf_positive_pct ?? null;
            d.fin_capex = q.capital_expenditure ?? null;
            // FCF conversion = free cash flow / net income, only meaningful while net income is positive
            d.fin_fcf_conv = q.fcf_conversion ?? (q.free_cash_flow != null && q.net_income != null && q.net_income > 0
                ? (q.free_cash_flow / q.net_income) * 100 : null);
        });

        // Filter to generally available days (mostly SPX days) for cleaner chart
        result = result.filter(d => d.close !== undefined);

        // Market breadth: companies with a CD / MC signal that day; breadth score = Score x share
        // of companies with a signal, CD positive and MC negative
        const useWeights = !selectedTicker && !!tickerWeights && Object.keys(tickerWeights).length > 0;
        const listTickers = tickers || [];
        // Weighted Breadth Score: weight each ticker's score by its market-cap share before summing
        const capW = useWeights ? tickerWeights : undefined;
        const cdCapScore = capWeightedScore(cdCompanyBreadth, capW, listTickers, effectiveWeights, firstDates, capHistory);
        const mcCapScore = capWeightedScore(mcCompanyBreadth, capW, listTickers, effectiveWeights, firstDates, capHistory);
        const dma = new Map(dmaBreadth.map(r => [r.date, r]));
        // Yields: carry the last published value over days FRED has no row for (holidays, latest day)
        const yields = [...bondYields].sort((a, b) => a.date.localeCompare(b.date));
        let yi = -1;
        const cdCompanies = new Map(cdCompanyBreadth.map(c => [c.date, c.count]));
        const mcCompanies = new Map(mcCompanyBreadth.map(c => [c.date, c.count]));
        result.forEach(d => {
            d.cdCompanies = cdCompanies.get(d.date) || 0;
            d.mcCompanies = mcCompanies.get(d.date) || 0;
            d.mcCompaniesNeg = -d.mcCompanies;
            d.cdShare = d.cdCompanies / div(d.date);
            d.mcShare = d.mcCompanies / div(d.date);
            const m = dma.get(d.date);
            d.dma20 = m?.above20 ?? null; d.dma50 = m?.above50 ?? null; d.dma200 = m?.above200 ?? null;
            while (yi + 1 < yields.length && yields[yi + 1].date <= d.date) yi++;
            const y = yi >= 0 ? yields[yi] : undefined;
            d.y3m = y?.y3m ?? null; d.y2y = y?.y2y ?? null; d.y10y = y?.y10y ?? null;
            d.yieldSpread = d.y10y != null && d.y2y != null ? d.y10y - d.y2y : null;
            d.cdBreadthScore = (d.cdNewScore || 0) * d.cdShare;
            d.mcBreadthScore = -(d.mcNewScore || 0) * d.mcShare;
            d.netBreadthScore = d.cdBreadthScore + d.mcBreadthScore;
            d.cdWBreadthScore = selectedTicker ? (d.cdNewScore || 0) : (cdCapScore.get(d.date) || 0);
            d.mcWBreadthScore = -(selectedTicker ? (d.mcNewScore || 0) : (mcCapScore.get(d.date) || 0));
            // Combined CD (up) / MC (down) tracks
            INTERVAL_KEYS.forEach(k => { d[`mc_neg_${k}`] = -(d[`mc_${k}`] || 0); });
            d.mcNewScoreNeg = -(d.mcNewScore || 0);
        });

        if (minDate) {
            const minStr = format(minDate, 'yyyy-MM-dd');
            result = result.filter(d => d.date >= minStr);
        }
        if (maxDate) {
            const maxStr = format(maxDate, 'yyyy-MM-dd');
            result = result.filter(d => d.date <= maxStr);
        }

        return result;
    }, [spxData, cdBreadth, mcBreadth, cdSignalBreadth, mcSignalBreadth, cdScoreBreadth, mcScoreBreadth, cdBreakthroughScoreBreadth, mcBreakthroughScoreBreadth, cdCompanyBreadth, mcCompanyBreadth, tickerWeights, firstDates, capHistory, dmaBreadth, bondYields, effectiveWeights, minDate, maxDate, selectedTicker, tickers, fundamentals]);

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

    const ReferenceBlock = ({ yAxisId }: { yAxisId?: string }) => (
        selection && visibleData[Math.min(selection.start, selection.end)] && visibleData[Math.max(selection.start, selection.end)] ? (
            <ReferenceArea
                x1={visibleData[Math.min(selection.start, selection.end)].date}
                x2={visibleData[Math.max(selection.start, selection.end)].date}
                strokeOpacity={0}
                fill="hsl(var(--primary))"
                fillOpacity={0.1}
                {...(yAxisId ? { yAxisId } : {})}
            />
        ) : <></>
    );


    return (
        <div className={`flex flex-col ${selectedTicker ? "h-[1300px]" : "h-[1500px]"} border rounded-lg bg-card p-4`}>
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
                        onClick={toggleTooltips}
                        className={`px-2 py-1 text-xs font-medium rounded-md border shrink-0 ${showTooltips ? 'bg-primary text-primary-foreground border-primary' : 'border-border text-muted-foreground hover:bg-muted'}`}
                        title="Show the hover info boxes"
                    >
                        Tooltips {showTooltips ? 'On' : 'Off'}
                    </button>
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
                            <Tooltip content={showTooltips ? <PriceTooltip /> : DateOnlyTooltip} cursor={{ stroke: 'rgba(150,150,150,0.5)', strokeDasharray: '3 3' }} wrapperStyle={{ zIndex: 100 }} />
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
                            <Tooltip content={showTooltips ? <VolumeTooltip /> : HiddenTooltip} cursor={{ stroke: 'rgba(150,150,150,0.5)', strokeDasharray: '3 3' }} wrapperStyle={{ zIndex: 100 }} />
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

                {/* 3. CD (up) / MC (down) signals by interval (stacked bar) */}
                <div className="flex-[0.6] min-h-0 border-b border-border/50 relative" style={{ zIndex: 80 }}>
                    <span className="absolute top-3 left-2 text-[10px] font-medium z-10"><span className="text-[#22c55e]">CD</span> / <span className="text-[#f87171]">MC</span></span>
                    <div className="absolute top-3 right-2 flex gap-1 z-10">
                        {INTERVALS.map(intv => (
                            <span key={intv} className="text-[8px] font-medium" style={{ color: INTERVAL_COLORS[intv] }}>{intv}</span>
                        ))}
                    </div>
                    <ResponsiveContainer width="100%" height="100%">
                        <ComposedChart data={visibleData} syncId="breadthSync" margin={{ left: 5, right: 5, top: 5, bottom: 5 }} stackOffset="sign">
                            <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={1} />
                            {commonXAxis(true)}
                            <YAxis
                                orientation="left"
                                mirror={true}
                                domain={['auto', 'auto']}
                                tickFormatter={(val) => val === 0 ? '0' : `${Math.abs(val)}`}
                                width={38}
                                tick={{ fontSize: 10 }}
                                tickCount={3}
                            />
                            <Tooltip content={showTooltips ? <CombinedSignalTooltip /> : HiddenTooltip} cursor={{ stroke: 'rgba(150,150,150,0.5)', strokeDasharray: '3 3' }} wrapperStyle={{ zIndex: 100 }} />
                            <ReferenceLine y={0} stroke="hsl(var(--muted-foreground))" strokeOpacity={0.6} />
                            {INTERVALS.map(intv => (
                                <Bar
                                    key={`cd_${intv}`}
                                    dataKey={`cd_${intv}`}
                                    stackId="sig_stack"
                                    fill={INTERVAL_COLORS[intv]}
                                    name={`CD ${intv}`}
                                    isAnimationActive={false}
                                />
                            ))}
                            {INTERVALS.map(intv => (
                                <Bar
                                    key={`mc_neg_${intv}`}
                                    dataKey={`mc_neg_${intv}`}
                                    stackId="sig_stack"
                                    fill={INTERVAL_COLORS[intv]}
                                    name={`MC ${intv}`}
                                    isAnimationActive={false}
                                />
                            ))}
                            <ReferenceBlock />
                        </ComposedChart>
                    </ResponsiveContainer>
                </div>

                {/* 7. CD Score (up) / MC Score (down), indicator-weighted */}
                <div className="flex-[0.6] min-h-0 border-b border-border/50 relative" style={{ zIndex: 60 }}>
                    <span className="absolute top-3 left-2 text-[10px] font-medium z-10"><span className="text-[#22c55e]">CD Score</span> / <span className="text-[#ef4444]">MC Score</span></span>
                    <ResponsiveContainer width="100%" height="100%">
                        <ComposedChart data={visibleData} syncId="breadthSync" margin={{ left: 5, right: 5, top: 5, bottom: 5 }} stackOffset="sign">
                            <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={1} />
                            {commonXAxis(true)}
                            <YAxis
                                orientation="left"
                                mirror={true}
                                domain={['auto', 'auto']}
                                tickFormatter={(val) => val === 0 ? '0' : Number.isInteger(val) ? `${Math.abs(val)}` : Math.abs(val).toFixed(2)}
                                width={38}
                                tick={{ fontSize: 10 }}
                                tickCount={3}
                            />
                            <Tooltip content={showTooltips ? <CombinedScoreTooltip /> : HiddenTooltip} cursor={{ stroke: 'rgba(150,150,150,0.5)', strokeDasharray: '3 3' }} wrapperStyle={{ zIndex: 100 }} />
                            <ReferenceLine y={0} stroke="hsl(var(--muted-foreground))" strokeOpacity={0.6} />
                            <Bar dataKey="cdNewScore" stackId="score_stack" fill="#22c55e" name="CD Score" isAnimationActive={false} />
                            <Bar dataKey="mcNewScoreNeg" stackId="score_stack" fill="#ef4444" name="MC Score" isAnimationActive={false} />
                            <ReferenceBlock />
                        </ComposedChart>
                    </ResponsiveContainer>
                </div>

                {/* 9. Market Breadth: companies with a CD (up) / MC (down) signal that day */}
                <div className="flex-[0.5] min-h-0 border-b border-border/50 relative" style={{ zIndex: 40 }}>
                    <span className="absolute top-3 left-2 text-[10px] font-medium z-10">
                        Market Breadth <span className="text-muted-foreground font-normal">(companies with <span className="text-[#22c55e]">CD</span> / <span className="text-[#ef4444]">MC</span>)</span>
                    </span>
                    <ResponsiveContainer width="100%" height="100%">
                        <ComposedChart data={visibleData} syncId="breadthSync" margin={{ left: 5, right: 5, top: 5, bottom: 5 }} stackOffset="sign">
                            <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={1} />
                            {commonXAxis(true)}
                            <YAxis
                                orientation="left"
                                mirror={true}
                                domain={['auto', 'auto']}
                                tickFormatter={(val) => val === 0 ? '0' : `${Math.abs(val)}`}
                                width={38}
                                tick={{ fontSize: 10 }}
                                tickCount={3}
                            />
                            <Tooltip content={showTooltips ? <MarketBreadthTooltip kind="count" /> : HiddenTooltip} cursor={{ stroke: 'rgba(150,150,150,0.5)', strokeDasharray: '3 3' }} wrapperStyle={{ zIndex: 100 }} />
                            <ReferenceLine y={0} stroke="hsl(var(--muted-foreground))" strokeOpacity={0.6} />
                            <Bar dataKey="cdCompanies" stackId="mb" fill="#22c55e" name="CD companies" isAnimationActive={false} />
                            <Bar dataKey="mcCompaniesNeg" stackId="mb" fill="#ef4444" name="MC companies" isAnimationActive={false} />
                            <ReferenceBlock />
                        </ComposedChart>
                    </ResponsiveContainer>
                </div>

                {/* 10. Breadth Score: CD Score x CD share (up), MC Score x MC share (down) */}
                <div className="flex-[0.5] min-h-0 border-b border-border/50 relative" style={{ zIndex: 30 }}>
                    <span className="absolute top-3 left-2 text-[10px] font-medium z-10">
                        Breadth Score <span className="text-muted-foreground font-normal">(Score × share of companies, <span className="text-[#22c55e]">CD</span> + / <span className="text-[#ef4444]">MC</span> −)</span>
                    </span>
                    <ResponsiveContainer width="100%" height="100%">
                        <ComposedChart data={visibleData} syncId="breadthSync" margin={{ left: 5, right: 5, top: 5, bottom: 5 }} stackOffset="sign">
                            <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={1} />
                            {commonXAxis(true)}
                            <YAxis
                                orientation="left"
                                mirror={true}
                                domain={['auto', 'auto']}
                                tickFormatter={(val) => val === 0 ? '0' : Number.isInteger(val) ? val : val.toFixed(2)}
                                width={38}
                                tick={{ fontSize: 10 }}
                                tickCount={3}
                            />
                            <Tooltip content={showTooltips ? <MarketBreadthTooltip kind="score" /> : HiddenTooltip} cursor={{ stroke: 'rgba(150,150,150,0.5)', strokeDasharray: '3 3' }} wrapperStyle={{ zIndex: 100 }} />
                            <ReferenceLine y={0} stroke="hsl(var(--muted-foreground))" strokeOpacity={0.6} />
                            <Bar dataKey="cdBreadthScore" stackId="bs" fill="#22c55e" name="CD breadth score" isAnimationActive={false} />
                            <Bar dataKey="mcBreadthScore" stackId="bs" fill="#ef4444" name="MC breadth score" isAnimationActive={false} />
                            <ReferenceBlock />
                        </ComposedChart>
                    </ResponsiveContainer>
                </div>

                {/* 10b. Weighted Breadth Score: sum over tickers of (interval-weighted score x market-cap share) */}
                <div className="flex-[0.5] min-h-0 border-b border-border/50 relative" style={{ zIndex: 24 }}>
                    <span className="absolute top-3 left-2 text-[10px] font-medium z-10">
                        Weighted Breadth Score <span className="text-muted-foreground font-normal">(Σ score × market-cap share, <span className="text-[#22c55e]">CD</span> + / <span className="text-[#ef4444]">MC</span> −)</span>
                    </span>
                    {!selectedTicker && !(cdCompanyBreadth.some(c => c.scores) || mcCompanyBreadth.some(c => c.scores)) && (
                        <span className="absolute top-3 right-2 text-[10px] text-muted-foreground z-10 pointer-events-none">
                            Needs a new Run Analysis (per-stock scores not saved yet)
                        </span>
                    )}
                    {!selectedTicker && (cdCompanyBreadth.some(c => c.scores) || mcCompanyBreadth.some(c => c.scores)) && !(tickerWeights && Object.keys(tickerWeights).length > 0) && (
                        <span className="absolute top-3 right-2 text-[10px] text-muted-foreground z-10 pointer-events-none">
                            No market caps yet: every stock weighted equally
                        </span>
                    )}
                    <ResponsiveContainer width="100%" height="100%">
                        <ComposedChart data={visibleData} syncId="breadthSync" margin={{ left: 5, right: 5, top: 5, bottom: 5 }} stackOffset="sign">
                            <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={1} />
                            {commonXAxis(true)}
                            <YAxis
                                orientation="left"
                                mirror={true}
                                domain={['auto', 'auto']}
                                tickFormatter={(val) => val === 0 ? '0' : Number.isInteger(val) ? val : val.toFixed(2)}
                                width={38}
                                tick={{ fontSize: 10 }}
                                tickCount={3}
                            />
                            <Tooltip content={showTooltips ? <MarketBreadthTooltip kind="weighted" /> : HiddenTooltip} cursor={{ stroke: 'rgba(150,150,150,0.5)', strokeDasharray: '3 3' }} wrapperStyle={{ zIndex: 100 }} />
                            <ReferenceLine y={0} stroke="hsl(var(--muted-foreground))" strokeOpacity={0.6} />
                            <Bar dataKey="cdWBreadthScore" stackId="wbs" fill="#22c55e" name="CD weighted breadth score" isAnimationActive={false} />
                            <Bar dataKey="mcWBreadthScore" stackId="wbs" fill="#ef4444" name="MC weighted breadth score" isAnimationActive={false} />
                            <ReferenceBlock />
                        </ComposedChart>
                    </ResponsiveContainer>
                </div>

                {/* 10c. % of stocks closing above their 20 / 50 / 200-day moving average (stock lists only) */}
                {!selectedTicker && <div className="flex-[0.5] min-h-0 border-b border-border/50 relative" style={{ zIndex: 20 }}>
                    <span className="absolute top-3 left-2 text-[10px] font-medium z-10">
                        % Above DMA <span className="text-muted-foreground font-normal">(stocks closing above their <span className="text-[#38bdf8]">20</span> / <span className="text-[#f59e0b]">50</span> / <span className="text-[#a78bfa]">200</span>-day average)</span>
                    </span>
                    {dmaBreadth.length === 0 && (
                        <span className="absolute top-3 right-2 text-[10px] text-muted-foreground z-10 pointer-events-none">
                            No daily price history for this list yet
                        </span>
                    )}
                    <ResponsiveContainer width="100%" height="100%">
                        <ComposedChart data={visibleData} syncId="breadthSync" margin={{ left: 5, right: 5, top: 5, bottom: 5 }}>
                            <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={1} />
                            {commonXAxis(true)}
                            <YAxis
                                orientation="left"
                                mirror={true}
                                domain={[0, 100]}
                                ticks={[20, 50, 80]}
                                tickFormatter={(val) => `${val}%`}
                                width={38}
                                tick={{ fontSize: 10 }}
                            />
                            <Tooltip content={showTooltips ? <DmaTooltip /> : HiddenTooltip} cursor={{ stroke: 'rgba(150,150,150,0.5)', strokeDasharray: '3 3' }} wrapperStyle={{ zIndex: 100 }} />
                            <ReferenceLine y={80} stroke="#22c55e" strokeOpacity={0.35} strokeDasharray="4 4" />
                            <ReferenceLine y={50} stroke="hsl(var(--muted-foreground))" strokeOpacity={0.4} />
                            <ReferenceLine y={20} stroke="#ef4444" strokeOpacity={0.35} strokeDasharray="4 4" />
                            <Line type="monotone" dataKey="dma20" stroke="#38bdf8" strokeWidth={1.2} dot={false} connectNulls isAnimationActive={false} name="% above 20DMA" />
                            <Line type="monotone" dataKey="dma50" stroke="#f59e0b" strokeWidth={1.2} dot={false} connectNulls isAnimationActive={false} name="% above 50DMA" />
                            <Line type="monotone" dataKey="dma200" stroke="#a78bfa" strokeWidth={1.4} dot={false} connectNulls isAnimationActive={false} name="% above 200DMA" />
                            <ReferenceBlock />
                        </ComposedChart>
                    </ResponsiveContainer>
                </div>}

                {/* US Treasury yields: 3-month / 2-year / 10-year (left), 10y − 2y spread (right, shaded) */}
                <div className="flex-[0.6] min-h-0 border-b border-border/50 relative" style={{ zIndex: 9 }}>
                    <span className="absolute top-3 left-2 text-[10px] font-medium z-10">
                        US Treasury Yield <span className="text-muted-foreground font-normal">(<span className="text-[#60a5fa]">3-month</span> / <span className="text-[#fbbf24]">2-year</span> / <span className="text-[#f87171]">10-year</span>, % left · <span className="text-foreground">10y − 2y spread</span>, right, shaded)</span>
                    </span>
                    {bondYields.length === 0 && (
                        <span className="absolute top-3 right-2 text-[10px] text-muted-foreground z-10 pointer-events-none">
                            Yield data not loaded
                        </span>
                    )}
                    <ResponsiveContainer width="100%" height="100%">
                        <ComposedChart data={visibleData} syncId="breadthSync" margin={{ left: 5, right: 5, top: 5, bottom: 5 }}>
                            <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={1} />
                            {commonXAxis(true)}
                            <YAxis
                                yAxisId="yield"
                                orientation="left"
                                mirror={true}
                                domain={['auto', 'auto']}
                                tickFormatter={(val) => `${Number(val).toFixed(1)}%`}
                                width={38}
                                tick={{ fontSize: 10 }}
                                tickCount={3}
                            />
                            <YAxis
                                yAxisId="spread"
                                orientation="right"
                                mirror={true}
                                domain={['auto', 'auto']}
                                tickFormatter={(val) => `${Number(val).toFixed(1)}%`}
                                width={38}
                                tick={{ fontSize: 10 }}
                                tickCount={3}
                            />
                            <Tooltip content={showTooltips ? <BondYieldTooltip /> : HiddenTooltip} cursor={{ stroke: 'rgba(150,150,150,0.5)', strokeDasharray: '3 3' }} wrapperStyle={{ zIndex: 100 }} />
                            <ReferenceLine yAxisId="spread" y={0} stroke="hsl(var(--muted-foreground))" strokeOpacity={0.5} strokeDasharray="4 4" />
                            <Area yAxisId="spread" type="monotone" dataKey="yieldSpread" stroke="hsl(var(--foreground))" strokeOpacity={0.4} fill="hsl(var(--foreground))" fillOpacity={0.08} strokeWidth={1} dot={false} isAnimationActive={false} connectNulls />
                            <Line yAxisId="yield" type="monotone" dataKey="y3m" stroke="#60a5fa" strokeWidth={1.2} dot={false} connectNulls isAnimationActive={false} />
                            <Line yAxisId="yield" type="monotone" dataKey="y2y" stroke="#fbbf24" strokeWidth={1.2} dot={false} connectNulls isAnimationActive={false} />
                            <Line yAxisId="yield" type="monotone" dataKey="y10y" stroke="#f87171" strokeWidth={1.5} dot={false} connectNulls isAnimationActive={false} />
                            <ReferenceBlock yAxisId="yield" />
                        </ComposedChart>
                    </ResponsiveContainer>
                </div>

                {/* Quarterly fundamentals: revenue / net income / gross margin */}
                <div className="flex-[0.7] min-h-0 border-b border-border/50 relative" style={{ zIndex: 8 }}>
                    <span className="absolute top-3 left-2 text-[10px] font-medium z-10">
                        <span className="text-[#60a5fa]">Revenue</span> / <span className="text-[#fbbf24]">Gross Margin % (right)</span> / <span className="text-[#34d399]">Net Income</span>
                        <span className="text-muted-foreground"> {selectedTicker ? '(quarterly)' : '(stock list total, quarterly)'}</span>
                    </span>
                    <ResponsiveContainer width="100%" height="100%">
                        <ComposedChart data={visibleData} syncId="breadthSync" margin={{ left: 5, right: 5, top: 5, bottom: 5 }}>
                            <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={1} />
                            {commonXAxis(true)}
                            <YAxis
                                yAxisId="money"
                                orientation="left"
                                mirror={true}
                                domain={['auto', 'auto']}
                                tickFormatter={(val) => formatMoney(val)}
                                width={50}
                                tick={{ fontSize: 10 }}
                                tickCount={3}
                            />
                            <Tooltip content={showTooltips ? <FundamentalsTooltip part="income" /> : HiddenTooltip} cursor={{ stroke: 'rgba(150,150,150,0.5)', strokeDasharray: '3 3' }} wrapperStyle={{ zIndex: 100 }} />
                            <YAxis
                                yAxisId="margin"
                                orientation="right"
                                mirror={true}
                                domain={['auto', 'auto']}
                                tickFormatter={(val) => `${Number(val).toFixed(0)}%`}
                                width={38}
                                tick={{ fontSize: 10 }}
                                tickCount={3}
                            />
                            <Line yAxisId="money" type="stepAfter" dataKey="fin_revenue" stroke="#60a5fa" dot={false} strokeWidth={1.5} isAnimationActive={false} connectNulls />
                            <Line yAxisId="money" type="stepAfter" dataKey="fin_net" stroke="#34d399" dot={false} strokeWidth={1.5} isAnimationActive={false} connectNulls />
                            <Line yAxisId="margin" type="stepAfter" dataKey="fin_gross_margin" stroke="#fbbf24" dot={false} strokeWidth={1.5} strokeDasharray="4 2" isAnimationActive={false} connectNulls />
                            <ReferenceBlock yAxisId="money" />
                        </ComposedChart>
                    </ResponsiveContainer>
                </div>

                {/* Quarterly cash flow: operating cash flow, capex, free cash flow; FCF margin / conversion on the right */}
                <div className="flex-[0.7] min-h-0 border-b border-border/50 relative" style={{ zIndex: 7 }}>
                    <span className="absolute top-3 left-2 text-[10px] font-medium z-10">
                        <span className="text-[#22d3ee]">Operating Cash Flow</span> / <span className="text-[#fb923c]">Capex</span> / <span className="text-[#f472b6]">Free Cash Flow</span>
                        {' · '}<span className="text-foreground">FCF Conversion (FCF ÷ net income, % right, dashed)</span>
                    </span>
                    <ResponsiveContainer width="100%" height="100%">
                        <ComposedChart data={visibleData} syncId="breadthSync" margin={{ left: 5, right: 5, top: 5, bottom: 5 }}>
                            <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={1} />
                            {commonXAxis(true)}
                            <YAxis
                                yAxisId="money"
                                orientation="left"
                                mirror={true}
                                domain={['auto', 'auto']}
                                tickFormatter={(val) => formatMoney(val)}
                                width={50}
                                tick={{ fontSize: 10 }}
                                tickCount={3}
                            />
                            <Tooltip content={showTooltips ? <FundamentalsTooltip part="cash" /> : HiddenTooltip} cursor={{ stroke: 'rgba(150,150,150,0.5)', strokeDasharray: '3 3' }} wrapperStyle={{ zIndex: 100 }} />
                            <YAxis
                                yAxisId="pct"
                                orientation="right"
                                mirror={true}
                                domain={['auto', 'auto']}
                                tickFormatter={(val) => `${Number(val).toFixed(0)}%`}
                                width={38}
                                tick={{ fontSize: 10 }}
                                tickCount={3}
                            />
                            <ReferenceLine yAxisId="money" y={0} stroke="hsl(var(--muted-foreground))" strokeOpacity={0.5} />
                            <Line yAxisId="money" type="stepAfter" dataKey="fin_ocf" stroke="#22d3ee" dot={false} strokeWidth={1.3} isAnimationActive={false} connectNulls />
                            <Line yAxisId="money" type="stepAfter" dataKey="fin_capex" stroke="#fb923c" dot={false} strokeWidth={1.3} isAnimationActive={false} connectNulls />
                            <Line yAxisId="money" type="stepAfter" dataKey="fin_fcf" stroke="#f472b6" dot={false} strokeWidth={1.8} isAnimationActive={false} connectNulls />
                            <Line yAxisId="pct" type="stepAfter" dataKey="fin_fcf_conv" stroke="hsl(var(--foreground))" strokeOpacity={0.7} dot={false} strokeWidth={1.2} strokeDasharray="4 2" isAnimationActive={false} connectNulls />
                            <ReferenceBlock yAxisId="money" />
                        </ComposedChart>
                    </ResponsiveContainer>
                </div>

                {/* Quarterly fundamentals: EPS (stock) or share of companies with rising EPS (stock list) */}
                <div className="flex-[0.7] min-h-0 relative" style={{ zIndex: 6 }}>
                    <span className="absolute top-3 left-2 text-[10px] font-medium text-[#a78bfa] z-10">
                        {selectedTicker ? 'EPS (quarterly, diluted)' : <>EPS up vs previous quarter / <span className="text-[#f472b6]">free cash flow positive</span> (% of companies)</>}
                    </span>
                    <ResponsiveContainer width="100%" height="100%">
                        <ComposedChart data={visibleData} syncId="breadthSync" margin={{ left: 5, right: 5, top: 5, bottom: 5 }}>
                            <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={1} />
                            {commonXAxis(false)}
                            <YAxis
                                orientation="left"
                                mirror={true}
                                domain={selectedTicker ? ['auto', 'auto'] : [0, 100]}
                                tickFormatter={(val) => selectedTicker ? Number(val).toFixed(2) : `${val}%`}
                                width={38}
                                tick={{ fontSize: 10 }}
                                tickCount={3}
                            />
                            <Tooltip content={showTooltips ? <FundamentalsTooltip part="eps" /> : HiddenTooltip} cursor={{ stroke: 'rgba(150,150,150,0.5)', strokeDasharray: '3 3' }} wrapperStyle={{ zIndex: 100 }} />
                            <Line type="stepAfter" dataKey={selectedTicker ? 'fin_eps' : 'fin_eps_up'} stroke="#a78bfa" dot={false} strokeWidth={1.5} isAnimationActive={false} connectNulls />
                            {!selectedTicker && <Line type="stepAfter" dataKey="fin_fcf_pos" stroke="#f472b6" dot={false} strokeWidth={1.5} isAnimationActive={false} connectNulls />}
                            <ReferenceBlock />
                        </ComposedChart>
                    </ResponsiveContainer>
                </div>
            </div>
        </div>
    );
};
