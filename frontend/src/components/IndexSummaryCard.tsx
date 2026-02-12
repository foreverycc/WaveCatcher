import React, { useMemo, useState } from 'react';
import { subDays, parseISO, isAfter, format } from 'date-fns';
import { MarketBreadthChart } from './MarketBreadthChart';
import { cn } from '../utils/cn';

interface BreadthDataPoint {
    date: string;
    count: number;
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
    minDate: Date;
    signals1234?: { cd_dates: string[], mc_dates: string[] };
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
                <div className={cn("relative h-3 flex-1 rounded-full overflow-hidden", c.track)}>
                    <div
                        className={cn("absolute inset-y-0 left-0 rounded-full transition-all duration-500", c.bg)}
                        style={{ width: `${Math.min(100, Math.max(0, percentile))}%`, opacity: 0.8 }}
                    />
                    {/* Marker line at 50th percentile */}
                    <div className="absolute inset-y-0 left-1/2 w-px bg-foreground/20" />
                </div>
                <span className="text-[10px] text-muted-foreground w-14 text-right shrink-0">
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
    minDate,
    signals1234
}) => {
    const [flipped, setFlipped] = useState(false);

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
            // Find today's count by matching the latest trading date (default to 0 if no entry)
            const todayEntry = data.find(d => d.date === latestDate);
            const today = todayEntry?.count ?? 0;
            const counts = data.map(d => d.count);
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
                height: flipped ? '1150px' : 'auto',
                minHeight: flipped ? '1150px' : '310px', // Allow growth if content needs it when not flipped
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
                        flipped ? "absolute inset-0" : "relative" // If flipped, take out of flow to let back face dictate size? No, actually container determines size.
                        // Better approach:
                        // When NOT flipped: relative, so it pushes container height.
                        // When flipped: absolute, so it doesn't push container height (container is fixed 650px).
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
                    <div className="mb-3">
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
                    <div className="mb-3">
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

                    {/* Breadth + Volume Percentile Meters */}
                    <div className="space-y-1.5 pb-6"> {/* pb-6 to perform space for absolute flip hint */}
                        <div className="text-xs text-muted-foreground font-medium">1234 Breadth & Volume (Percentile)</div>
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
                        {volumeStats && (
                            <PercentileMeter
                                percentile={volumeStats.percentile}
                                label="Vol"
                                value={`${formatVol(volumeStats.today)} / ${formatVol(volumeStats.avg)}`}
                                color="blue"
                            />
                        )}
                    </div>

                    {/* Flip hint */}
                    <div className="absolute bottom-2 right-3 text-[10px] text-muted-foreground/60">
                        Click to view chart →
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
                            <MarketBreadthChart
                                title={title}
                                spxData={spxData}
                                cdBreadth={cdBreadth}
                                mcBreadth={mcBreadth}
                                cdSignalBreadth={cdSignalBreadth}
                                mcSignalBreadth={mcSignalBreadth}
                                minDate={minDate}
                                signals1234={signals1234}
                            />
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
};
