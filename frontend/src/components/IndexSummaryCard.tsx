import React, { useCallback, useMemo, useState } from 'react';
import { format } from 'date-fns';
import { useQuery } from '@tanstack/react-query';
import { analysisApi } from '../services/api';
import { MarketBreadthChart } from './MarketBreadthChart';
import { BreadthHistogramPanel } from './BreadthHistogramPanel';
import { cn } from '../utils/cn';
import { breadthShare, breadthScore, companiesFromSignalBreadth, balanceIndex, signalCountSeries, scoreSeries, listedCount, type CapHistory, type CompanyBreadthPoint, type DmaBreadthPoint, type FirstDates } from '../utils/marketBreadth';
import { Gauge, PLAIN_ZONES, BALANCE_ZONES, zoneOf, toneText } from './Gauge';
import { Maximize2, Minimize2, ChevronLeft, ChevronRight } from 'lucide-react';

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

export interface IndexSummaryCardProps {
    staticSummary?: boolean;
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
    title,
    spxData,
    cdBreadth,
    mcBreadth,
    cdSignalBreadth = [],
    mcSignalBreadth = [],
    cdScoreBreadth = [],
    mcScoreBreadth = [],
    cdBreakthroughScoreBreadth = [],
    mcBreakthroughScoreBreadth = [],
    cdCompanyBreadth = [],
    mcCompanyBreadth = [],
    tickerWeights,
    intervalWeights,
    firstDates,
    capHistory,
    dmaBreadth,
    minDate,
    maxDate,
    signals1234,
    tickers = [],
    indexTicker,
    staticSummary = false
}) => {
    const [cardView, setCardView] = useState<'summary' | 'histogram' | 'chart'>('summary');
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
        enabled: !staticSummary && !!selectedTicker && cardView === 'chart'
    });

    // Fetch per-ticker signal/score data across all intervals (for component OR index)
    const { data: tickerSignals } = useQuery({
        queryKey: ['tickerSignals', effectiveTicker],
        queryFn: () => effectiveTicker ? analysisApi.getTickerSignals(effectiveTicker) : null,
        staleTime: 1000 * 60 * 60,
        enabled: !staticSummary && !!effectiveTicker && cardView === 'chart'
    });

    // Quarterly revenue / gross profit / net income / EPS: the selected stock, or the stock-list totals
    const { data: fundamentals } = useQuery({
        queryKey: ['fundamentals', selectedTicker || `list:${title}`, selectedTicker ? '' : tickers.length],
        queryFn: () => selectedTicker ? analysisApi.getFundamentals(selectedTicker) : analysisApi.getFundamentalsAggregate(tickers),
        staleTime: 1000 * 60 * 60,
        enabled: !staticSummary && cardView === 'chart' && (!!selectedTicker || tickers.length > 0)
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
    const effectiveCdBtScoreBreadth = useTickerSignals ? (tickerSignals!.cd_breakthrough_score_breadth ?? []) : cdBreakthroughScoreBreadth;
    const effectiveMcBtScoreBreadth = useTickerSignals ? (tickerSignals!.mc_breakthrough_score_breadth ?? []) : mcBreakthroughScoreBreadth;

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

    // --- Derive summary metrics from existing data ---

    // Latest close price + daily change
    const priceInfo = useMemo(() => {
        if (!filteredSpxData || filteredSpxData.length === 0) return null;
        const validPriceData = filteredSpxData.filter(d => d && d.close !== null && d.close !== undefined);
        if (validPriceData.length === 0) return null;
        const latest = validPriceData[validPriceData.length - 1];
        const prev = validPriceData.length > 1 ? validPriceData[validPriceData.length - 2] : null;
        const change = prev && prev.close ? ((latest.close - prev.close) / prev.close) * 100 : 0;
        return {
            close: latest.close,
            change,
            date: latest.time?.split('T')[0] ?? ''
        };
    }, [filteredSpxData]);

    // CD/MC signals for last 7 trading days (from price history 1d data)
    const recentSignals = useMemo(() => {
        if (!filteredSpxData || filteredSpxData.length === 0) return [];
        const last7 = filteredSpxData.slice(-7);
        return last7.map(d => ({
            date: d.time?.split('T')[0] ?? '',
            cd: !!d.cd_signal,
            mc: !!d.mc_signal
        }));
    }, [filteredSpxData]);

    // 1234 signals for last 7 days — per-day dot format (matches recentSignals shape)
    const recent1234Dots = useMemo(() => {
        if (!signals1234 || !filteredSpxData || filteredSpxData.length === 0) return [] as { date: string, cd: boolean, mc: boolean }[];
        const last7 = filteredSpxData.slice(-7);
        const cdSet = new Set(signals1234.cd_dates || []);
        const mcSet = new Set(signals1234.mc_dates || []);
        return last7.map(d => {
            const date = d.time?.split('T')[0] ?? '';
            return {
                date,
                cd: cdSet.has(date),
                mc: mcSet.has(date)
            };
        });
    }, [signals1234, filteredSpxData]);

    // Helper: compute percentile of a value within a sorted array
    const computePercentile = (value: number, data: number[]): number => {
        if (data.length === 0) return 0;
        // Special case: if value is 0 (the absolute minimum for counts/scores), it's the 0th percentile.
        // Otherwise, a dataset with 90% zeros would assign the ~45th percentile to a value of 0 
        // due to the standard statistical tie-breaking formula.
        if (value === 0) return 0;

        const sorted = [...data].sort((a, b) => a - b);
        const below = sorted.filter(v => v < value).length;
        const equal = sorted.filter(v => v === value).length;
        return ((below + equal * 0.5) / sorted.length) * 100;
    };

    // CD vs MC balance gauges (0-100): percentile of today's CD - MC among the days in range
    const gauges = useMemo(() => {
        const days = (filteredSpxData || []).map((d: any) => d.time?.split('T')[0] ?? '').filter(Boolean);
        const n = listedCount(tickers, firstDates);
        const last = (idx: number[]) => idx.length ? idx[idx.length - 1] : 50;
        const pct = (rows: CompanyBreadthPoint[]) => breadthShare(rows, n).map(r => ({ date: r.date, value: r.value * 100 }));
        const bs = balanceIndex(
            breadthScore(cdCompanyBreadth, cdScoreBreadth, intervalWeights, n),
            breadthScore(mcCompanyBreadth, mcScoreBreadth, intervalWeights, n), days);
        const ago = (k: number) => bs.length > k ? bs[bs.length - 1 - k] : null;
        return {
            breadthScore: last(bs),
            history: [
                { label: 'Previous day', value: ago(1) },
                { label: '1 week ago', value: ago(5) },
                { label: '1 month ago', value: ago(21) },
            ],
            signals: last(balanceIndex(signalCountSeries(cdSignalBreadth, n), signalCountSeries(mcSignalBreadth, n), days)),
            scores: last(balanceIndex(scoreSeries(cdScoreBreadth, intervalWeights, n), scoreSeries(mcScoreBreadth, intervalWeights, n), days)),
            breadth: last(balanceIndex(pct(cdCompanyBreadth), pct(mcCompanyBreadth), days)),
        };
    }, [filteredSpxData, tickers, cdCompanyBreadth, mcCompanyBreadth, cdScoreBreadth, mcScoreBreadth, cdSignalBreadth, mcSignalBreadth, intervalWeights, firstDates]);

    // Volume: today vs 1yr average + percentile
    const volumeStats = useMemo(() => {
        if (!filteredSpxData || filteredSpxData.length === 0) return null;
        const validVolumeData = filteredSpxData.filter(d => d && d.volume !== null && d.volume !== undefined && d.volume > 0);
        if (validVolumeData.length === 0) return null;
        const todayVol = validVolumeData[validVolumeData.length - 1].volume;
        const volumes = validVolumeData.map((d: any) => d.volume);
        const avg = volumes.reduce((a: number, b: number) => a + b, 0) / volumes.length;
        const ratio = avg > 0 ? ((todayVol - avg) / avg) * 100 : 0;
        const percentile = computePercentile(todayVol, volumes);
        return { today: todayVol, avg, ratio, percentile };
    }, [filteredSpxData]);

    const chartCardHeight = selectedTicker ? '1360px' : '1560px';

    return (
        <>
            <div
                className="relative w-full"
                style={{
                    // chart view: the Market Breadth chart's height (see MarketBreadthChart) + header
                    height: cardView === 'chart' ? chartCardHeight : cardView === 'histogram' ? '888px' : 'auto',
                    minHeight: cardView === 'chart' ? chartCardHeight : cardView === 'histogram' ? '888px' : '0px',
                    transition: 'height 0.4s ease, min-height 0.4s ease'
                }}
            >
                {/* === SUMMARY VIEW === */}
                <div
                    className={cn(
                        "border rounded-lg bg-card p-4 shadow-sm hover:shadow-md transition-all overflow-hidden",
                        "w-full",
                        cardView === 'summary' ? 'relative opacity-100' : 'absolute inset-0 opacity-0 pointer-events-none'
                    )}
                >
                    {/* Header */}
                    <div className="flex items-center justify-between mb-2">
                        <h3 className="text-lg font-bold">{title}</h3>
                        {priceInfo && (
                            <div className="text-right">
                                <span className="text-lg font-semibold">{priceInfo.close.toLocaleString(undefined, { maximumFractionDigits: 2 })}</span>
                                <span className={cn(
                                    "ml-2 text-sm font-medium",
                                    priceInfo.change >= 0 ? "text-green-500" : "text-red-500"
                                )}>
                                    {priceInfo.change >= 0 ? '+' : ''}{priceInfo.change.toFixed(2)}%
                                </span>
                            </div>
                        )}
                    </div>

                    {/* CD/MC Signals last 7 days */}
                    <div className="mb-1 flex items-center gap-4">
                        <span className="text-xs text-muted-foreground font-medium shrink-0">idx CD/MC</span>
                        <div className="flex gap-2 items-center flex-wrap">
                            {recentSignals.map((s, i) => (
                                <div key={i} className="flex flex-col items-center gap-0.5">
                                    <span className="text-[10px] text-muted-foreground">{s.date.slice(5)}</span>
                                    <div className="flex gap-0.5">
                                        <div className={cn(
                                            "w-3 h-3 rounded-full border",
                                            s.cd ? "bg-green-500 border-green-600" : "bg-muted border-border"
                                        )} title={`CD ${s.cd ? 'Buy' : '-'}`} />
                                        <div className={cn(
                                            "w-3 h-3 rounded-full border",
                                            s.mc ? "bg-red-500 border-red-600" : "bg-muted border-border"
                                        )} title={`MC ${s.mc ? 'Sell' : '-'}`} />
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>

                    {/* 1234 Signals last 7 days */}
                    <div className="mb-1 flex items-center gap-7">
                        <span className="text-xs text-muted-foreground font-medium shrink-0">idx 1234</span>
                        <div className="flex gap-2 items-center flex-wrap">
                            {recent1234Dots.map((s, i) => (
                                <div key={i} className="flex flex-col items-center gap-0.5">
                                    <span className="text-[10px] text-muted-foreground">{s.date.slice(5)}</span>
                                    <div className="flex gap-0.5">
                                        <div className={cn(
                                            "w-3 h-3 rounded-full border",
                                            s.cd ? "bg-green-500 border-green-600" : "bg-muted border-border"
                                        )} title={`1234 CD ${s.cd ? 'Buy' : '-'}`} />
                                        <div className={cn(
                                            "w-3 h-3 rounded-full border",
                                            s.mc ? "bg-red-500 border-red-600" : "bg-muted border-border"
                                        )} title={`1234 MC ${s.mc ? 'Sell' : '-'}`} />
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>

                    {/* Breadth Score gauge (main) with recent history */}
                    <div className="flex items-center gap-3 mt-1">
                        <div className="flex-1 min-w-0">
                            <Gauge
                                size="lg"
                                title="Breadth Score"
                                value={gauges.breadthScore}
                            />
                        </div>
                        <div className="w-28 shrink-0 space-y-1.5">
                            {gauges.history.map(h => {
                                const zone = h.value != null ? zoneOf(h.value, BALANCE_ZONES) : null;
                                return (
                                    <div key={h.label} className="flex items-center justify-between gap-1 border-b border-dashed border-border/60 pb-1">
                                        <div className="min-w-0">
                                            <div className="text-[9px] text-muted-foreground leading-tight">{h.label}</div>
                                            <div className={cn("text-[10px] font-semibold leading-tight truncate", zone ? toneText(zone) : 'text-muted-foreground')}>{zone ? zone.label : '-'}</div>
                                        </div>
                                        <span className={cn("text-xs font-bold shrink-0", zone ? toneText(zone) : 'text-muted-foreground')}>{h.value != null ? Math.round(h.value) : '-'}</span>
                                    </div>
                                );
                            })}
                        </div>
                    </div>

                    {/* Smaller gauges: signal count, score, market breadth, volume */}
                    <div className="grid grid-cols-4 gap-1 mt-2">
                        <Gauge title="CD/MC" value={gauges.signals} />
                        <Gauge title="Score" value={gauges.scores} />
                        <Gauge title="Breadth %" value={gauges.breadth} />
                        <Gauge title="Volume" value={volumeStats ? volumeStats.percentile : 50} zones={PLAIN_ZONES} />
                    </div>

                    {/* Navigation arrows */}
                    <div className="flex items-center justify-between mt-1" hidden={staticSummary}>
                        <button
                            onClick={() => setCardView('histogram')}
                            className="flex items-center gap-1 text-[10px] text-muted-foreground/60 hover:text-muted-foreground transition-colors"
                        >
                            <ChevronLeft className="w-3 h-3" /> Distributions
                        </button>
                        <button
                            onClick={() => setCardView('chart')}
                            className="flex items-center gap-1 text-[10px] text-muted-foreground/60 hover:text-muted-foreground transition-colors"
                        >
                            Market Breadth <ChevronRight className="w-3 h-3" />
                        </button>
                    </div>

                </div>

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
                            onNavigateRight={() => setCardView('summary')}
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
                                    onClick={() => setCardView('summary')}
                                    className="text-xs text-muted-foreground hover:text-foreground transition-colors"
                                >
                                    ← Back to summary
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
                                    onTickerChange={setSelectedTicker}
                                    indexTitle={title}
                                    fundamentals={fundamentals}
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
                                onClick={() => { setChartFullscreen(false); setCardView('summary'); }}
                                className="text-xs text-muted-foreground hover:text-foreground transition-colors"
                            >
                                ← Back to summary
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
                            onTickerChange={setSelectedTicker}
                            indexTitle={title}
                            fundamentals={fundamentals}
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
                        onNavigateRight={() => { setHistogramFullscreen(false); setCardView('summary'); }}
                        onMaximize={() => setHistogramFullscreen(false)}
                        isFullscreen={true}
                    />
                </div>
            )}
        </>
    );
};
