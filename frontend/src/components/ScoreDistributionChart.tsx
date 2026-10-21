import React, { useMemo } from 'react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, ReferenceLine } from 'recharts';
import type { ScoreDistribution } from '../services/api';

const INTERVALS = ['1h', '2h', '3h', '4h', '1d'] as const;
const INTERVAL_COLORS: Record<string, string> = {
    '1h': '#60a5fa',
    '2h': '#34d399',
    '3h': '#fbbf24',
    '4h': '#f87171',
    '1d': '#a78bfa',
};

export const BIN_WIDTH_OPTIONS = [1, 2, 5, 10, 20] as const;

/** Bin widths the stored distribution can be merged into (multiples of its own bin width). */
export const availableBinWidths = (dist: ScoreDistribution) =>
    BIN_WIDTH_OPTIONS.filter(w => w >= dist.bin_width && w % dist.bin_width === 0);

const DistributionTooltip = ({ active, payload, binWidth }: any) => {
    if (!active || !payload?.length) return null;
    const d = payload[0].payload;
    return (
        <div className="bg-background border border-border p-2 rounded shadow text-xs z-50">
            <p className="font-semibold mb-1">Score {d.bin}–{d.bin + binWidth}</p>
            <div className="grid grid-cols-2 gap-x-4">
                {INTERVALS.map(k => (
                    <React.Fragment key={k}>
                        <span style={{ color: INTERVAL_COLORS[k] }}>{k}:</span>
                        <span className="text-right">{(d[k] || 0).toLocaleString()}</span>
                    </React.Fragment>
                ))}
                <span className="text-muted-foreground border-t border-border/50 pt-0.5 mt-0.5">Total:</span>
                <span className="text-right border-t border-border/50 pt-0.5 mt-0.5">{d.total.toLocaleString()}</span>
                <span className="text-muted-foreground">Score ≥ {d.bin}:</span>
                <span className="text-right">{d.keptPct.toFixed(0)}%</span>
            </div>
        </div>
    );
};

/** Histogram of the scores of every CD or MC indicator firing, with the threshold marked. */
export const ScoreDistributionChart: React.FC<{
    dist: ScoreDistribution;
    side: 'cd' | 'mc';
    threshold: number;
    binWidth: number;
}> = ({ dist, side, threshold, binWidth }) => {
    const width = binWidth % dist.bin_width === 0 && binWidth >= dist.bin_width ? binWidth : dist.bin_width;
    const { rows, total, kept } = useMemo(() => {
        const perInterval = dist[side] || {};
        // Merge the stored bins into bins of the picked width
        const byBin = new Map<number, any>();
        dist.bins.forEach((edge, i) => {
            const bin = Math.floor(edge / width) * width;
            if (!byBin.has(bin)) byBin.set(bin, { bin, total: 0, ...Object.fromEntries(INTERVALS.map(k => [k, 0])) });
            const row = byBin.get(bin);
            INTERVALS.forEach(k => {
                const c = perInterval[k]?.[i] || 0;
                row[k] += c;
                row.total += c;
            });
        });
        const rows = Array.from(byBin.values()).sort((a, b) => a.bin - b.bin);
        const total = rows.reduce((a, r) => a + r.total, 0);
        // Share of firings with score >= the bin's lower edge (what that threshold would keep)
        let above = total;
        rows.forEach(r => {
            r.keptPct = total > 0 ? (above / total) * 100 : 0;
            above -= r.total;
        });
        // Kept share from the stored (finest) bins, so it stays exact whatever the display width
        const kept = dist.bins.reduce((a, edge, i) => edge >= threshold
            ? a + INTERVALS.reduce((s, k) => s + (perInterval[k]?.[i] || 0), 0) : a, 0);
        return { rows, total, kept };
    }, [dist, side, threshold, width]);

    if (total === 0) {
        return <div className="text-xs text-muted-foreground py-4">No {side.toUpperCase()} scores in the latest run.</div>;
    }

    return (
        <div>
            <div className="text-[11px] text-muted-foreground mb-1">
                Threshold {threshold} keeps <span className="text-foreground font-medium">{((kept / total) * 100).toFixed(0)}%</span> of {total.toLocaleString()} {side.toUpperCase()} firings
            </div>
            <div className="h-32">
                <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={rows} margin={{ left: 0, right: 4, top: 4, bottom: 0 }} barCategoryGap={width === 1 ? 0 : 1}>
                        <XAxis dataKey="bin" tick={{ fontSize: 10 }} interval={Math.max(0, Math.ceil(rows.length / 10) - 1)} />
                        <YAxis tick={{ fontSize: 10 }} width={40} tickFormatter={(v) => v >= 1000 ? `${(v / 1000).toFixed(0)}k` : v} />
                        <Tooltip content={<DistributionTooltip binWidth={width} />} cursor={{ fill: 'rgba(150,150,150,0.15)' }} />
                        {INTERVALS.map(k => (
                            <Bar key={k} dataKey={k} stackId="s" fill={INTERVAL_COLORS[k]} isAnimationActive={false}>
                                {rows.map(r => <Cell key={r.bin} fillOpacity={r.bin + width > threshold ? 0.9 : 0.25} />)}
                            </Bar>
                        ))}
                        <ReferenceLine x={[...rows].reverse().find(r => r.bin <= threshold)?.bin} stroke="hsl(var(--foreground))" strokeDasharray="3 3" />
                    </BarChart>
                </ResponsiveContainer>
            </div>
        </div>
    );
};
