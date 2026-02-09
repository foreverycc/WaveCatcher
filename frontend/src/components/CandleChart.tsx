import React, { useMemo } from 'react';
import {
    ComposedChart,
    Bar,
    Cell,
    Line,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    Legend,
    ResponsiveContainer,
    Scatter,
    ReferenceLine,
    ReferenceArea
} from 'recharts';
import { format } from 'date-fns';
import { formatNumberShort } from '../utils/chartUtils';

import { cn } from '../utils/cn';

interface CandleData {
    time: string;
    open: number;
    high: number;
    low: number;
    close: number;
    volume: number;
    cd_signal?: boolean;
    mc_signal?: boolean;
    ema_13?: number;
    ema_21?: number;
    ema_144?: number;
    ema_169?: number;
}

interface CandleChartProps {
    data: CandleData[];
    ticker: string;
    interval: string;
    onIntervalChange?: (interval: string) => void;
}

const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
        // Find the main payload item (usually the candle or volume, we want all info)
        // payload[0] might be volume or candle depending on order/hover
        // But we can extract from payload[0].payload which is the full data object
        const { open, high, low, close, volume, cd_signal, mc_signal, ema_13, ema_21, ema_144, ema_169 } = payload[0].payload;

        return (
            <div className="bg-background border border-border p-2 rounded shadow text-xs z-50">
                <p className="font-semibold mb-1">{format(new Date(label), 'yyyy-MM-dd HH:mm')}</p>
                <div className="grid grid-cols-2 gap-x-4">
                    <span className="text-muted-foreground">Open:</span> <span className="text-foreground text-right">{open.toFixed(2)}</span>
                    <span className="text-muted-foreground">High:</span> <span className="text-foreground text-right">{high.toFixed(2)}</span>
                    <span className="text-muted-foreground">Low:</span> <span className="text-foreground text-right">{low.toFixed(2)}</span>
                    <span className="text-muted-foreground">Close:</span> <span className="text-foreground text-right">{close.toFixed(2)}</span>
                    <span className="text-muted-foreground">Vol:</span> <span className="text-foreground text-right">{formatNumberShort(volume)}</span>
                </div>

                {/* EMA Section */}
                <div className="mt-2 pt-2 border-t border-border/50 grid grid-cols-2 gap-x-4">
                    <span className="text-muted-foreground">EMA 13:</span> <span className="text-[#0ea5e9] text-right">{ema_13?.toFixed(2) || 'N/A'}</span>
                    <span className="text-muted-foreground">EMA 21:</span> <span className="text-[#3b82f6] text-right">{ema_21?.toFixed(2) || 'N/A'}</span>
                    <span className="text-muted-foreground">EMA 144:</span> <span className="text-[#ef4444] text-right">{ema_144?.toFixed(2) || 'N/A'}</span>
                    <span className="text-muted-foreground">EMA 169:</span> <span className="text-[#f97316] text-right">{ema_169?.toFixed(2) || 'N/A'}</span>
                </div>

                {(cd_signal || mc_signal) && (
                    <div className="mt-2 pt-2 border-t border-border flex flex-col gap-1">
                        {cd_signal && <span className="text-green-500 font-bold flex items-center gap-1">↑ CD BUY</span>}
                        {mc_signal && <span className="text-red-500 font-bold flex items-center gap-1">↓ MC SELL</span>}
                    </div>
                )}
            </div>
        );
    }
    return null;
};

const CandleShape = (props: any) => {
    const { x, y, width, height } = props;
    const { payload } = props;
    const { open: openVal, close: closeVal, high: highVal, low: lowVal } = payload;

    const isUp = closeVal >= openVal;
    const color = isUp ? '#22c55e' : '#ef4444';

    if (highVal === undefined || lowVal === undefined) return null;

    // Y Axis is inverted (0 is top), but values are normal
    // We need to map values to pixels. 
    // Recharts passes us x,y,width,height which is the bar's bounding box.
    // However, for candlestick, we need exact scaling.
    // IMPORTANT: The 'Bar' component with dataKey={[min, max]} will calculate y and height 
    // corresponding to 'min' and 'max' scaled to the axis.
    // So 'y' is the top (max price), 'height' is the span (max - min).
    // We can assume strict linear scaling within this box.

    // BUT we need open/close pixel positions.
    // height = (max - min) * scale
    // scale = height / (max - min)

    const range = highVal - lowVal;
    const scale = range === 0 ? 0 : height / range;

    // y is the pixel position of the TOP (highVal)
    // We calculate offsets from top (highVal)

    const openOffset = (highVal - openVal) * scale;
    const closeOffset = (highVal - closeVal) * scale;

    const bodyTop = Math.min(openOffset, closeOffset);
    const bodyHeight = Math.max(1, Math.abs(openOffset - closeOffset));

    // Center wick
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

export const CandleChart: React.FC<CandleChartProps> = ({ data, ticker, interval, onIntervalChange }) => {

    // --- Zoom State & Logic ---
    const [zoomState, setZoomState] = React.useState<{ start: number, end: number } | null>(null);
    const [selection, setSelection] = React.useState<{ start: number, end: number } | null>(null);
    const isSelectingRef = React.useRef(false);
    const startXRef = React.useRef(0);
    const chartContainerRef = React.useRef<HTMLDivElement>(null);

    // Initial data processing
    const allData = useMemo(() => {
        if (!data) return [];
        return data.filter(d =>
            d.open != null && d.close != null && d.high != null && d.low != null
        ).map(d => ({
            ...d,
            buySignal: d.cd_signal ? d.low * 0.999 : null,
            sellSignal: d.mc_signal ? d.high * 1.001 : null
        }));
    }, [data]);

    // Visible data slice
    const visibleData = useMemo(() => {
        if (allData.length === 0) return [];
        if (!zoomState) return allData;
        return allData.slice(zoomState.start, zoomState.end + 1);
    }, [allData, zoomState]);

    // Helpers to convert pixel to data index
    const getChartArea = (container: HTMLElement) => {
        // Hardcoded margins matching ComposedChart
        const margins = { left: 20, right: 55 };
        const width = container.clientWidth;
        const chartWidth = width - margins.left - margins.right;
        if (chartWidth <= 0) return null;
        return { width: chartWidth, left: margins.left };
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

        // We track local index (0 to validData.length) to display ReferenceArea which matches XAxis
        // XAxis uses 'time' string. ReferenceArea needs that label string.
        setSelection({ start: clickIndex, end: clickIndex });
        startXRef.current = e.nativeEvent.offsetX;
        document.body.style.cursor = 'crosshair';
    };

    const handleMouseMove = React.useCallback((e: MouseEvent) => {
        if (!isSelectingRef.current || !chartContainerRef.current) return;

        const chartArea = getChartArea(chartContainerRef.current);
        if (!chartArea) return;

        const count = visibleData.length;
        const moveIndex = pixelToIndex(e.offsetX, chartArea, count);

        setSelection(prev => prev ? { ...prev, end: moveIndex } : null);
    }, [visibleData.length]);

    const handleMouseUp = React.useCallback(() => {
        if (!isSelectingRef.current) return;
        isSelectingRef.current = false;
        document.body.style.cursor = '';

        setSelection(prev => {
            if (prev && Math.abs(prev.end - prev.start) > 1) { // Min 2 bars
                // Calculate GLOBAL indices
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
        // Scroll to zoom
        if (visibleData.length === 0) return;

        const currentStart = zoomState ? zoomState.start : 0;
        const currentEnd = zoomState ? zoomState.end : allData.length - 1;
        const currentLength = currentEnd - currentStart + 1;

        const zoomFactor = 0.1;
        const delta = e.deltaY > 0 ? 1 : -1; // Down = Zoom Out (Expand), Up = Zoom In (Shrink)
        const change = Math.max(2, Math.floor(currentLength * zoomFactor)); // At least 2 bars change

        let newStart = currentStart;
        let newEnd = currentEnd;

        if (delta > 0) { // Zoom Out
            newStart = Math.max(0, currentStart - Math.ceil(change / 2));
            newEnd = Math.min(allData.length - 1, currentEnd + Math.ceil(change / 2));
        } else { // Zoom In
            newStart = Math.min(newEnd - 5, currentStart + Math.ceil(change / 2)); // Min 5 bars
            newEnd = Math.max(newStart + 5, currentEnd - Math.ceil(change / 2));
        }

        setZoomState({ start: newStart, end: newEnd });
    };

    const handleTouchStart = (e: React.TouchEvent<HTMLDivElement>) => {
        isSelectingRef.current = true;
        const chartArea = getChartArea(e.currentTarget);
        if (!chartArea) return;

        const touchX = e.touches[0].clientX;
        const rect = e.currentTarget.getBoundingClientRect();
        const localX = touchX - rect.left;

        const count = visibleData.length;
        const clickIndex = pixelToIndex(localX, chartArea, count);

        setSelection({ start: clickIndex, end: clickIndex });
        startXRef.current = localX;
    };

    const handleTouchMove = (e: React.TouchEvent<HTMLDivElement>) => {
        if (!isSelectingRef.current || !chartContainerRef.current) return;

        const chartArea = getChartArea(chartContainerRef.current);
        if (!chartArea) return;

        const touchX = e.touches[0].clientX;
        const rect = e.currentTarget.getBoundingClientRect();
        const localX = touchX - rect.left;

        const count = visibleData.length;
        const moveIndex = pixelToIndex(localX, chartArea, count);

        setSelection(prev => prev ? { ...prev, end: moveIndex } : null);
    };

    const handleTouchEnd = () => {
        if (!isSelectingRef.current) return;
        isSelectingRef.current = false;

        setSelection(prev => {
            if (prev && Math.abs(prev.end - prev.start) > 1) { // Min 2 bars
                const currentStart = zoomState ? zoomState.start : 0;

                const localMin = Math.min(prev.start, prev.end);
                const localMax = Math.max(prev.start, prev.end);

                const newStart = currentStart + localMin;
                const newEnd = currentStart + localMax;

                setZoomState({ start: newStart, end: newEnd });
            }
            return null;
        });
    };

    // Attach global handlers
    React.useEffect(() => {
        if (chartContainerRef.current) {
            window.addEventListener('mousemove', handleMouseMove);
            window.addEventListener('mouseup', handleMouseUp);
        }
        return () => {
            window.removeEventListener('mousemove', handleMouseMove);
            window.removeEventListener('mouseup', handleMouseUp);
        };
    }, [handleMouseMove, handleMouseUp]);

    // Define intervals to show
    const intervals = ['5m', '15m', '30m', '1h', '2h', '4h', '1d', '1w'];

    // Date format logic for XAxis
    const axisDateFormat = useMemo(() => {
        if (visibleData.length === 0) return 'MM-dd';
        const start = new Date(visibleData[0].time);
        const end = new Date(visibleData[visibleData.length - 1].time);

        const diffTime = Math.abs(end.getTime() - start.getTime());
        const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));

        // If spans across years
        if (start.getFullYear() !== end.getFullYear()) {
            // For longer durations (e.g. > 3 months), show Year-Month
            if (diffDays > 90) return 'yyyy-MM';
            // For shorter cross-year durations, show full date to distinct days
            return 'yyyy-MM-dd';
        }

        return 'MM-dd';
    }, [visibleData]);

    // Calculate Y-Axis Domain with padding
    const yDomain = useMemo(() => {
        if (visibleData.length === 0) return ['auto', 'auto'];

        // Consider both candle prices and EMA lines for domain calculation
        let min = Infinity;
        let max = -Infinity;

        visibleData.forEach(d => {
            if (d.low < min) min = d.low;
            if (d.high > max) max = d.high;
            // Include EMAs if valid
            if (d.ema_13) { if (d.ema_13 < min) min = d.ema_13; if (d.ema_13 > max) max = d.ema_13; }
            if (d.ema_144) { if (d.ema_144 < min) min = d.ema_144; if (d.ema_144 > max) max = d.ema_144; }
        });

        if (min === Infinity || max === -Infinity) return ['auto', 'auto'];

        const padding = (max - min) * 0.2; // 20% padding
        // If flat line, add minimal padding
        const finalPadding = padding === 0 ? max * 0.05 : padding;

        return [min - finalPadding, max + finalPadding];
    }, [visibleData]);

    if (!allData || allData.length === 0) {
        return <div className="h-full flex items-center justify-center text-muted-foreground bg-muted/10 rounded border border-dashed border-border p-4">No price data available</div>;
    }

    return (
        <div className="w-full h-full flex flex-col">
            <div className="flex justify-between items-center mb-2">
                <div className="flex items-center gap-2">
                    <h3 className="text-sm font-semibold">Price History - {ticker} ({interval})</h3>
                    {onIntervalChange && (
                        <div className="flex bg-muted/20 rounded-lg p-0.5 ml-2">
                            {intervals.map((int) => (
                                <button
                                    key={int}
                                    onClick={() => onIntervalChange(int)}
                                    className={cn(
                                        "px-2 py-0.5 text-[10px] font-medium rounded transition-all",
                                        interval === int
                                            ? "bg-background shadow-sm text-foreground"
                                            : "text-muted-foreground hover:text-foreground"
                                    )}
                                >
                                    {int}
                                </button>
                            ))}
                        </div>
                    )}
                </div>
                <button
                    onClick={() => setZoomState(null)} // Reset
                    className="px-2 py-1 text-xs font-medium rounded-md border border-border text-muted-foreground hover:bg-muted"
                >
                    Reset Zoom
                </button>
            </div>

            {/* Price Chart - Top Section */}
            <div
                ref={chartContainerRef}
                className="flex-1 min-h-0 select-none touch-none"
                onMouseDown={handleMouseDown}
                onWheel={handleWheel}
                onTouchStart={handleTouchStart}
                onTouchMove={handleTouchMove}
                onTouchEnd={handleTouchEnd}
            >
                <ResponsiveContainer width="100%" height="100%">
                    <ComposedChart
                        data={visibleData}
                        syncId="candleGraph"
                        margin={{ top: 10, right: 55, left: 20, bottom: 5 }}
                    >
                        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="hsl(var(--border))" opacity={0.5} />

                        <XAxis
                            dataKey="time"
                            tickFormatter={(tick) => {
                                try {
                                    return format(new Date(tick), axisDateFormat)
                                } catch (e) {
                                    return tick;
                                }
                            }}
                            stroke="hsl(var(--muted-foreground))"
                            tick={{ fontSize: 11 }}
                            minTickGap={30}
                            hide // Hide XAxis on top chart to avoid clutter, user can see specific time in tooltip
                        />

                        <YAxis
                            domain={yDomain}
                            stroke="hsl(var(--muted-foreground))"
                            tick={{ fontSize: 11 }}
                            tickFormatter={(val: number) => formatNumberShort(val)}
                            scale="linear"
                            allowDataOverflow={true} // Allow overflow to respect domain
                            label={{ value: 'Price', angle: -90, position: 'insideLeft', style: { textAnchor: 'middle' }, fill: 'hsl(var(--muted-foreground))', fontSize: 11 }}
                        />

                        <Tooltip content={<CustomTooltip />} />
                        <Legend wrapperStyle={{ fontSize: '11px', paddingTop: '10px' }} align="center" />

                        {/* Candlestick - Using [low, high] with custom shape */}
                        <Bar
                            name="Price"
                            dataKey={(d) => [d.low, d.high]}
                            shape={<CandleShape />}
                            isAnimationActive={false}
                            legendType="none" // Hide generic Candle bar from legend if preferred, or keep
                        />

                        {/* Vegas Channel */}
                        <Line type="monotone" dataKey="ema_13" stroke="#0ea5e9" strokeWidth={1} dot={false} name="EMA 13" />
                        <Line type="monotone" dataKey="ema_21" stroke="#3b82f6" strokeWidth={1} dot={false} name="EMA 21" />
                        <Line type="monotone" dataKey="ema_144" stroke="#ef4444" strokeWidth={1} dot={false} name="EMA 144" />
                        <Line type="monotone" dataKey="ema_169" stroke="#f97316" strokeWidth={1} dot={false} name="EMA 169" />

                        {/* Current Price Line */}
                        <ReferenceLine
                            y={visibleData[visibleData.length - 1]?.close}
                            stroke="hsl(var(--foreground))"
                            strokeDasharray="3 3"
                            label={{
                                value: visibleData[visibleData.length - 1]?.close?.toFixed(2),
                                position: 'right',
                                fill: 'hsl(var(--foreground))',
                                fontSize: 11
                            }}
                        />

                        {/* Buy Signals (CD) */}
                        <Scatter
                            name="CD Buy Signal"
                            dataKey="buySignal"
                            shape={(props: any) => {
                                const { cx, cy } = props;
                                if (!cx || !cy) return <g />;
                                return (
                                    <path
                                        d={`M${cx},${cy} l-4,6 l8,0 z`}
                                        fill="#22c55e"
                                        stroke="#22c55e"
                                        transform={`translate(0, 10)`} // Offset below
                                    />
                                );
                            }}
                            isAnimationActive={false}
                            fill="#22c55e"
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
                                        d={`M${cx},${cy} l-4,-6 l8,0 z`}
                                        fill="#ef4444"
                                        stroke="#ef4444"
                                        transform={`translate(0, -10)`} // Offset above
                                    />
                                );
                            }}
                            isAnimationActive={false}
                            fill="#ef4444"
                        />

                        {selection && visibleData[Math.min(selection.start, selection.end)] && visibleData[Math.max(selection.start, selection.end)] && (
                            <ReferenceArea
                                x1={visibleData[Math.min(selection.start, selection.end)].time}
                                x2={visibleData[Math.max(selection.start, selection.end)].time}
                                strokeOpacity={0}
                                fill="hsl(var(--primary))"
                                fillOpacity={0.1}
                            />
                        )}
                    </ComposedChart>
                </ResponsiveContainer>
            </div>

            {/* Volume Chart - Bottom Section */}
            <div className="h-[100px] mt-2">
                <ResponsiveContainer width="100%" height="100%">
                    <ComposedChart
                        data={visibleData}
                        syncId="candleGraph"
                        margin={{ top: 0, right: 55, left: 20, bottom: 20 }}
                    >
                        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="hsl(var(--border))" opacity={0.5} />

                        <XAxis
                            dataKey="time"
                            tickFormatter={(tick) => {
                                try {
                                    return format(new Date(tick), axisDateFormat)
                                } catch (e) {
                                    return tick;
                                }
                            }}
                            stroke="hsl(var(--muted-foreground))"
                            tick={{ fontSize: 11 }}
                            minTickGap={30}
                            label={{ value: 'Date', position: 'insideBottom', offset: -10, fill: 'hsl(var(--muted-foreground))', fontSize: 11 }}
                        />

                        <YAxis
                            domain={[0, 'auto']}
                            stroke="hsl(var(--muted-foreground))"
                            tick={{ fontSize: 11 }}
                            tickFormatter={(val: number) => formatNumberShort(val)}
                            label={{ value: 'Vol', angle: -90, position: 'insideLeft', style: { textAnchor: 'middle' }, fill: 'hsl(var(--muted-foreground))', fontSize: 11 }}
                        />

                        <Tooltip content={() => null} />

                        <Bar
                            dataKey="volume"
                            opacity={0.6}
                            barSize={30}
                            name="Volume"
                            isAnimationActive={false}
                        >
                            {visibleData.map((entry, index) => (
                                <Cell
                                    key={`cell-${index}`}
                                    fill={entry.close >= entry.open ? '#22c55e' : '#ef4444'}
                                />
                            ))}
                        </Bar>
                    </ComposedChart>
                </ResponsiveContainer>
            </div>
        </div>
    );
};
