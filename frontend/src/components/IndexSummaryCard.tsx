import React, { useMemo, useState } from 'react';
import { subDays, parseISO, isAfter, format } from 'date-fns';
import { useQuery } from '@tanstack/react-query';
import { analysisApi } from '../services/api';
import { MarketBreadthChart } from './MarketBreadthChart';
import { cn } from '../utils/cn';

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

interface IndexSummaryCardProps {
    title: string;
    spxData: any[];
    cdBreadth: BreadthDataPoint[];
    mcBreadth: BreadthDataPoint[];
    cdSignalBreadth?: SignalBreadthDataPoint[];
    mcSignalBreadth?: SignalBreadthDataPoint[];
    cdScoreBreadth?: { date: string, score_1h: number, score_2h: number, score_3h: number, score_4h: number, score_1d: number, total_score: number }[];
    mcScoreBreadth?: { date: string, score_1h: number, score_2h: number, score_3h: number, score_4h: number, score_1d: number, total_score: number }[];
    cdBreakthroughScoreBreadth?: { date: string, score_1h: number, score_2h: number, score_3h: number, score_4h: number, score_1d: number, total_score: number }[];
    mcBreakthroughScoreBreadth?: { date: string, score_1h: number, score_2h: number, score_3h: number, score_4h: number, score_1d: number, total_score: number }[];
    intervalWeights?: Record<string, number>;
    minDate: Date;
    signals1234?: { cd_dates: string[], mc_dates: string[] };
    tickers?: string[];
    indexTicker?: string;
}

// Percentile meter: a horizontal bar showing where the current value falls
const PercentileMeter = ({ percentile, label, value, color }: {
    percentile: number,
    label: string,
    value: string,
    color: 'green' | 'red' | 'blue'
}) => {
    const colorMap = {
        green: { bg: 'bg-green-500', track: 'bg-green-500/15', text: 'text-green-600' },
        red: { bg: 'bg-red-500', track: 'bg-red-500/15', text: 'text-red-600' },
        blue: { bg: 'bg-blue-500', track: 'bg-blue-500/15', text: 'text-blue-600' }
    };
    const c = colorMap[color];

    return (
        <div className="flex items-center gap-2">
            <span className={cn("text-xs font-medium w-8 shrink-0", c.text)}>{label}</span>
            <div className="flex-1 flex items-center gap-2">
                <div className={cn("relative h-2 flex-1 rounded-full overflow-hidden", c.track)}>
                    <div
                        className={cn("absolute inset-y-0 left-0 rounded-full transition-all duration-500", c.bg)}
                        style={{ width: `${Math.min(100, Math.max(0, percentile))}%`, opacity: 0.8 }}
                    />
                    {/* Marker line at 50th percentile */}
                    <div className="absolute inset-y-0 left-1/2 w-px bg-foreground/20" />
                </div>
                <span className="text-[10px] text-muted-foreground w-20 text-right shrink-0">
                    {value}
                </span>
                <span className={cn("text-[10px] font-semibold w-8 text-right shrink-0", c.text)}>
                    P{Math.round(percentile)}
                </span>
            </div>
        </div>
    );
};

export const IndexSummaryCard: React.FC<IndexSummaryCardProps> = ({
    title,
    spxData,
    cdBreadth,
    mcBreadth,
    cdSignalBreadth = [],
    mcSignalBreadth = [],
    cdScoreBreadth = [],
    mcScoreBreadth = [],
    cdBreakthroughScoreBreadth = [],
    mcBreakthroughScoreBreadth = [],
    intervalWeights,
    minDate,
    signals1234,
    tickers = [],
    indexTicker
}) => {
    const [flipped, setFlipped] = useState(false);
    const [selectedTicker, setSelectedTicker] = useState<string>('');

    // Effective ticker is either the selected component or the index itself
    const effectiveTicker = selectedTicker || indexTicker;

    // Fetch price history for the selected component stock (only if selected)
    const { data: stockData } = useQuery({
        queryKey: ['stockPriceHistory', selectedTicker, '1d'],
        queryFn: () => analysisApi.getPriceHistory(selectedTicker, '1d'),
        staleTime: 1000 * 60 * 60, // 1 hour
        enabled: !!selectedTicker && flipped
    });

    // Fetch per-ticker signal/score data across all intervals (for component OR index)
    const { data: tickerSignals } = useQuery({
        queryKey: ['tickerSignals', effectiveTicker],
        queryFn: () => effectiveTicker ? analysisApi.getTickerSignals(effectiveTicker) : null,
        staleTime: 1000 * 60 * 60,
        enabled: !!effectiveTicker && flipped
    });

    // When a ticker is selected, swap index-level breadth with per-ticker data
    // If NO ticker selected (Index view):
    // - Panels use CD/MC Breadth (Sector Sums) passed via props
    // - Chart uses spxData (Index Price + Index Signals)
    const useTickerSignals = !!selectedTicker && !!tickerSignals;

    const effectiveCdBreadth = useTickerSignals ? tickerSignals!.cd_breadth : cdBreadth;
    const effectiveMcBreadth = useTickerSignals ? tickerSignals!.mc_breadth : mcBreadth;
    const effectiveCdSignalBreadth = useTickerSignals ? tickerSignals!.cd_signal_breadth : cdSignalBreadth;
    const effectiveMcSignalBreadth = useTickerSignals ? tickerSignals!.mc_signal_breadth : mcSignalBreadth;
    const effectiveCdScoreBreadth = useTickerSignals ? tickerSignals!.cd_score_breadth : cdScoreBreadth;
    const effectiveMcScoreBreadth = useTickerSignals ? tickerSignals!.mc_score_breadth : mcScoreBreadth;
    const effectiveCdBtScoreBreadth = useTickerSignals ? (tickerSignals!.cd_breakthrough_score_breadth ?? []) : cdBreakthroughScoreBreadth;
    const effectiveMcBtScoreBreadth = useTickerSignals ? (tickerSignals!.mc_breakthrough_score_breadth ?? []) : mcBreakthroughScoreBreadth;

    // --- Derive summary metrics from existing data ---

    // Latest close price + daily change
    const priceInfo = useMemo(() => {
        if (!spxData || spxData.length === 0) return null;
        const latest = spxData[spxData.length - 1];
        const prev = spxData.length > 1 ? spxData[spxData.length - 2] : null;
        const change = prev ? ((latest.close - prev.close) / prev.close) * 100 : 0;
        return {
            close: latest.close,
            change,
            date: latest.time?.split('T')[0] ?? ''
        };
    }, [spxData]);

    // CD/MC signals for last 7 trading days (from price history 1d data)
    const recentSignals = useMemo(() => {
        if (!spxData || spxData.length === 0) return [];
        const last7 = spxData.slice(-7);
        return last7.map(d => ({
            date: d.time?.split('T')[0] ?? '',
            cd: !!d.cd_signal,
            mc: !!d.mc_signal
        }));
    }, [spxData]);

    // 1234 signals for last 7 days
    const recent1234 = useMemo(() => {
        if (!signals1234) return { cd: [] as string[], mc: [] as string[] };
        const cutoff = subDays(new Date(), 7);
        const cdRecent = (signals1234.cd_dates || []).filter(d => {
            try { return isAfter(parseISO(d), cutoff); } catch { return false; }
        });
        const mcRecent = (signals1234.mc_dates || []).filter(d => {
            try { return isAfter(parseISO(d), cutoff); } catch { return false; }
        });
        return { cd: cdRecent, mc: mcRecent };
    }, [signals1234]);

    // Helper: compute percentile of a value within a sorted array
    const computePercentile = (value: number, data: number[]): number => {
        if (data.length === 0) return 0;
        const sorted = [...data].sort((a, b) => a - b);
        const below = sorted.filter(v => v < value).length;
        const equal = sorted.filter(v => v === value).length;
        return ((below + equal * 0.5) / sorted.length) * 100;
    };

    // Breadth stats: today's count + percentile
    const breadthStats = useMemo(() => {
        // Get the latest trading date from price data to match breadth entries
        const latestDate = spxData && spxData.length > 0
            ? spxData[spxData.length - 1]?.time?.split('T')[0] ?? ''
            : '';

        const computeStats = (data: BreadthDataPoint[]) => {
            if (!data || data.length === 0) return { today: 0, avg: 0, median: 0, percentile: 0 };
            const totalCount = (d: BreadthDataPoint) => (d.count_1h || 0) + (d.count_2h || 0) + (d.count_3h || 0) + (d.count_4h || 0) + (d.count_1d || 0);
            // Find today's count by matching the latest trading date (default to 0 if no entry)
            const todayEntry = data.find(d => d.date === latestDate);
            const today = todayEntry ? totalCount(todayEntry) : 0;
            const counts = data.map(d => totalCount(d));
            const avg = counts.reduce((a, b) => a + b, 0) / counts.length;
            const sorted = [...counts].sort((a, b) => a - b);
            const median = sorted.length % 2 === 0
                ? (sorted[sorted.length / 2 - 1] + sorted[sorted.length / 2]) / 2
                : sorted[Math.floor(sorted.length / 2)];
            const percentile = computePercentile(today, counts);
            return { today, avg: Math.round(avg * 10) / 10, median, percentile };
        };
        return {
            cd: computeStats(cdBreadth),
            mc: computeStats(mcBreadth)
        };
    }, [cdBreadth, mcBreadth, spxData]);

    // Signal Breadth stats (Today vs Avg + Percentile)
    const signalStats = useMemo(() => {
        const latestDate = spxData && spxData.length > 0
            ? spxData[spxData.length - 1]?.time?.split('T')[0] ?? ''
            : '';

        const computeStats = (data: any[]) => {
            if (!data || data.length === 0) return { today: 0, avg: 0, median: 0, percentile: 0 };
            const totalCount = (d: any) => (d.count_1h || 0) + (d.count_2h || 0) + (d.count_3h || 0) + (d.count_4h || 0) + (d.count_1d || 0);
            const todayEntry = data.find(d => d.date === latestDate);
            const today = todayEntry ? totalCount(todayEntry) : 0;
            const counts = data.map(d => totalCount(d));
            const avg = counts.reduce((a, b) => a + b, 0) / counts.length;
            const sorted = [...counts].sort((a, b) => a - b);
            const median = sorted.length % 2 === 0
                ? (sorted[sorted.length / 2 - 1] + sorted[sorted.length / 2]) / 2
                : sorted[Math.floor(sorted.length / 2)];
            const percentile = computePercentile(today, counts);
            return { today, avg: Math.round(avg * 10) / 10, median, percentile };
        };
        return {
            cd: computeStats(cdSignalBreadth),
            mc: computeStats(mcSignalBreadth)
        };
    }, [cdSignalBreadth, mcSignalBreadth, spxData]);

    // Score Breadth stats (Today vs Avg + Percentile)
    const scoreStats = useMemo(() => {
        const latestDate = spxData && spxData.length > 0
            ? spxData[spxData.length - 1]?.time?.split('T')[0] ?? ''
            : '';

        const computeStats = (data: any[]) => {
            if (!data || data.length === 0) return { today: 0, avg: 0, median: 0, percentile: 0 };
            const totalScore = (d: any) => d.total_score || 0;
            const todayEntry = data.find(d => d.date === latestDate);
            const today = todayEntry ? totalScore(todayEntry) : 0;
            const scores = data.map(d => totalScore(d));
            const avg = scores.reduce((a, b) => a + b, 0) / scores.length;
            const sorted = [...scores].sort((a, b) => a - b);
            const median = sorted.length % 2 === 0
                ? (sorted[sorted.length / 2 - 1] + sorted[sorted.length / 2]) / 2
                : sorted[Math.floor(sorted.length / 2)];
            const percentile = computePercentile(today, scores);
            return { today, avg: Math.round(avg * 10) / 10, median, percentile };
        };
        return {
            cd: computeStats(cdScoreBreadth),
            mc: computeStats(mcScoreBreadth)
        };
    }, [cdScoreBreadth, mcScoreBreadth, spxData]);

    // Breakthrough Score stats (same approach as scoreStats)
    const breakthroughScoreStats = useMemo(() => {
        if (!spxData || spxData.length === 0) return { cd: { today: 0, avg: 0, median: 0, percentile: 0 }, mc: { today: 0, avg: 0, median: 0, percentile: 0 } };
        const latestDate = spxData[spxData.length - 1]?.time?.split('T')[0] ?? '';
        const effectiveWeights = intervalWeights || { '1h': 1, '2h': 2, '3h': 4, '4h': 8, '1d': 32 };
        const totalScore = (d: any) => {
            return (d.score_1h || 0) * effectiveWeights['1h'] + (d.score_2h || 0) * effectiveWeights['2h']
                + (d.score_3h || 0) * effectiveWeights['3h'] + (d.score_4h || 0) * effectiveWeights['4h']
                + (d.score_1d || 0) * effectiveWeights['1d'];
        };
        const computeStats = (data: any[]) => {
            if (!data || data.length === 0) return { today: 0, avg: 0, median: 0, percentile: 0 };
            const todayEntry = data.find(d => d.date === latestDate);
            const today = todayEntry ? totalScore(todayEntry) : 0;
            const scores = data.map(d => totalScore(d));
            const avg = scores.reduce((a, b) => a + b, 0) / scores.length;
            const sorted = [...scores].sort((a, b) => a - b);
            const median = sorted.length % 2 === 0
                ? (sorted[sorted.length / 2 - 1] + sorted[sorted.length / 2]) / 2
                : sorted[Math.floor(sorted.length / 2)];
            const percentile = computePercentile(today, scores);
            return { today, avg: Math.round(avg * 10) / 10, median, percentile };
        };
        return {
            cd: computeStats(cdBreakthroughScoreBreadth),
            mc: computeStats(mcBreakthroughScoreBreadth)
        };
    }, [cdBreakthroughScoreBreadth, mcBreakthroughScoreBreadth, spxData, intervalWeights]);

    // Volume: today vs 1yr average + percentile
    const volumeStats = useMemo(() => {
        if (!spxData || spxData.length === 0) return null;
        const todayVol = spxData[spxData.length - 1]?.volume ?? 0;
        const volumes = spxData.map((d: any) => d.volume).filter((v: number) => v > 0);
        if (volumes.length === 0) return null;
        const avg = volumes.reduce((a: number, b: number) => a + b, 0) / volumes.length;
        const ratio = avg > 0 ? ((todayVol - avg) / avg) * 100 : 0;
        const percentile = computePercentile(todayVol, volumes);
        return { today: todayVol, avg, ratio, percentile };
    }, [spxData]);

    // Format volume
    const formatVol = (v: number) => {
        if (v >= 1e9) return `${(v / 1e9).toFixed(1)}B`;
        if (v >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
        if (v >= 1e3) return `${(v / 1e3).toFixed(0)}K`;
        return v.toFixed(0);
    };

    return (
        <div
            className="relative cursor-pointer w-full"
            style={{
                perspective: '1200px',
                height: flipped ? '898px' : 'auto',
                minHeight: flipped ? '898px' : '380px', // Adjusted front face to hug content tightly
                transition: 'height 0.4s ease, min-height 0.4s ease'
            }}
            onClick={() => setFlipped(!flipped)}
        >
            <div
                className="w-full h-full transition-transform duration-500 ease-in-out relative"
                style={{
                    transformStyle: 'preserve-3d',
                    transform: flipped ? 'rotateY(180deg)' : 'rotateY(0deg)'
                }}
            >
                {/* === FRONT FACE === */}
                <div
                    className={cn(
                        "border rounded-lg bg-card p-4 shadow-sm hover:shadow-md transition-shadow overflow-hidden",
                        "w-full h-full", // Fill container
                        flipped ? "absolute inset-0" : "relative"
                    )}
                    style={{
                        backfaceVisibility: 'hidden',
                        position: flipped ? 'absolute' : 'relative',
                        top: 0, left: 0 // meaningful only if absolute
                    }}
                >
                    {/* Header */}
                    <div className="flex items-center justify-between mb-3">
                        <h3 className="text-lg font-bold">{title}</h3>
                        {priceInfo && (
                            <div className="text-right">
                                <span className="text-lg font-semibold">{priceInfo.close.toLocaleString(undefined, { maximumFractionDigits: 2 })}</span>
                                <span className={cn(
                                    "ml-2 text-sm font-medium",
                                    priceInfo.change >= 0 ? "text-green-500" : "text-red-500"
                                )}>
                                    {priceInfo.change >= 0 ? '+' : ''}{priceInfo.change.toFixed(2)}%
                                </span>
                            </div>
                        )}
                    </div>

                    {/* CD/MC Signals last 7 days */}
                    <div className="mb-2">
                        <div className="text-xs text-muted-foreground mb-1 font-medium">CD/MC Signals (7d)</div>
                        <div className="flex gap-1.5 items-center flex-wrap">
                            {recentSignals.map((s, i) => (
                                <div key={i} className="flex flex-col items-center gap-0.5">
                                    <span className="text-[10px] text-muted-foreground">{s.date.slice(5)}</span>
                                    <div className="flex gap-0.5">
                                        <div className={cn(
                                            "w-3 h-3 rounded-full border",
                                            s.cd ? "bg-green-500 border-green-600" : "bg-muted border-border"
                                        )} title={`CD ${s.cd ? 'Buy' : '-'}`} />
                                        <div className={cn(
                                            "w-3 h-3 rounded-full border",
                                            s.mc ? "bg-red-500 border-red-600" : "bg-muted border-border"
                                        )} title={`MC ${s.mc ? 'Sell' : '-'}`} />
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>

                    {/* 1234 Signals last 7 days */}
                    <div className="mb-2">
                        <div className="text-xs text-muted-foreground mb-1 font-medium">1234 Signals (7d)</div>
                        <div className="flex gap-2 text-sm flex-wrap">
                            <span className={cn(
                                "px-2 py-0.5 rounded text-xs font-medium whitespace-nowrap",
                                recent1234.cd.length > 0 ? "bg-green-500/15 text-green-600" : "bg-muted text-muted-foreground"
                            )}>
                                Buy: {recent1234.cd.length > 0 ? recent1234.cd.map(d => format(parseISO(d), 'MM-dd')).join(', ') : 'None'}
                            </span>
                            <span className={cn(
                                "px-2 py-0.5 rounded text-xs font-medium whitespace-nowrap",
                                recent1234.mc.length > 0 ? "bg-red-500/15 text-red-600" : "bg-muted text-muted-foreground"
                            )}>
                                Sell: {recent1234.mc.length > 0 ? recent1234.mc.map(d => format(parseISO(d), 'MM-dd')).join(', ') : 'None'}
                            </span>
                        </div>
                    </div>

                    {/* Panel 1: CD/MC (Signal Breadth) */}
                    <div className="space-y-1 pb-1">
                        <div className="text-xs text-muted-foreground font-medium">CD/MC</div>
                        <PercentileMeter
                            percentile={signalStats.cd.percentile}
                            label="Buy"
                            value={`${signalStats.cd.today} / ${signalStats.cd.avg}`}
                            color="green"
                        />
                        <PercentileMeter
                            percentile={signalStats.mc.percentile}
                            label="Sell"
                            value={`${signalStats.mc.today} / ${signalStats.mc.avg}`}
                            color="red"
                        />
                    </div>

                    {/* Panel 2: CD/MC Score (Score Breadth) */}
                    <div className="space-y-1 pb-1">
                        <div className="text-xs text-muted-foreground font-medium">CD/MC Score</div>
                        <PercentileMeter
                            percentile={scoreStats.cd.percentile}
                            label="Buy"
                            value={`${scoreStats.cd.today.toFixed(0)} / ${scoreStats.cd.avg.toFixed(0)}`}
                            color="green"
                        />
                        <PercentileMeter
                            percentile={scoreStats.mc.percentile}
                            label="Sell"
                            value={`${scoreStats.mc.today.toFixed(0)} / ${scoreStats.mc.avg.toFixed(0)}`}
                            color="red"
                        />
                    </div>

                    {/* Panel 3: CD/MC Breakthrough (was Buy/Sell) */}
                    <div className="space-y-1 pb-1">
                        <div className="text-xs text-muted-foreground font-medium">CD/MC Breakthrough</div>
                        <PercentileMeter
                            percentile={breadthStats.cd.percentile}
                            label="Buy"
                            value={`${breadthStats.cd.today} / ${breadthStats.cd.avg}`}
                            color="green"
                        />
                        <PercentileMeter
                            percentile={breadthStats.mc.percentile}
                            label="Sell"
                            value={`${breadthStats.mc.today} / ${breadthStats.mc.avg}`}
                            color="red"
                        />
                    </div>

                    {/* Panel 4: CD/MC Breakthrough Score + Volume */}
                    <div className="space-y-1 pb-1">
                        <div className="text-xs text-muted-foreground font-medium">CD/MC Breakthrough Score</div>
                        <PercentileMeter
                            percentile={breakthroughScoreStats.cd.percentile}
                            label="Buy"
                            value={`${breakthroughScoreStats.cd.today.toFixed(0)} / ${breakthroughScoreStats.cd.avg.toFixed(0)}`}
                            color="green"
                        />
                        <PercentileMeter
                            percentile={breakthroughScoreStats.mc.percentile}
                            label="Sell"
                            value={`${breakthroughScoreStats.mc.today.toFixed(0)} / ${breakthroughScoreStats.mc.avg.toFixed(0)}`}
                            color="red"
                        />
                        {volumeStats && (
                            <PercentileMeter
                                percentile={volumeStats.percentile}
                                label="Vol"
                                value={`${formatVol(volumeStats.today)} / ${formatVol(volumeStats.avg)}`}
                                color="blue"
                            />
                        )}
                    </div>


                </div>

                {/* === BACK FACE (Chart) === */}
                <div
                    className={cn(
                        "rounded-lg bg-card overflow-hidden",
                        "absolute inset-0 w-full h-full" // Always absolute to fill container
                    )}
                    style={{
                        backfaceVisibility: 'hidden',
                        transform: 'rotateY(180deg)',
                        opacity: flipped ? 1 : 0 // improve rendering
                    }}
                    onClick={(e) => e.stopPropagation()}
                >
                    <div className="border rounded-lg bg-card overflow-hidden h-full flex flex-col">
                        <div
                            className="p-2 border-b bg-muted/30 flex justify-between items-center cursor-pointer shrink-0"
                            onClick={() => setFlipped(false)}
                        >
                            <span className="text-sm font-medium">{title} — Market Breadth</span>
                            <span className="text-xs text-muted-foreground hover:text-foreground transition-colors">
                                ← Back to summary
                            </span>
                        </div>
                        <div className="p-1 flex-1 min-h-0">
                            {flipped && (
                                <MarketBreadthChart
                                    title={title}
                                    spxData={selectedTicker && stockData ? stockData : spxData}
                                    cdBreadth={effectiveCdBreadth}
                                    mcBreadth={effectiveMcBreadth}
                                    cdSignalBreadth={effectiveCdSignalBreadth}
                                    mcSignalBreadth={effectiveMcSignalBreadth}
                                    cdScoreBreadth={effectiveCdScoreBreadth}
                                    mcScoreBreadth={effectiveMcScoreBreadth}
                                    cdBreakthroughScoreBreadth={effectiveCdBtScoreBreadth}
                                    mcBreakthroughScoreBreadth={effectiveMcBtScoreBreadth}
                                    intervalWeights={intervalWeights}
                                    minDate={minDate}
                                    signals1234={selectedTicker ? undefined : signals1234}
                                    tickers={tickers}
                                    selectedTicker={selectedTicker}
                                    onTickerChange={setSelectedTicker}
                                    indexTitle={title}
                                />
                            )}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
};
