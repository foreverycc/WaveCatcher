import React from 'react';
import {
    ComposedChart,
    Line,
    Bar,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    Legend,
    ResponsiveContainer,
    ReferenceLine
} from 'recharts';

interface PriceVolumeChartProps {
    data: Array<{
        date: string;
        open: number | null;
        high: number | null;
        low: number | null;
        close: number | null;
        volume: number;
    }>;
    title?: string;
    signalDates?: string[];
}

export const PriceVolumeChart: React.FC<PriceVolumeChartProps> = ({ data, title, signalDates = [] }) => {
    if (!data || !Array.isArray(data) || data.length === 0) {
        return <div className="flex items-center justify-center h-full text-muted-foreground text-sm">No price data available</div>;
    }

    // Format data for chart - simplify date display
    const chartData = data.map(d => ({
        ...d,
        dateShort: new Date(d.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
    }));

    return (
        <div className="w-full h-full flex flex-col">
            {title && <h3 className="text-sm font-semibold mb-2">{title}</h3>}
            <div className="w-full" style={{ height: '250px' }}>
                <ResponsiveContainer width="100%" height={250}>
                    <ComposedChart
                        data={chartData}
                        margin={{
                            top: 5,
                            right: 30,
                            left: 20,
                            bottom: 20,
                        }}
                    >
                        <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                        <XAxis
                            dataKey="dateShort"
                            stroke="hsl(var(--muted-foreground))"
                            tick={{ fill: 'hsl(var(--muted-foreground))', fontSize: 10 }}
                            interval="preserveStartEnd"
                        />
                        <YAxis
                            yAxisId="price"
                            stroke="hsl(var(--muted-foreground))"
                            tick={{ fill: 'hsl(var(--muted-foreground))' }}
                            label={{ value: 'Price', angle: -90, position: 'insideLeft', fill: 'hsl(var(--muted-foreground))' }}
                        />
                        <YAxis
                            yAxisId="volume"
                            orientation="right"
                            stroke="hsl(var(--muted-foreground))"
                            tick={{ fill: 'hsl(var(--muted-foreground))' }}
                            label={{ value: 'Volume', angle: 90, position: 'insideRight', fill: 'hsl(var(--muted-foreground))' }}
                        />
                        <Tooltip
                            contentStyle={{
                                backgroundColor: 'hsl(var(--card))',
                                borderColor: 'hsl(var(--border))',
                                color: 'hsl(var(--card-foreground))',
                                fontSize: '12px'
                            }}
                            formatter={(value: any, name: string) => {
                                if (name === 'volume') return [Math.round(value).toLocaleString(), 'Volume'];
                                return [typeof value === 'number' ? value.toFixed(2) : value, name];
                            }}
                        />
                        <Legend wrapperStyle={{ fontSize: '12px' }} />

                        {/* Volume bars in background */}
                        <Bar
                            yAxisId="volume"
                            dataKey="volume"
                            fill="hsl(var(--muted))"
                            opacity={0.3}
                            name="Volume"
                        />

                        {/* Price lines - showing close, high, low */}
                        <Line
                            yAxisId="price"
                            type="monotone"
                            dataKey="high"
                            stroke="hsl(var(--muted-foreground))"
                            strokeDasharray="2 2"
                            strokeWidth={1}
                            dot={false}
                            name="High"
                        />
                        <Line
                            yAxisId="price"
                            type="monotone"
                            dataKey="close"
                            stroke="hsl(var(--primary))"
                            strokeWidth={2}
                            dot={false}
                            name="Close"
                        />
                        <Line
                            yAxisId="price"
                            type="monotone"
                            dataKey="low"
                            stroke="hsl(var(--muted-foreground))"
                            strokeDasharray="2 2"
                            strokeWidth={1}
                            dot={false}
                            name="Low"
                        />
                    </ComposedChart>
                </ResponsiveContainer>
            </div>
        </div>
    );
};
