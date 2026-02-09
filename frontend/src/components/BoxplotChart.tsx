import React from 'react';
import {
    ComposedChart,
    Bar,
    Line,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    Legend,
    ResponsiveContainer,
    ReferenceLine,
    ReferenceArea
} from 'recharts';
import { processRowDataForChart, extractCurrentTrajectory, formatNumberShort } from '../utils/chartUtils';
import { cn } from '../utils/cn';

const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
        const data = payload[0].payload;
        // data contains: period, min, max, q1, q3, median, avgVolume, currentReturn, currentVolume

        return (
            <div className="bg-card border border-border p-2 rounded shadow text-xs z-50 min-w-[150px]">
                <p className="font-semibold mb-1">Period: {label}</p>
                <div className="grid grid-cols-2 gap-x-2 gap-y-0.5">
                    {/* Returns Section */}
                    <span className="text-muted-foreground">Current:</span>
                    <span className={cn("text-right font-medium", data.currentReturn >= 0 ? "text-green-500" : "text-red-500")}>
                        {data.currentReturn !== null ? `${data.currentReturn.toFixed(2)}%` : '-'}
                    </span>

                    <span className="text-muted-foreground">Median:</span>
                    <span className="text-foreground text-right">{data.median?.toFixed(2)}%</span>

                    <span className="text-muted-foreground">Q1 / Q3:</span>
                    <span className="text-foreground text-right">{data.q1?.toFixed(2)}% / {data.q3?.toFixed(2)}%</span>

                    <span className="text-muted-foreground">Min / Max:</span>
                    <span className="text-foreground text-right">{data.min?.toFixed(2)}% / {data.max?.toFixed(2)}%</span>

                    <div className="col-span-2 h-px bg-border my-1" />

                    {/* Volume Section */}
                    <span className="text-muted-foreground">Cur Vol:</span>
                    <span className="text-foreground text-right">{data.currentVolume ? formatNumberShort(data.currentVolume) : '-'}</span>

                    <span className="text-muted-foreground">Avg Vol:</span>
                    <span className="text-foreground text-right">{formatNumberShort(data.avgVolume)}</span>
                </div>
            </div>
        );
    }
    return null;
};

interface BoxplotChartProps {
    selectedRow: any | null;
    title?: string;
    subtitle?: string;
}

export const BoxplotChart: React.FC<BoxplotChartProps> = ({ selectedRow, title, subtitle }) => {
    console.log('BoxplotChart received selectedRow:', selectedRow);

    if (!selectedRow) {
        return <div className="flex items-center justify-center h-full text-muted-foreground">No data available</div>;
    }

    // Process historical data for boxplot
    const boxplotData = processRowDataForChart(selectedRow);
    console.log('BoxplotChart boxplotData:', boxplotData);

    if (boxplotData.length === 0) {
        console.log('BoxplotChart: No boxplot data - this file type does not have detailed historical data');
        return (
            <div className="flex flex-col items-center justify-center h-full text-muted-foreground text-sm p-4 text-center">
                <p className="mb-2">No historical data available for this interval.</p>
                <p className="text-xs">For details, please go to <span className="font-semibold">Detailed Results</span> tab.</p>
            </div>
        );
    }

    // Extract current signal trajectory
    const currentTrajectory = extractCurrentTrajectory(selectedRow);
    const currentPeriod = parseInt(selectedRow.current_period) || 0;

    // Combine data for chart
    const chartData = boxplotData.map(d => ({
        ...d,
        iqrBase: d.q1 || 0,
        iqrRange: (d.q3 || 0) - (d.q1 || 0),
        currentReturn: (d.period <= currentPeriod && currentTrajectory.returns[d.period] !== undefined)
            ? currentTrajectory.returns[d.period]
            : null,
        currentVolume: (d.period <= currentPeriod && currentTrajectory.volumes[d.period] !== undefined)
            ? currentTrajectory.volumes[d.period]
            : null
    }));

    // Create data for volume chart (separate)
    const volumeData = chartData.map(d => ({
        period: d.period,
        volume: d.avgVolume,
        currentVolume: d.currentVolume
    }));

    // --- Zoom State ---
    const [zoomDomain, setZoomDomain] = React.useState<{ min: number, max: number } | null>(null);
    const [selection, setSelection] = React.useState<{ start: number, end: number } | null>(null);
    const isSelectingRef = React.useRef(false);
    const startXRef = React.useRef(0);
    const chartContainerRef = React.useRef<HTMLDivElement>(null);

    // Helpers
    const getChartArea = (container: HTMLElement) => {
        const margins = { left: 20, right: 55 };
        const width = container.clientWidth;
        const chartWidth = width - margins.left - margins.right;
        if (chartWidth <= 0) return null;
        return { width: chartWidth, left: margins.left };
    };

    const pixelToValue = (x: number, chartArea: { width: number, left: number }, currentDomain: { min: number, max: number }) => {
        const relativeX = x - chartArea.left;
        const fraction = relativeX / chartArea.width;
        const clampedFraction = Math.max(0, Math.min(1, fraction));
        const range = currentDomain.max - currentDomain.min;
        return currentDomain.min + (clampedFraction * range);
    };

    const globalDomain = { min: 0, max: 100 }; // Assuming period is 0-100 always
    const currentDomain = zoomDomain || globalDomain;

    const handleMouseDown = (e: React.MouseEvent<HTMLDivElement>) => {
        isSelectingRef.current = true;
        const chartArea = getChartArea(e.currentTarget);
        if (!chartArea) return;

        const val = pixelToValue(e.nativeEvent.offsetX, chartArea, currentDomain);
        setSelection({ start: val, end: val });
        startXRef.current = e.nativeEvent.offsetX;
        document.body.style.cursor = 'crosshair';
    };

    const handleMouseMove = React.useCallback((e: MouseEvent) => {
        if (!isSelectingRef.current || !chartContainerRef.current) return;
        const chartArea = getChartArea(chartContainerRef.current);
        if (!chartArea) return;

        const val = pixelToValue(e.offsetX, chartArea, currentDomain);
        setSelection(prev => prev ? { ...prev, end: val } : null);
    }, [currentDomain]);

    const handleMouseUp = React.useCallback(() => {
        if (!isSelectingRef.current) return;
        isSelectingRef.current = false;
        document.body.style.cursor = '';

        setSelection(prev => {
            if (prev && Math.abs(prev.end - prev.start) > 2) { // Min 2 periods
                setZoomDomain({
                    min: Math.floor(Math.min(prev.start, prev.end)),
                    max: Math.ceil(Math.max(prev.start, prev.end))
                });
            }
            return null;
        });
    }, []);

    const handleWheel = (e: React.WheelEvent) => {
        const range = currentDomain.max - currentDomain.min;
        if (range <= 0) return;

        const zoomFactor = 0.1;
        const delta = e.deltaY > 0 ? 1 : -1;
        const change = Math.max(2, range * zoomFactor);

        let newMin = currentDomain.min;
        let newMax = currentDomain.max;

        if (delta > 0) { // Zoom Out
            newMin = Math.max(globalDomain.min, currentDomain.min - change / 2);
            newMax = Math.min(globalDomain.max, currentDomain.max + change / 2);
        } else { // Zoom In
            newMin = currentDomain.min + change / 2;
            newMax = currentDomain.max - change / 2;
            if (newMax - newMin < 5) { // Min 5 periods
                return;
            }
        }

        setZoomDomain({ min: newMin, max: newMax });
    };

    const handleTouchStart = (e: React.TouchEvent<HTMLDivElement>) => {
        isSelectingRef.current = true;
        const chartArea = getChartArea(e.currentTarget);
        if (!chartArea) return;

        const touchX = e.touches[0].clientX;
        const rect = e.currentTarget.getBoundingClientRect();
        const localX = touchX - rect.left;

        const val = pixelToValue(localX, chartArea, currentDomain);
        setSelection({ start: val, end: val });
        startXRef.current = localX;
    };

    const handleTouchMove = (e: React.TouchEvent<HTMLDivElement>) => {
        if (!isSelectingRef.current || !chartContainerRef.current) return;
        const chartArea = getChartArea(chartContainerRef.current);
        if (!chartArea) return;

        const touchX = e.touches[0].clientX;
        const rect = e.currentTarget.getBoundingClientRect();
        const localX = touchX - rect.left;

        const val = pixelToValue(localX, chartArea, currentDomain);
        setSelection(prev => prev ? { ...prev, end: val } : null);
    };

    const handleTouchEnd = () => {
        if (!isSelectingRef.current) return;
        isSelectingRef.current = false;

        setSelection(prev => {
            if (prev && Math.abs(prev.end - prev.start) > 2) {
                setZoomDomain({
                    min: Math.floor(Math.min(prev.start, prev.end)),
                    max: Math.ceil(Math.max(prev.start, prev.end))
                });
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


    return (
        <div className="w-full h-full flex flex-col">
            <div className="flex justify-between items-center mb-2">
                <div>
                    {title && <h3 className="text-sm font-semibold">{title}</h3>}
                    {subtitle && <p className="text-xs text-muted-foreground mt-1">{subtitle}</p>}
                </div>
                <button
                    onClick={() => setZoomDomain(null)}
                    className="px-2 py-1 text-xs font-medium rounded-md border border-border text-muted-foreground hover:bg-muted"
                >
                    Reset Zoom
                </button>
            </div>

            {/* Returns Chart - Top */}
            <div
                ref={chartContainerRef}
                className="w-full mb-1 select-none touch-none"
                style={{ height: '200px' }}
                onMouseDown={handleMouseDown}
                onWheel={handleWheel}
                onTouchStart={handleTouchStart}
                onTouchMove={handleTouchMove}
                onTouchEnd={handleTouchEnd}
            >
                <ResponsiveContainer width="100%" height={200}>
                    <ComposedChart
                        data={chartData}
                        syncId="returnDistribution"
                        margin={{ top: 5, right: 55, left: 20, bottom: 5 }}
                    >
                        <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                        <XAxis
                            dataKey="period"
                            stroke="hsl(var(--muted-foreground))"
                            tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 11 }}
                            hide
                            type="number"
                            domain={[currentDomain.min, currentDomain.max]}
                            allowDataOverflow={true}
                        />
                        <YAxis
                            stroke="hsl(var(--muted-foreground))"
                            tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 11 }}
                            label={{ value: 'Return (%)', angle: -90, position: 'insideLeft', style: { textAnchor: 'middle' }, fill: 'hsl(var(--muted-foreground))', fontSize: 11 }}
                        />
                        <Tooltip
                            content={<CustomTooltip />}
                        />
                        <Legend wrapperStyle={{ fontSize: '11px' }} align="center" />
                        <ReferenceLine y={0} stroke="hsl(var(--muted-foreground))" strokeDasharray="3 3" />

                        {/* Min/Max - light gray dashed line */}
                        <Line
                            type="monotone"
                            dataKey="max"
                            stroke="hsl(var(--muted-foreground))"
                            strokeWidth={1}
                            strokeOpacity={0.62}
                            strokeDasharray="4 4"
                            dot={false}
                            name="Max"
                        />
                        <Line
                            type="monotone"
                            dataKey="min"
                            stroke="hsl(var(--muted-foreground))"
                            strokeWidth={1}
                            strokeOpacity={0.62}
                            strokeDasharray="4 4"
                            dot={false}
                            name="Min"
                            legendType="none" // Hide Min legend
                        />

                        {/* Q1-Q3 Interquartile Range - light blue fill using stacked bar */}
                        <Bar
                            dataKey="iqrBase"
                            fill="transparent"
                            stackId="iqr"
                            legendType="none"
                        />
                        <Bar
                            dataKey="iqrRange"
                            fill="hsl(var(--primary))"
                            fillOpacity={0.2}
                            stackId="iqr"
                            name="IQR (Q1/Q3)"
                            legendType="none" // Hide bar legend
                        />

                        {/* Q1 and Q3 lines - blue dashed */}
                        <Line
                            type="monotone"
                            dataKey="q3"
                            stroke="hsl(var(--primary))"
                            strokeWidth={1}
                            strokeDasharray="3 3"
                            dot={false}
                            name="Q3"
                            legendType="none" // Merged into Q1/Q3
                        />
                        <Line
                            type="monotone"
                            dataKey="q1"
                            stroke="hsl(var(--primary))"
                            strokeWidth={1}
                            strokeDasharray="3 3"
                            dot={false}
                            name="Q1"
                        />

                        {/* Median - small blue dots only */}
                        <Line
                            type="monotone"
                            dataKey="median"
                            stroke="hsl(var(--primary))"
                            strokeWidth={1}
                            dot={{ r: 1, fill: 'hsl(var(--primary))' }}
                            name="Median"
                        />

                        {/* Current return - red solid line */}
                        <Line
                            type="monotone"
                            dataKey="currentReturn"
                            stroke="#ef4444"
                            strokeWidth={1}
                            dot={{ r: 1, fill: '#ef4444' }}
                            name="Current"
                        />

                        {selection && (
                            <ReferenceArea
                                x1={Math.min(selection.start, selection.end)}
                                x2={Math.max(selection.start, selection.end)}
                                strokeOpacity={0}
                                fill="hsl(var(--primary))"
                                fillOpacity={0.1}
                            />
                        )}

                    </ComposedChart>
                </ResponsiveContainer>
            </div>

            {/* Volume Chart - Bottom */}
            <div className="w-full" style={{ height: '100px' }}>
                <ResponsiveContainer width="100%" height={100}>
                    <ComposedChart
                        data={volumeData}
                        syncId="returnDistribution"
                        margin={{ top: 0, right: 55, left: 20, bottom: 20 }}
                    >
                        <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                        <XAxis
                            dataKey="period"
                            stroke="hsl(var(--muted-foreground))"
                            tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 11 }}
                            label={{ value: 'Period', position: 'insideBottom', offset: -10, fill: 'hsl(var(--muted-foreground))', fontSize: 11 }}
                            type="number"
                            domain={[currentDomain.min, currentDomain.max]}
                            allowDataOverflow={true}
                        />
                        <YAxis
                            stroke="hsl(var(--muted-foreground))"
                            tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 11 }}
                            label={{ value: 'Vol', angle: -90, position: 'insideLeft', style: { textAnchor: 'middle' }, fill: 'hsl(var(--muted-foreground))', fontSize: 11 }}
                            tickFormatter={(value: any) => formatNumberShort(value, 0)}
                        />
                        <Tooltip content={() => null} />
                        <Bar
                            dataKey="volume"
                            fill="hsl(var(--muted-foreground))"
                            opacity={0.5}
                            name="Avg Volume"
                        />

                        {/* Current volume - red solid line */}
                        <Line
                            type="monotone"
                            dataKey="currentVolume"
                            stroke="#ef4444"
                            strokeWidth={1}
                            dot={{ r: 1, fill: '#ef4444' }}
                            name="Current Volume"
                        />
                    </ComposedChart>
                </ResponsiveContainer>
            </div>
        </div>
    );
};
