import { format } from 'date-fns';
import { useState, type ReactNode } from 'react';
import { IndexSummaryCard, type IndexSummaryCardProps } from './IndexSummaryCard';
import { MarketBreadthChart } from './MarketBreadthChart';
import { BreadthHistogramPanel } from './BreadthHistogramPanel';

function ReportFigure({ id, title, children }: { id: string; title: string; children: ReactNode }) {
    const [open, setOpen] = useState(false);
    return <details id={id} className="report-figure-toggle" onToggle={event => setOpen(event.currentTarget.open)}>
        <summary>{title}</summary>
        {open && <div className="report-figure-content">{children}</div>}
    </details>;
}

/** One visual implementation for the dashboard and the offline report. */
export function IndexSummaryFigures({ expanded = false, anchorPrefix = "sector", ...props }: IndexSummaryCardProps & { expanded?: boolean; anchorPrefix?: string }) {
    if (!expanded) return <IndexSummaryCard {...props} />;
    const start = format(props.minDate, 'yyyy-MM-dd');
    const end = props.maxDate ? format(props.maxDate, 'yyyy-MM-dd') : '9999-12-31';
    const filter = <T extends { date: string }>(rows: T[] = []) => rows.filter(row => row.date >= start && row.date <= end);
    return <div className="report-figures space-y-6" data-index={props.title}>
        <div className="report-summary mx-auto w-full max-w-xl" data-figure="summary">
            <IndexSummaryCard {...props} staticSummary />
        </div>
        <ReportFigure id={`${anchorPrefix}-breadth`} title={`${props.title} — Market Breadth`}>
        <div data-figure="market-breadth" className="report-breadth">
            <MarketBreadthChart {...props} indexTitle={props.title} />
        </div>
        </ReportFigure>
        <ReportFigure id={`${anchorPrefix}-distribution`} title={`${props.title} — Distribution`}>
        <div data-figure="distribution" className="report-distribution border rounded-lg bg-card" style={{ height: 1030 }}>
            <BreadthHistogramPanel
                title={props.title}
                cdSignalBreadth={filter(props.cdSignalBreadth)} mcSignalBreadth={filter(props.mcSignalBreadth)}
                cdScoreBreadth={filter(props.cdScoreBreadth)} mcScoreBreadth={filter(props.mcScoreBreadth)}
                cdCompanyBreadth={filter(props.cdCompanyBreadth)} mcCompanyBreadth={filter(props.mcCompanyBreadth)}
                intervalWeights={props.intervalWeights} tickers={props.tickers ?? []} firstDates={props.firstDates}
                tickerWeights={props.tickerWeights} capHistory={props.capHistory}
                filteredSpxData={props.spxData.filter(row => row.time.slice(0, 10) >= start && row.time.slice(0, 10) <= end)}
                onNavigateRight={() => {}} isFullscreen
            />
        </div>
        </ReportFigure>
    </div>;
}
