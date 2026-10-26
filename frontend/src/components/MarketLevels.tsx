import React, { useMemo, useState } from 'react';
import { parseISO } from 'date-fns';
import { MarketTrendGrid, MARKET_ROW, type Metric } from './MarketTrendGrid';
import { MarketHeatmap, type HeatmapGroup } from './MarketHeatmap';
import { IndexSummaryCard, type IndexSummaryCardProps } from './IndexSummaryCard';

/** An index card's data; the date range and the day picked in Market Trend come from MarketLevels */
export type IndexCardData = Omit<IndexSummaryCardProps, 'minDate' | 'maxDate' | 'focusDate'>;

export interface LevelIndex {
    key: string;
    group: HeatmapGroup;
    card: IndexCardData;
}

interface Props {
    indices: LevelIndex[];
    intervalWeights: Record<string, number>;
    /** Date Filters range of the charts (YYYY-MM-DD) */
    dateRange: { start: string; end: string };
    /** start with every index's heatmap and card open (the report) instead of none (Summary) */
    openAll?: boolean;
    /** wraps each level, e.g. with a section heading in the report */
    renderLevel?: (level: 1 | 2 | 3, content: React.ReactNode) => React.ReactNode;
}

/**
 * The three chart levels: (1) Market Trend, one row per index -> click a row for (2) its stock
 * heatmap -> click a heatmap block for (3) the index card (Market Breadth, flips to Distributions).
 */
export const MarketLevels: React.FC<Props> = ({ indices, intervalWeights, dateRange, openAll = false, renderLevel = (_, content) => content }) => {
    const allKeys = indices.map(idx => idx.key);
    const [heatmapIndices, setHeatmapIndices] = useState<string[]>(() => openAll ? allKeys : []);
    const [heatmapDate, setHeatmapDate] = useState<string | null>(null); // null = latest day
    // Breadth Score by default; Weighted can be shown with it or alone (at least one stays on)
    const [trendMetrics, setTrendMetrics] = useState<Metric[]>(['breadth']);
    const [expandedIndices, setExpandedIndices] = useState<string[]>(() => openAll ? allKeys : []);

    const toggleTrendMetric = (m: Metric) => setTrendMetrics(prev => {
        const next = prev.includes(m) ? prev.filter(x => x !== m) : [...prev, m];
        return next.length ? (['breadth', 'weighted'] as Metric[]).filter(k => next.includes(k)) : prev;
    });
    const toggleHeatmap = (key: string) => {
        setHeatmapDate(null);
        setHeatmapIndices(prev => prev.includes(key) ? prev.filter(k => k !== key) : [...prev, key]);
    };
    const toggleAllHeatmaps = () => {
        setHeatmapDate(null);
        setHeatmapIndices(prev => prev.length === indices.length ? [] : allKeys);
    };
    const pickHeatmapDay = (key: string, date: string) => {
        setHeatmapDate(date);
        setHeatmapIndices(prev => key === MARKET_ROW
            ? allKeys
            : prev.includes(key) ? prev : [...prev, key]);
    };
    const toggleIndex = (key: string) =>
        setExpandedIndices(prev => prev.includes(key) ? prev.filter(k => k !== key) : [...prev, key]);

    const minDate = useMemo(() => parseISO(dateRange.start), [dateRange.start]);
    const maxDate = useMemo(() => parseISO(dateRange.end), [dateRange.end]);
    const shownGroups = indices.filter(idx => heatmapIndices.includes(idx.key)).map(idx => idx.group);
    const openIndices = indices.filter(idx => expandedIndices.includes(idx.key) && heatmapIndices.includes(idx.key));

    return <>
        {renderLevel(1,
            <MarketTrendGrid
                groups={indices.map(idx => idx.group)}
                intervalWeights={intervalWeights}
                minDate={dateRange.start}
                maxDate={dateRange.end}
                selected={heatmapIndices}
                onToggle={toggleHeatmap}
                onSelectAll={toggleAllHeatmaps}
                onPickDay={pickHeatmapDay}
                pickedDate={heatmapDate}
                metrics={trendMetrics}
                onToggleMetric={toggleTrendMetric}
            />
        )}

        {shownGroups.length > 0 && renderLevel(2,
            <MarketHeatmap
                groups={shownGroups}
                intervalWeights={intervalWeights}
                maxDate={dateRange.end}
                date={heatmapDate}
                metrics={['breadth', 'weighted']}
                onClearDate={() => setHeatmapDate(null)}
                expanded={expandedIndices}
                onToggle={toggleIndex}
            />
        )}

        {/* Market Breadth charts of the indices opened in the heatmap (flip to Distributions inside each card) */}
        {openIndices.length > 0 && renderLevel(3,
            <div className="grid gap-4 w-full grid-cols-1 xl:grid-cols-2">
                {openIndices.map(idx => (
                    <IndexSummaryCard key={idx.key} {...idx.card} minDate={minDate} maxDate={maxDate} focusDate={heatmapDate} />
                ))}
            </div>
        )}
    </>;
};
