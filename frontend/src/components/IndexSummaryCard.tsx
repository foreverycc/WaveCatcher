import React, { useCallback, useMemo, useState } from 'react';
import { format } from 'date-fns';
import { useQuery } from '@tanstack/react-query';
import { analysisApi } from '../services/api';
import { MarketBreadthChart } from './MarketBreadthChart';
import { BreadthHistogramPanel } from './BreadthHistogramPanel';
import { cn } from '../utils/cn';
import { companiesFromSignalBreadth, type CapHistory, type CompanyBreadthPoint, type DmaBreadthPoint, type FirstDates } from '../utils/marketBreadth';
import { Maximize2, Minimize2 } from 'lucide-react';

interface BreadthDataPoint {
    date: string;
    count_1h: number;
    count_2h: number;
    count_3h: number;
    count_4h: number;
    count_1d: number;
}

interface SignalBreadthDataPoint {
    date: string;
    count_1h: number;
    count_2h: number;
    count_3h: number;
    count_4h: number;
    count_1d: number;
}

// Shared empty array for missing props, so the charts' memoized data keeps its identity across renders
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const NONE: any[] = [];

export interface IndexSummaryCardProps {
    /** saved data only (the offline report): no live requests, no switching to a single stock */
    offline?: boolean;
    /** day picked in Market Trend (YYYY-MM-DD): the Distributions mark it instead of the latest day */
    focusDate?: string | null;
    title: string;
    spxData: any[];
    cdBreadth: BreadthDataPoint[];
    mcBreadth: BreadthDataPoint[];
    cdSignalBreadth?: SignalBreadthDataPoint[];
    mcSignalBreadth?: SignalBreadthDataPoint[];
    cdScoreBreadth?: { date: string, score_1h: number, score_2h: number, score_3h: number, score_4h: number, score_1d: number, total_score: number }[];
    mcScoreBreadth?: { date: string, score_1h: number, score_2h: number, score_3h: number, score_4h: number, score_1d: number, total_score: number }[];
    cdBreakthroughScoreBreadth?: { date: string, score_1h: number, score_2h: number, score_3h: number, score_4h: number, score_1d: number, total_score: number }[];
    mcBreakthroughScoreBreadth?: { date: string, score_1h: number, score_2h: number, score_3h: number, score_4h: number, score_1d: number, total_score: number }[];
    cdCompanyBreadth?: CompanyBreadthPoint[];
    mcCompanyBreadth?: CompanyBreadthPoint[];
    tickerWeights?: Record<string, number>;
    intervalWeights?: Record<string, number>;
    minDate: Date;
    maxDate?: Date;
    signals1234?: { cd_dates: string[], mc_dates: string[] };
    tickers?: string[];
    /** first trading day of recently listed stocks: they only count from then on */
    firstDates?: FirstDates;
    /** price history for weights at each day's market cap */
    capHistory?: CapHistory;
    /** % of stocks above their 20 / 50 / 200-day moving average */
    dmaBreadth?: DmaBreadthPoint[];
    indexTicker?: string;
}

export const IndexSummaryCard: React.FC<IndexSummaryCardProps> = ({
    offline = false,
    title,
    spxData,
    cdBreadth,
    mcBreadth,
    cdSignalBreadth = NONE,
    mcSignalBreadth = NONE,
    cdScoreBreadth = NONE,
    mcScoreBreadth = NONE,
    cdBreakthroughScoreBreadth = NONE,
    mcBreakthroughScoreBreadth = NONE,
    cdCompanyBreadth = NONE,
    mcCompanyBreadth = NONE,
    tickerWeights,
    intervalWeights,
    firstDates,
    capHistory,
    dmaBreadth,
    minDate,
    maxDate,
    signals1234,
    tickers = NONE,
    indexTicker,
    focusDate
}) => {
    const [cardView, setCardView] = useState<'histogram' | 'chart'>('chart');
    const [selectedTicker, setSelectedTicker] = useState<string>('');
    const [chartFullscreen, setChartFullscreen] = useState(false);
    const [histogramFullscreen, setHistogramFullscreen] = useState(false);

    // Effective ticker is either the selected component or the index itself
    const effectiveTicker = selectedTicker || indexTicker;

    // Fetch price history for the selected component stock (only if selected)
    const { data: stockData } = useQuery({
        queryKey: ['stockPriceHistory', selectedTicker, '1d'],
        queryFn: () => analysisApi.getPriceHistory(selectedTicker, '1d'),
        staleTime: 1000 * 60 * 60, // 1 hour
        enabled: !offline && !!selectedTicker && cardView === 'chart'
    });

    // Fetch per-ticker signal/score data across all intervals (for component OR index)
    const { data: tickerSignals } = useQuery({
        queryKey: ['tickerSignals', effectiveTicker],
        queryFn: () => effectiveTicker ? analysisApi.getTickerSignals(effectiveTicker) : null,
        staleTime: 1000 * 60 * 60,
        enabled: !offline && !!effectiveTicker && cardView === 'chart'
    });

    // Quarterly revenue / gross profit / net income / EPS: the selected stock, or the stock-list totals
    const { data: fundamentals } = useQuery({
        queryKey: ['fundamentals', selectedTicker || `list:${title}`, selectedTicker ? '' : tickers.length],
        queryFn: () => selectedTicker ? analysisApi.getFundamentals(selectedTicker) : analysisApi.getFundamentalsAggregate(tickers),
        staleTime: 1000 * 60 * 60,
        enabled: !offline && cardView === 'chart' && (!!selectedTicker || tickers.length > 0)
    });

    // Earnings report dates of the selected stock (marked in the EPS lane)
    const { data: earnings } = useQuery({
        queryKey: ['earningsDates', selectedTicker],
        queryFn: () => analysisApi.getEarningsDates(selectedTicker),
        staleTime: 1000 * 60 * 60,
        enabled: !offline && !!selectedTicker && cardView === 'chart'
    });

    // When a ticker is selected, swap index-level breadth with per-ticker data
    // If NO ticker selected (Index view):
    // - Panels use CD/MC Breadth (Sector Sums) passed via props
    // - Chart uses spxData (Index Price + Index Signals)
    const useTickerSignals = !!selectedTicker && !!tickerSignals;

    const effectiveCdBreadth = useTickerSignals ? tickerSignals!.cd_breadth : cdBreadth;
    const effectiveMcBreadth = useTickerSignals ? tickerSignals!.mc_breadth : mcBreadth;
    const effectiveCdSignalBreadth = useTickerSignals ? tickerSignals!.cd_signal_breadth : cdSignalBreadth;
    const effectiveMcSignalBreadth = useTickerSignals ? tickerSignals!.mc_signal_breadth : mcSignalBreadth;
    const effectiveCdScoreBreadth = useTickerSignals ? tickerSignals!.cd_score_breadth : cdScoreBreadth;
    const effectiveMcScoreBreadth = useTickerSignals ? tickerSignals!.mc_score_breadth : mcScoreBreadth;
    const effectiveCdBtScoreBreadth = useTickerSignals ? (tickerSignals!.cd_breakthrough_score_breadth ?? NONE) : cdBreakthroughScoreBreadth;
    const effectiveMcBtScoreBreadth = useTickerSignals ? (tickerSignals!.mc_breakthrough_score_breadth ?? NONE) : mcBreakthroughScoreBreadth;

    // Market breadth: companies with a CD / MC signal per day (a single ticker counts 1 on its signal days)
    const effectiveCdCompanyBreadth = useMemo(() => useTickerSignals ? companiesFromSignalBreadth(effectiveCdSignalBreadth) : cdCompanyBreadth,
        [useTickerSignals, effectiveCdSignalBreadth, cdCompanyBreadth]);
    const effectiveMcCompanyBreadth = useMemo(() => useTickerSignals ? companiesFromSignalBreadth(effectiveMcSignalBreadth) : mcCompanyBreadth,
        [useTickerSignals, effectiveMcSignalBreadth, mcCompanyBreadth]);

    // --- Filter data by date range ---
    const minDateStr = useMemo(() => format(minDate, 'yyyy-MM-dd'), [minDate]);
    const maxDateStr = useMemo(() => maxDate ? format(maxDate, 'yyyy-MM-dd') : null, [maxDate]);

    const filteredSpxData = useMemo(() => {
        if (!spxData) return [];
        return spxData.filter(d => {
            const date = d.time?.split('T')[0] ?? '';
            if (date < minDateStr) return false;
            if (maxDateStr && date > maxDateStr) return false;
            return true;
        });
    }, [spxData, minDateStr, maxDateStr]);

    const filterByDateRange = useCallback(<T extends { date: string }>(data: T[]): T[] => {
        if (!data) return [];
        return data.filter(d => {
            if (d.date < minDateStr) return false;
            if (maxDateStr && d.date > maxDateStr) return false;
            return true;
        });
    }, [minDateStr, maxDateStr]);

    const chartCardHeight = '1060px';

    return (
        <>
            <div
                className="relative w-full"
                style={{
                    // the Market Breadth chart's height (see MarketBreadthChart) + header
                    height: chartCardHeight,
                    minHeight: chartCardHeight,
                }}
            >
                {/* === HISTOGRAM VIEW === */}
                <div
                    className={cn(
                        "border rounded-lg bg-card overflow-hidden",
                        cardView === 'histogram' ? 'relative opacity-100 w-full h-full' : 'absolute inset-0 opacity-0 pointer-events-none'
                    )}
                >
                    {cardView === 'histogram' && (
                        <BreadthHistogramPanel
                            title={title}
                            cdSignalBreadth={filterByDateRange(cdSignalBreadth)}
                            mcSignalBreadth={filterByDateRange(mcSignalBreadth)}
                            cdScoreBreadth={filterByDateRange(cdScoreBreadth)}
                            mcScoreBreadth={filterByDateRange(mcScoreBreadth)}
                            cdCompanyBreadth={filterByDateRange(cdCompanyBreadth)}
                            mcCompanyBreadth={filterByDateRange(mcCompanyBreadth)}
                            intervalWeights={intervalWeights}
                            tickers={tickers}
                            firstDates={firstDates}
                            filteredSpxData={filteredSpxData}
                        focusDate={focusDate}
                        tickerWeights={tickerWeights}
                        capHistory={capHistory}
                            onNavigateRight={() => setCardView('chart')}
                            onMaximize={() => setHistogramFullscreen(true)}
                        />
                    )}
                </div>

                {/* === CHART VIEW === */}
                <div
                    className={cn(
                        "border rounded-lg bg-card overflow-hidden",
                        cardView === 'chart' ? 'relative opacity-100 w-full h-full' : 'absolute inset-0 opacity-0 pointer-events-none'
                    )}
                >
                    <div className="border rounded-lg bg-card overflow-hidden h-full flex flex-col">
                        <div
                            className="p-2 border-b bg-muted/30 flex justify-between items-center shrink-0"
                        >
                            <span className="text-sm font-medium">{title} — Market Breadth</span>
                            <div className="flex items-center gap-2">
                                <button
                                    onClick={() => setChartFullscreen(true)}
                                    className="p-2 text-muted-foreground hover:text-foreground rounded-md hover:bg-muted/50 transition-colors"
                                    title="Maximize"
                                >
                                    <Maximize2 className="w-4 h-4" />
                                </button>
                                <button
                                    onClick={() => setCardView('histogram')}
                                    className="text-xs text-muted-foreground hover:text-foreground transition-colors"
                                >
                                    ← Distributions
                                </button>
                            </div>
                        </div>
                        <div className="p-1 flex-1 min-h-0">
                            {cardView === 'chart' && (
                                <MarketBreadthChart
                                    title={title}
                                    spxData={selectedTicker && stockData ? stockData : spxData}
                                    cdBreadth={effectiveCdBreadth}
                                    mcBreadth={effectiveMcBreadth}
                                    cdSignalBreadth={effectiveCdSignalBreadth}
                                    mcSignalBreadth={effectiveMcSignalBreadth}
                                    cdScoreBreadth={effectiveCdScoreBreadth}
                                    mcScoreBreadth={effectiveMcScoreBreadth}
                                    cdBreakthroughScoreBreadth={effectiveCdBtScoreBreadth}
                                    mcBreakthroughScoreBreadth={effectiveMcBtScoreBreadth}
                                    cdCompanyBreadth={effectiveCdCompanyBreadth}
                                    mcCompanyBreadth={effectiveMcCompanyBreadth}
                                    tickerWeights={useTickerSignals ? undefined : tickerWeights}
                                    capHistory={useTickerSignals ? undefined : capHistory}
                                    dmaBreadth={useTickerSignals ? undefined : dmaBreadth}
                                    intervalWeights={intervalWeights}
                                    minDate={minDate}
                                    maxDate={maxDate}
                                    signals1234={selectedTicker ? undefined : signals1234}
                                    tickers={tickers}
                                    firstDates={firstDates}
                                    selectedTicker={selectedTicker}
                                    onTickerChange={offline ? undefined : setSelectedTicker}
                                    indexTitle={title}
                                    fundamentals={fundamentals}
                                    earnings={selectedTicker ? earnings : undefined}
                                />
                            )}
                        </div>
                    </div>
                </div>
            </div>

            {/* === FULLSCREEN OVERLAY === */}
            {chartFullscreen && (
                <div
                    className="absolute inset-0 z-[9999] flex flex-col bg-card overflow-hidden"
                    onClick={(e) => e.stopPropagation()}
                >
                    <div className="p-2 border-b bg-muted/30 flex justify-between items-center shrink-0">
                        <span className="text-sm font-medium">{title} — Market Breadth</span>
                        <div className="flex items-center gap-2">
                            <button
                                onClick={() => setChartFullscreen(false)}
                                className="p-2 text-muted-foreground hover:text-foreground rounded-md hover:bg-muted/50 transition-colors"
                                title="Restore"
                            >
                                <Minimize2 className="w-4 h-4" />
                            </button>
                            <button
                                onClick={() => { setChartFullscreen(false); setCardView('histogram'); }}
                                className="text-xs text-muted-foreground hover:text-foreground transition-colors"
                            >
                                ← Distributions
                            </button>
                        </div>
                    </div>
                    <div className="p-1 flex-1 min-h-0 overflow-y-auto">
                        <MarketBreadthChart
                            title={title}
                            spxData={selectedTicker && stockData ? stockData : spxData}
                            cdBreadth={effectiveCdBreadth}
                            mcBreadth={effectiveMcBreadth}
                            cdSignalBreadth={effectiveCdSignalBreadth}
                            mcSignalBreadth={effectiveMcSignalBreadth}
                            cdScoreBreadth={effectiveCdScoreBreadth}
                            mcScoreBreadth={effectiveMcScoreBreadth}
                            cdBreakthroughScoreBreadth={effectiveCdBtScoreBreadth}
                            mcBreakthroughScoreBreadth={effectiveMcBtScoreBreadth}
                            cdCompanyBreadth={effectiveCdCompanyBreadth}
                            mcCompanyBreadth={effectiveMcCompanyBreadth}
                            tickerWeights={useTickerSignals ? undefined : tickerWeights}
                                    capHistory={useTickerSignals ? undefined : capHistory}
                                    dmaBreadth={useTickerSignals ? undefined : dmaBreadth}
                            intervalWeights={intervalWeights}
                            minDate={minDate}
                            maxDate={maxDate}
                            signals1234={selectedTicker ? undefined : signals1234}
                            tickers={tickers}
                            firstDates={firstDates}
                            selectedTicker={selectedTicker}
                            onTickerChange={offline ? undefined : setSelectedTicker}
                            indexTitle={title}
                            fundamentals={fundamentals}
                                    earnings={selectedTicker ? earnings : undefined}
                        />
                    </div>
                </div>
            )}

            {/* === HISTOGRAM FULLSCREEN OVERLAY === */}
            {histogramFullscreen && (
                <div
                    className="absolute inset-0 z-[9999] flex flex-col bg-card overflow-hidden"
                    onClick={(e) => e.stopPropagation()}
                >
                    <BreadthHistogramPanel
                        title={title}
                        cdSignalBreadth={filterByDateRange(cdSignalBreadth)}
                        mcSignalBreadth={filterByDateRange(mcSignalBreadth)}
                        cdScoreBreadth={filterByDateRange(cdScoreBreadth)}
                        mcScoreBreadth={filterByDateRange(mcScoreBreadth)}
                        cdCompanyBreadth={filterByDateRange(cdCompanyBreadth)}
                        mcCompanyBreadth={filterByDateRange(mcCompanyBreadth)}
                        intervalWeights={intervalWeights}
                        tickers={tickers}
                        firstDates={firstDates}
                        filteredSpxData={filteredSpxData}
                        focusDate={focusDate}
                        tickerWeights={tickerWeights}
                        capHistory={capHistory}
                        onNavigateRight={() => { setHistogramFullscreen(false); setCardView('chart'); }}
                        onMaximize={() => setHistogramFullscreen(false)}
                        isFullscreen={true}
                    />
                </div>
            )}
        </>
    );
};
