import React, { useMemo } from 'react';
import {
    BarChart,
    Bar,
    XAxis,
    YAxis,
    CartesianGrid,
    ReferenceLine,
    ResponsiveContainer,
    Cell,
    Tooltip,
} from 'recharts';
import { Maximize2, Minimize2 } from 'lucide-react';
import { cn } from '../utils/cn';

interface HistogramData {
    label: string;
    values: number[];   // All daily values for the distribution
    today: number;      // Current / latest day's value
    color: 'green' | 'red';
}

// Compute percentile of a value within a sorted list
const computePercentile = (value: number, sorted: number[]): number => {
    if (sorted.length === 0) return 0;
    const count = sorted.filter(v => v <= value).length;
    return (count / sorted.length) * 100;
};

const fmt = (v: number) => v < 10 ? v.toFixed(v < 1 ? 2 : 1) : v.toFixed(0);

// Single mini histogram using Recharts
const MiniHistogram = ({ data, height = 140, isFullscreen = false }: { data: HistogramData; height?: number; isFullscreen?: boolean }) => {
    const computed = useMemo(() => {
        const { values, today } = data;
        if (values.length === 0) return null;

        const min = Math.min(...values);
        const max = Math.max(...values);
        const range = max - min || 1;
        const numBins = Math.min(20, Math.max(8, Math.ceil(Math.sqrt(values.length))));
        const binWidth = range / numBins;

        // Create bins
        const bins = Array.from({ length: numBins }, (_, i) => ({
            start: min + i * binWidth,
            end: min + (i + 1) * binWidth,
            count: 0,
            midpoint: min + (i + 0.5) * binWidth,
        }));

        for (const v of values) {
            let idx = Math.floor((v - min) / binWidth);
            if (idx >= numBins) idx = numBins - 1;
            if (idx < 0) idx = 0;
            bins[idx].count++;
        }

        // Today's bin
        let todayBinIdx = Math.floor((today - min) / binWidth);
        if (todayBinIdx >= numBins) todayBinIdx = numBins - 1;
        if (todayBinIdx < 0) todayBinIdx = 0;

        // Stats
        const sorted = [...values].sort((a, b) => a - b);
        const avg = values.reduce((a, b) => a + b, 0) / values.length;
        const median = sorted.length % 2 === 0
            ? (sorted[sorted.length / 2 - 1] + sorted[sorted.length / 2]) / 2
            : sorted[Math.floor(sorted.length / 2)];
        const percentile = computePercentile(today, sorted);

        const chartData = bins.map((bin, i) => ({
            name: String(i),  // Must be uniquely identifiable for ReferenceLine
            midpoint: bin.midpoint,
            count: bin.count,
            logCount: Math.log10(bin.count + 1),
            isToday: i === todayBinIdx,
        }));

        const maxLogCount = Math.max(...chartData.map(d => d.logCount), 0.01);

        return { chartData, avg, median, percentile, todayBinIdx, maxLogCount, min, max: bins[bins.length - 1].end, range };
    }, [data]);

    if (!computed) {
        return <div className="text-xs text-muted-foreground text-center py-2">No data</div>;
    }

    const { chartData, avg, median, percentile } = computed;

    const colorMap = {
        green: { bar: 'rgba(60, 179, 113, 0.5)', todayBar: '#25c660ff', label: 'text-green-600' },
        red: { bar: 'rgba(255,99,71,0.5)', todayBar: '#fd7373ff', label: 'text-red-600' },
    };
    const colors = colorMap[data.color];

    // Median and average as x-axis positions (bin index, fractional)
    const min = computed.min;
    const range = computed.range;
    const numBins = chartData.length;
    const medianBinPos = ((median - min) / range) * numBins;
    const avgBinPos = ((avg - min) / range) * numBins;

    // Convert to chart name for ReferenceLine (use index-based)
    // ReferenceLine with x works on category axis by name — we'll use x as number on the index
    // Instead, we use a custom approach: map median/avg to the nearest bin name
    const medianBinIdx = Math.min(Math.max(Math.round(medianBinPos), 0), numBins - 1);
    const avgBinIdx = Math.min(Math.max(Math.round(avgBinPos), 0), numBins - 1);

    return (
        <div className="w-full">
            <div className="flex items-center justify-between mb-0.5 px-0.5">
                <span className={cn(isFullscreen ? "text-sm" : "text-[11px]", "font-semibold", colors.label)}>{data.label}</span>
                {isFullscreen ? (
                    <span className="text-xs text-muted-foreground space-x-2">
                        <span style={{ color: '#c026d3' }}>med: {fmt(median)}</span>
                        <span style={{ color: '#3b82f6' }}>avg: {fmt(avg)}</span>
                        <span>today: {fmt(data.today)}</span>
                        <span className="opacity-70">P{percentile.toFixed(0)}</span>
                    </span>
                ) : (
                    <span className="text-[10px] text-muted-foreground space-x-1">
                        <span style={{ color: '#c026d3' }}>m:{fmt(median)}</span>
                        <span style={{ color: '#3b82f6' }}>a:{fmt(avg)}</span>
                        <span>t:{fmt(data.today)}</span>
                        <span className="opacity-70">P{percentile.toFixed(0)}</span>
                    </span>
                )}
            </div>
            <ResponsiveContainer width="100%" height={height}>
                <BarChart data={chartData} margin={{ top: 4, right: 4, bottom: 2, left: -30 }} barCategoryGap="8%">
                    <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={0.15} />
                    <XAxis
                        dataKey="name"
                        tick={{ fontSize: 10 }}
                        tickLine={{ strokeWidth: 0.5 }}
                        axisLine={{ strokeWidth: 0.5 }}
                        interval="preserveStartEnd"
                        tickFormatter={(value, index) => {
                            const d = chartData[index];
                            return d ? fmt(d.midpoint) : value;
                        }}
                    />
                    <YAxis
                        dataKey="logCount"
                        tick={{ fontSize: 10 }}
                        tickLine={{ strokeWidth: 0.5 }}
                        axisLine={{ strokeWidth: 0.5 }}
                        tickFormatter={(v: number) => {
                            const raw = Math.round(Math.pow(10, v) - 1);
                            return raw <= 0 ? '0' : String(raw);
                        }}
                        domain={[0, 'auto']}
                    />
                    <Tooltip
                        content={({ active, payload }) => {
                            if (!active || !payload || !payload[0]) return null;
                            const d = payload[0].payload;
                            return (
                                <div className="bg-popover border border-border rounded px-2 py-1 text-xs shadow-md">
                                    <div>Bin: {fmt(d.midpoint)}</div>
                                    <div>Count: {d.count}</div>
                                    {d.isToday && <div className="font-bold mt-0.5">← Today</div>}
                                </div>
                            );
                        }}
                    />
                    {/* Reference lines for median and average */}
                    <ReferenceLine
                        x={chartData[medianBinIdx]?.name}
                        stroke="#c026d3"
                        strokeWidth={1.5}
                        strokeDasharray="6 3"
                    />
                    <ReferenceLine
                        x={chartData[avgBinIdx]?.name}
                        stroke="#3b82f6"
                        strokeWidth={1.5}
                        strokeDasharray="4 2"
                    />
                    <Bar dataKey="logCount" radius={[2, 2, 0, 0]}>
                        {chartData.map((entry, index) => (
                            <Cell
                                key={`cell-${index}`}
                                fill={entry.isToday ? colors.todayBar : colors.bar}
                                stroke={entry.isToday ? colors.todayBar : 'none'}
                                strokeWidth={entry.isToday ? 2 : 0}
                            />
                        ))}
                    </Bar>
                </BarChart>
            </ResponsiveContainer>
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
    cdBreadth: { date: string; count_1h: number; count_2h: number; count_3h: number; count_4h: number; count_1d: number }[];
    mcBreadth: { date: string; count_1h: number; count_2h: number; count_3h: number; count_4h: number; count_1d: number }[];
    cdBreakthroughScoreBreadth: { date: string; score_1h: number; score_2h: number; score_3h: number; score_4h: number; score_1d: number; total_score: number }[];
    mcBreakthroughScoreBreadth: { date: string; score_1h: number; score_2h: number; score_3h: number; score_4h: number; score_1d: number; total_score: number }[];
    intervalWeights?: Record<string, number>;
    tickers: string[];
    filteredSpxData: any[];
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
    cdBreadth,
    mcBreadth,
    cdBreakthroughScoreBreadth,
    mcBreakthroughScoreBreadth,
    intervalWeights,
    tickers,
    filteredSpxData,
    onNavigateRight,
    onMaximize,
    isFullscreen = false,
}) => {
    const divisor = tickers.length > 0 ? tickers.length : 1;
    const effectiveWeights = intervalWeights || { '1h': 1, '2h': 2, '3h': 4, '4h': 8, '1d': 32 };

    const latestDate = filteredSpxData && filteredSpxData.length > 0
        ? filteredSpxData[filteredSpxData.length - 1]?.time?.split('T')[0] ?? ''
        : '';
    const totalDays = filteredSpxData ? filteredSpxData.length : 0;

    const countValues = (data: { count_1h: number; count_2h: number; count_3h: number; count_4h: number; count_1d: number; date: string }[]) => {
        const totalCount = (d: typeof data[0]) => ((d.count_1h || 0) + (d.count_2h || 0) + (d.count_3h || 0) + (d.count_4h || 0) + (d.count_1d || 0)) / divisor;
        const vals = data.map(d => totalCount(d));
        const todayEntry = data.find(d => d.date === latestDate);
        const today = todayEntry ? totalCount(todayEntry) : 0;
        return { values: vals, today };
    };

    const scoreValues = (data: { score_1h: number; score_2h: number; score_3h: number; score_4h: number; score_1d: number; date: string }[]) => {
        const totalScore = (d: typeof data[0]) => {
            return ((d.score_1h || 0) * effectiveWeights['1h'] + (d.score_2h || 0) * effectiveWeights['2h']
                + (d.score_3h || 0) * effectiveWeights['3h'] + (d.score_4h || 0) * effectiveWeights['4h']
                + (d.score_1d || 0) * effectiveWeights['1d']) / divisor;
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
        const cdBt = countValues(cdBreadth);
        const mcBt = countValues(mcBreadth);
        const cdBtScore = scoreValues(cdBreakthroughScoreBreadth);
        const mcBtScore = scoreValues(mcBreakthroughScoreBreadth);

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
                section: 'CD/MC BT', items: [
                    { label: 'CD', values: pad(cdBt.values), today: cdBt.today, color: 'green' as const },
                    { label: 'MC', values: pad(mcBt.values), today: mcBt.today, color: 'red' as const },
                ]
            },
            {
                section: 'CD/MC BT Score', items: [
                    { label: 'CD', values: pad(cdBtScore.values), today: cdBtScore.today, color: 'green' as const },
                    { label: 'MC', values: pad(mcBtScore.values), today: mcBtScore.today, color: 'red' as const },
                ]
            },
        ];
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [cdSignalBreadth, mcSignalBreadth, cdScoreBreadth, mcScoreBreadth, cdBreadth, mcBreadth, cdBreakthroughScoreBreadth, mcBreakthroughScoreBreadth, tickers, filteredSpxData, intervalWeights]);

    const histogramHeight = isFullscreen ? 150 : 130;

    return (
        <div className="h-full flex flex-col overflow-hidden">
            {/* Header */}
            <div className="p-2 border-b bg-muted/30 flex justify-between items-center shrink-0">
                <span className="text-sm font-medium">{title} — Distributions</span>
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
                        Back to summary →
                    </button>
                </div>
            </div>

            {/* Histograms grid — 2 per row */}
            <div className="flex-1 overflow-y-auto p-3">
                <div className="grid grid-cols-2 gap-x-4 gap-y-1">
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
