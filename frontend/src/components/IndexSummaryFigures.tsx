import { format } from 'date-fns';
import { IndexSummaryCard, type IndexSummaryCardProps } from './IndexSummaryCard';
import { MarketBreadthChart } from './MarketBreadthChart';
import { BreadthHistogramPanel } from './BreadthHistogramPanel';

/** One visual implementation for the dashboard and the offline report. */
export function IndexSummaryFigures({ expanded = false, ...props }: IndexSummaryCardProps & { expanded?: boolean }) {
    if (!expanded) return <IndexSummaryCard {...props} />;
    const start = format(props.minDate, 'yyyy-MM-dd');
    const end = props.maxDate ? format(props.maxDate, 'yyyy-MM-dd') : '9999-12-31';
    const filter = <T extends { date: string }>(rows: T[] = []) => rows.filter(row => row.date >= start && row.date <= end);
    return <div className="report-figures space-y-6" data-index={props.title}>
        <div className="report-summary mx-auto w-full max-w-xl" data-figure="summary">
            <IndexSummaryCard {...props} staticSummary />
        </div>
        <div data-figure="market-breadth" className="report-breadth">
            <h3 className="text-lg font-semibold mb-2">{props.title} — Market Breadth</h3>
            <MarketBreadthChart {...props} indexTitle={props.title} />
        </div>
        <div data-figure="distribution" className="report-distribution border rounded-lg bg-card" style={{ height: 850 }}>
            <BreadthHistogramPanel
                title={props.title}
                cdSignalBreadth={filter(props.cdSignalBreadth)} mcSignalBreadth={filter(props.mcSignalBreadth)}
                cdScoreBreadth={filter(props.cdScoreBreadth)} mcScoreBreadth={filter(props.mcScoreBreadth)}
                cdBreadth={filter(props.cdBreadth)} mcBreadth={filter(props.mcBreadth)}
                cdBreakthroughScoreBreadth={filter(props.cdBreakthroughScoreBreadth)} mcBreakthroughScoreBreadth={filter(props.mcBreakthroughScoreBreadth)}
                intervalWeights={props.intervalWeights} tickers={props.tickers ?? []}
                filteredSpxData={props.spxData.filter(row => row.time.slice(0, 10) >= start && row.time.slice(0, 10) <= end)}
                onNavigateRight={() => {}} isFullscreen
            />
        </div>
    </div>;
}
