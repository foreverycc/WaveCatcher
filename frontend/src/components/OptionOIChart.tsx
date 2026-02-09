import React, { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
    ComposedChart,
    Bar,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    Legend,
    ResponsiveContainer,
    ReferenceLine,
    Line,
    ReferenceArea
} from 'recharts';
import { analysisApi } from '../services/api';
import { cn } from '../utils/cn';
import { formatNumberShort } from '../utils/chartUtils';

interface OptionOIChartProps {
    ticker?: string;
    data?: any[]; // Manual data mode (e.g. from CSV)
    maxPain?: number; // Manual max pain
    currentPrice?: number; // Manual current price
    priceRange?: { min: number; max: number }; // Manual zoom range
    onRangeChange?: (min: number, max: number) => void;
}

export const OptionOIChart: React.FC<OptionOIChartProps> = ({
    ticker,
    data: manualData,
    maxPain: manualMaxPain,
    currentPrice: manualCurrentPrice,
    priceRange,
    onRangeChange
}) => {
    const [selectedTimeframe, setSelectedTimeframe] = useState<'nearest' | 'week' | 'month'>('nearest');
    const [showFullRange, setShowFullRange] = useState(false);

    // Interaction State
    const chartContainerRef = React.useRef<HTMLDivElement>(null);
    // const draggingRef = React.useRef(false); // Removed
    // const startXRef = React.useRef(0); // Removed
    // const rangeSnapshotRef = React.useRef<{ min: number, max: number } | null>(null); // Removed

    // Fetch options data (only if ticker is provided and no manual data)
    const { data: optionsData, isLoading, error } = useQuery({
        queryKey: ['options', ticker],
        queryFn: () => ticker ? analysisApi.getOptions(ticker) : null,
        staleTime: 1000 * 60 * 5, // 5 minutes
        enabled: !!ticker && !manualData
    });

    const activeData = useMemo(() => {
        if (manualData) {
            return {
                data: manualData,
                max_pain: manualMaxPain,
                date: 'Manual Import'
            };
        }
        if (!optionsData || !optionsData[selectedTimeframe]) return null;
        return optionsData[selectedTimeframe];
    }, [optionsData, selectedTimeframe, manualData, manualMaxPain]);

    const globalMinMax = useMemo(() => {
        if (!activeData?.data || activeData.data.length === 0) return { min: 0, max: 0 };
        const strikes = activeData.data.map((d: any) => d.strike);
        return {
            min: Math.min(...strikes),
            max: Math.max(...strikes)
        };
    }, [activeData]);

    const chartData = useMemo(() => {
        if (!activeData?.data) return [];
        let data = activeData.data;
        // Use manual price if available, otherwise fetch result
        const currentPrice = manualCurrentPrice ?? optionsData?.current_price;

        // 1. External Filter (Range Slider or Zoom/Pan State)
        if (priceRange) {
            data = data.filter((d: any) => d.strike >= priceRange.min && d.strike <= priceRange.max);
        }
        // 2. Focused Range Toggle (fallback if no range slider)
        else if (!showFullRange && currentPrice && data.length > 0) {
            const lowerBound = currentPrice * 0.75;
            const upperBound = currentPrice * 1.25;
            data = data.filter((d: any) => d.strike >= lowerBound && d.strike <= upperBound);
        }
        return data;
    }, [activeData, optionsData, showFullRange, priceRange, manualCurrentPrice]);

    const expiryDate = activeData?.date || '';
    const maxPain = manualMaxPain ?? activeData?.max_pain;
    const currentPrice = manualCurrentPrice ?? optionsData?.current_price;

    // --- Interaction Handlers ---

    const effectiveRange = useMemo(() => {
        if (priceRange) return priceRange;
        if (chartData.length > 0) {
            // Assuming sorted data by strike
            const min = chartData[0].strike;
            const max = chartData[chartData.length - 1].strike;
            return { min, max };
        }
        return { min: 0, max: 0 };
    }, [priceRange, chartData]);

    const [selection, setSelection] = useState<{ start: number, end: number } | null>(null);
    const isSelectingRef = React.useRef(false);
    const startXRef = React.useRef(0);

    const handleMouseDown = (e: React.MouseEvent<HTMLDivElement>) => {
        if (!onRangeChange) return;
        isSelectingRef.current = true;
        // Calculate initial strike from x coordinate? 
        // We can't easily get the exact strike on MouseDown without calculating it from pixels.
        // Let's store the PIXELS and convert later, or convert on the fly for the preview.

        // Better: We need visual feedback. Recharts ReferenceArea takes X axis values (Strikes).
        // So we MUST convert pixels to strikes immediately.

        const chartArea = getChartArea(e.currentTarget);
        if (!chartArea) return;

        const strike = pixelToStrike(e.nativeEvent.offsetX, chartArea, effectiveRange);
        if (strike !== null) {
            setSelection({ start: strike, end: strike });
            startXRef.current = e.nativeEvent.offsetX;
            document.body.style.cursor = 'crosshair';
        }
    };

    const handleMouseMove = React.useCallback((e: MouseEvent) => {
        if (!isSelectingRef.current || !chartContainerRef.current) return;

        const chartArea = getChartArea(chartContainerRef.current);
        if (!chartArea) return;

        const strike = pixelToStrike(e.offsetX, chartArea, effectiveRange);

        if (strike !== null) {
            setSelection(prev => prev ? { ...prev, end: strike } : null);
        }
    }, [effectiveRange]);

    const handleMouseUp = React.useCallback(() => {
        if (!isSelectingRef.current) return;
        isSelectingRef.current = false;
        document.body.style.cursor = '';

        setSelection(prev => {
            if (prev && Math.abs(prev.end - prev.start) > 5) { // Minimum threshold
                const min = Math.min(prev.start, prev.end);
                const max = Math.max(prev.start, prev.end);

                // Trigger change
                if (onRangeChange) onRangeChange(min, max);
            }
            return null; // Clear selection
        });
    }, [onRangeChange]);

    // Helpers
    const getChartArea = (container: HTMLElement) => {
        // Hardcoded margins matching ComposedChart
        const margins = { left: 20, right: 25 };
        const width = container.clientWidth;
        const chartWidth = width - margins.left - margins.right;
        if (chartWidth <= 0) return null;
        return { width: chartWidth, left: margins.left };
    };

    const pixelToStrike = (x: number, chartArea: { width: number, left: number }, range: { min: number, max: number }) => {
        const relativeX = x - chartArea.left;
        const fraction = relativeX / chartArea.width;
        // Clamp fraction? Allow slightly outside?
        // Let's clamp to 0-1 to avoid selecting outside axis
        const clampedFraction = Math.max(0, Math.min(1, fraction));

        return range.min + clampedFraction * (range.max - range.min);
    };

    const handleTouchStart = (e: React.TouchEvent<HTMLDivElement>) => {
        if (!onRangeChange) return;
        isSelectingRef.current = true;
        const chartArea = getChartArea(e.currentTarget);
        if (!chartArea) return;

        const touchX = e.touches[0].clientX;
        // Adjust for element position since clientX is global
        const rect = e.currentTarget.getBoundingClientRect();
        const localX = touchX - rect.left;

        const strike = pixelToStrike(localX, chartArea, effectiveRange);
        if (strike !== null) {
            setSelection({ start: strike, end: strike });
            startXRef.current = localX;
        }
    };

    const handleTouchMove = (e: React.TouchEvent<HTMLDivElement>) => {
        if (!isSelectingRef.current) return;

        // Prevent scrolling while dragging logic could go here if needed
        // e.preventDefault(); 

        const chartArea = getChartArea(e.currentTarget);
        if (!chartArea) return;

        const touchX = e.touches[0].clientX;
        const rect = e.currentTarget.getBoundingClientRect();
        const localX = touchX - rect.left;

        const strike = pixelToStrike(localX, chartArea, effectiveRange);
        if (strike !== null) {
            setSelection(prev => prev ? { ...prev, end: strike } : null);
        }
    };

    const handleTouchEnd = () => {
        if (!isSelectingRef.current) return;
        isSelectingRef.current = false;

        setSelection(prev => {
            if (prev && Math.abs(prev.end - prev.start) > 5) {
                const min = Math.min(prev.start, prev.end);
                const max = Math.max(prev.start, prev.end);
                if (onRangeChange) onRangeChange(min, max);
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

    // Note: For touch, we generally attach directly to the element rather than window 
    // because standard behavior handles touch capture differently.

    // Wheel Zoom (Keep this?) - User said "Drag and select", didn't explicitly ask to remove Zoom. 
    // Keeping scroll zoom is usually nice.
    const handleWheel = (e: React.WheelEvent) => {
        if (!onRangeChange) return;
        const currentRange = effectiveRange.max - effectiveRange.min;
        if (currentRange <= 0) return;
        const zoomFactor = 0.1;
        const delta = e.deltaY > 0 ? 1 : -1;
        const change = currentRange * zoomFactor * delta;
        let newMin = effectiveRange.min - (change / 2);
        let newMax = effectiveRange.max + (change / 2);
        if (newMin < globalMinMax.min) newMin = globalMinMax.min;
        if (newMax > globalMinMax.max) newMax = globalMinMax.max;
        if (newMax - newMin < 5) return;
        onRangeChange(newMin, newMax);
    };


    if (isLoading && !manualData) {
        return <div className="h-[350px] flex items-center justify-center text-muted-foreground">Loading option data...</div>;
    }

    if (error) {
        return (
            <div className="h-[350px] flex items-center justify-center text-red-500">
                Failed to load option data
            </div>
        );
    }

    if (!activeData || chartData.length === 0) {
        return (
            <div className="h-[350px] flex items-center justify-center text-muted-foreground">
                No option data available for this timeframe
            </div>
        );
    }

    return (
        <div className="flex flex-col h-full space-y-4">
            <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-2">
                <div>
                    <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
                        Open Interest (Exp: {expiryDate})
                        {maxPain !== undefined && maxPain !== null && (
                            <span className="text-xs font-normal text-muted-foreground bg-muted/30 px-2 py-0.5 rounded ml-2">
                                Max Pain: {maxPain}
                            </span>
                        )}
                    </h3>
                </div>

                <div className="flex items-center gap-2">
                    <button
                        onClick={() => {
                            // Reset logic - Show Global Range
                            if (onRangeChange) onRangeChange(globalMinMax.min, globalMinMax.max);
                            setShowFullRange(true); // Ensure flag reflects "all"
                        }}
                        className="px-2 py-1 text-xs font-medium rounded-md border border-border text-muted-foreground hover:bg-muted"
                        title="Reset Zoom"
                    >
                        Reset Zoom
                    </button>

                    <div className="flex bg-muted/20 rounded-lg p-1">
                        {(['nearest', 'week', 'month'] as const).map((tf) => (
                            <button
                                key={tf}
                                onClick={() => setSelectedTimeframe(tf)}
                                className={cn(
                                    "px-3 py-1 text-xs font-medium rounded-md transition-all",
                                    selectedTimeframe === tf
                                        ? "bg-background shadow-sm text-foreground"
                                        : "text-muted-foreground hover:text-foreground"
                                )}
                            >
                                {tf.charAt(0).toUpperCase() + tf.slice(1)}
                            </button>
                        ))}
                    </div>
                </div>
            </div>

            <div
                ref={chartContainerRef}
                className="flex-1 min-h-[300px] select-none touch-none" // Add touch-none to prevent scrolling
                onWheel={handleWheel}
                onMouseDown={handleMouseDown}
                onTouchStart={handleTouchStart}
                onTouchMove={handleTouchMove}
                onTouchEnd={handleTouchEnd}
            >
                <ResponsiveContainer width="100%" height="100%">
                    <ComposedChart
                        data={chartData}
                        margin={{ top: 20, right: 25, left: 20, bottom: 30 }}
                        barGap={0}
                    >
                        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="hsl(var(--border))" />
                        <XAxis
                            dataKey="strike"
                            tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 11 }}
                            tickLine={true}
                            axisLine={true}
                            type="number"
                            domain={['dataMin', 'dataMax']}
                            allowDataOverflow={true} // Allow fixed domain from state
                        />
                        <YAxis
                            yAxisId="left"
                            tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 11 }}
                            tickLine={true}
                            axisLine={true}
                            tickFormatter={(value) => formatNumberShort(value)}
                        />
                        <YAxis
                            yAxisId="right"
                            orientation="right"
                            tick={{ fill: '#3b82f6', fontSize: 11 }}
                            tickLine={{ stroke: '#3b82f6' }}
                            axisLine={{ stroke: '#3b82f6' }}
                            tickFormatter={(value) => formatNumberShort(value)}
                            label={{ value: 'Option Value ($)', angle: 90, position: 'insideRight', style: { textAnchor: 'middle' }, fill: '#3b82f6', fontSize: 10 }}
                        />
                        <Tooltip
                            contentStyle={{
                                backgroundColor: 'hsl(var(--popover))',
                                borderColor: 'hsl(var(--border))',
                                borderRadius: 'var(--radius)',
                                fontSize: '12px'
                            }}
                            cursor={{ fill: 'hsl(var(--muted)/0.2)' }}
                            formatter={(value: number, name: string) => [
                                formatNumberShort(value),
                                name.charAt(0).toUpperCase() + name.slice(1)
                            ]}
                        />
                        <Legend wrapperStyle={{ fontSize: '11px', paddingTop: '10px' }} />

                        {/* Calls */}
                        <Bar
                            yAxisId="left"
                            dataKey="calls"
                            name="Calls"
                            fill="#22c55e"
                            opacity={0.8}
                            radius={[2, 2, 0, 0]}
                        />

                        {/* Puts */}
                        <Bar
                            yAxisId="left"
                            dataKey="puts"
                            name="Puts"
                            fill="#ef4444"
                            opacity={0.8}
                            radius={[2, 2, 0, 0]}
                        />

                        {/* Pain Line (Blue) */}
                        <Line
                            yAxisId="right"
                            type="monotone"
                            dataKey="pain"
                            name="Option Value"
                            stroke="#3b82f6"
                            strokeWidth={2}
                            strokeDasharray="3 3"
                            dot={false}
                        />

                        {/* Selection Overlay */}
                        {selection && (
                            <ReferenceArea
                                yAxisId="left"
                                x1={Math.min(selection.start, selection.end)}
                                x2={Math.max(selection.start, selection.end)}
                                strokeOpacity={0}
                                fill="hsl(var(--primary))"
                                fillOpacity={0.1}
                            />
                        )}

                        {/* Max Pain Highlight */}
                        {maxPain && (
                            <ReferenceLine
                                yAxisId="left"
                                x={maxPain}
                                stroke="#f59e0b"
                                strokeWidth={1}
                                strokeDasharray="3 3"
                                label={{
                                    value: `Max Pain: ${maxPain}`,
                                    position: 'insideTopRight',
                                    fill: '#f59e0b',
                                    fontSize: 10,
                                    // fontWeight: 'bold',
                                    dy: 10
                                }}
                            />
                        )}

                        {/* Reference Line for Current Price - Snapped to closest strike */}
                        {currentPrice && (() => {
                            if (chartData.length === 0) return null;
                            // Find closest strike
                            const closest = chartData.reduce((prev: any, curr: any) => {
                                return (Math.abs(curr.strike - currentPrice) < Math.abs(prev.strike - currentPrice) ? curr : prev);
                            });

                            return (
                                <ReferenceLine
                                    yAxisId="left"
                                    x={closest.strike}
                                    stroke="hsl(var(--foreground))"
                                    strokeDasharray="3 3"
                                    opacity={0.5}
                                    label={{
                                        value: `Price: ${currentPrice.toFixed(2)}`,
                                        position: 'insideTopRight',
                                        fill: 'hsl(var(--foreground))',
                                        fontSize: 10
                                    }}
                                />
                            );
                        })()}

                        {/* Max Pain Reference (already covered by Pain Line minimum, but keeping for specific label if needed) */}
                        {/* We could add it, but the Curve shows it. Let's keep it simple. */}
                    </ComposedChart>
                </ResponsiveContainer>
            </div>
        </div>
    );
};
