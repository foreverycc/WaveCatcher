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
    minDate?: Date;
    signals1234?: { cd_dates: string[], mc_dates: string[] };
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

// Score weights per interval: base(5) + interval weight(1/2/3/4/8)
const SCORE_WEIGHTS: Record<string, number> = {
    '1h': 1,  // 5+1
    '2h': 2,  // 5+2
    '3h': 3,  // 5+3
    '4h': 4,  // 5+4
    '1d': 8, // 5+8
};

export const MarketBreadthChart: React.FC<MarketBreadthChartProps> = ({
    title,
    spxData,
    cdBreadth = [],
    mcBreadth = [],
    cdSignalBreadth = [],
    mcSignalBreadth = [],
    minDate,
    signals1234
}) => {
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

            // Check if this date is in the external 1234 signals (from analysis results)
            const is1234CD = signals1234?.cd_dates?.includes(dateStr) ?? false;
            const is1234MC = signals1234?.mc_dates?.includes(dateStr) ?? false;

            // Debug logging (first 3 items only to avoid spam)
            if (is1234CD || is1234MC) {
                console.log(`[MarketBreadthChart] 1234 signal matched: date=${dateStr}, CD=${is1234CD}, MC=${is1234MC}`);
            }

            d.cd_1234_signal = is1234CD;
            d.mc_1234_signal = is1234MC;

            // Signal Markers
            d.buySignal = p.cd_signal ? p.low * 0.995 : null; // Slightly below low
            d.sellSignal = p.mc_signal ? p.high * 1.005 : null; // Slightly above high

            // 1234 Markers (from analysis results)
            d.buySignal1234 = is1234CD ? p.low * 0.98 : null;
            d.sellSignal1234 = is1234MC ? p.high * 1.02 : null;
        });

        // Process CD Breadth
        cdBreadth.forEach(b => {
            const dateStr = b.date;
            if (!dataMap.has(dateStr)) dataMap.set(dateStr, { date: dateStr });
            dataMap.get(dateStr).cdCount = b.count;
        });

        // Process MC Breadth
        mcBreadth.forEach(b => {
            const dateStr = b.date;
            if (!dataMap.has(dateStr)) dataMap.set(dateStr, { date: dateStr });
            dataMap.get(dateStr).mcCount = b.count;
        });

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
            // CD Score = weighted sum
            d.cdScore = d.cd_1h * SCORE_WEIGHTS['1h'] + d.cd_2h * SCORE_WEIGHTS['2h']
                + d.cd_3h * SCORE_WEIGHTS['3h'] + d.cd_4h * SCORE_WEIGHTS['4h']
                + d.cd_1d * SCORE_WEIGHTS['1d'];
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
            // MC Score = weighted sum
            d.mcScore = d.mc_1h * SCORE_WEIGHTS['1h'] + d.mc_2h * SCORE_WEIGHTS['2h']
                + d.mc_3h * SCORE_WEIGHTS['3h'] + d.mc_4h * SCORE_WEIGHTS['4h']
                + d.mc_1d * SCORE_WEIGHTS['1d'];
        });

        // Convert to array and sort
        let result = Array.from(dataMap.values())
            .sort((a, b) => a.date.localeCompare(b.date));

        if (minDate) {
            const minStr = format(minDate, 'yyyy-MM-dd');
            result = result.filter(d => d.date >= minStr);
        }

        // Filter to generally available days (mostly SPX days) for cleaner chart
        result = result.filter(d => d.close !== undefined);

        return result;
    }, [spxData, cdBreadth, mcBreadth, cdSignalBreadth, mcSignalBreadth, minDate, signals1234]);

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

    const spxPadding = (validMax - validMin) * 0.5; // 50% padding for signals visibility
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
        <div className="flex flex-col h-[1100px] border rounded-lg bg-card p-4">
            <div className="flex justify-between items-center mb-2">
                <h3 className="text-lg font-semibold text-foreground">{title}</h3>
                <button
                    onClick={() => setZoomState(null)}
                    className="px-2 py-1 text-xs font-medium rounded-md border border-border text-muted-foreground hover:bg-muted"
                >
                    Reset Zoom
                </button>
            </div>

            <div
                ref={wrapperRef}
                className="flex-1 flex flex-col min-h-0 select-none pb-2"
                onWheel={handleWheel}
                onMouseDown={handleMouseDown}
            >
                {/* 1. Price History (Candle) */}
                <div className="flex-[2] min-h-0 border-b border-border/50 relative">
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
                            <Tooltip content={<></>} />
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
                <div className="flex-[0.5] min-h-0 border-b border-border/50 relative">
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
                            <Tooltip content={<></>} />
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
                <div className="flex-[0.5] min-h-0 border-b border-border/50 relative">
                    <span className="absolute top-3 left-2 text-[10px] font-medium text-[#60a5fa] z-10">CD</span>
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
                            <Tooltip content={<></>} />
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
                <div className="flex-[0.5] min-h-0 border-b border-border/50 relative">
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
                            <Tooltip content={<></>} />
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

                {/* 5. CD Score */}
                <div className="flex-[0.5] min-h-0 border-b border-border/50 relative">
                    <span className="absolute top-3 left-2 text-[10px] font-medium text-[#22c55e] z-10">CD Score</span>
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
                            <Tooltip content={<></>} />
                            <Bar
                                dataKey="cdScore"
                                fill="#22c55e"
                                name="CD Score"
                                isAnimationActive={false}
                            />
                            <ReferenceBlock />
                        </ComposedChart>
                    </ResponsiveContainer>
                </div>

                {/* 6. MC Score */}
                <div className="flex-[0.5] min-h-0 border-b border-border/50 relative">
                    <span className="absolute top-3 left-2 text-[10px] font-medium text-[#ef4444] z-10">MC Score</span>
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
                            <Tooltip content={<></>} />
                            <Bar
                                dataKey="mcScore"
                                fill="#ef4444"
                                name="MC Score"
                                isAnimationActive={false}
                            />
                            <ReferenceBlock />
                        </ComposedChart>
                    </ResponsiveContainer>
                </div>

                {/* 7. CD 1234 Counts (Buy) */}
                <div className="flex-[0.5] min-h-0 border-b border-border/50 relative">
                    <span className="absolute top-3 left-2 text-[10px] font-medium text-[#22c55e] z-10">Buy</span>
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
                            <Tooltip content={<></>} />
                            <Bar dataKey="cdCount" fill="#22c55e" name="Buy Signals" />
                            <ReferenceBlock />
                        </ComposedChart>
                    </ResponsiveContainer>
                </div>

                {/* 8. MC 1234 Counts (Sell) */}
                <div className="flex-[0.6] min-h-0 border-b border-border/50 relative">
                    <span className="absolute top-3 left-2 text-[10px] font-medium text-[#ef4444] z-10">Sell</span>
                    <ResponsiveContainer width="100%" height="100%">
                        <ComposedChart data={visibleData} syncId="breadthSync" margin={{ left: 5, right: 5, top: 5, bottom: 5 }}>
                            <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={1} />
                            {commonXAxis(false)}
                            <YAxis
                                orientation="left"
                                mirror={true}
                                domain={[0, 'auto']}
                                tickFormatter={(val) => val === 0 ? '' : val}
                                width={38}
                                tick={{ fontSize: 10 }}
                                tickCount={3}
                            />
                            <Tooltip labelStyle={{ color: 'black' }} />
                            <Bar dataKey="mcCount" fill="#ef4444" name="Sell Signals" />
                            <ReferenceBlock />
                        </ComposedChart>
                    </ResponsiveContainer>
                </div>
            </div>
        </div>
    );
};
