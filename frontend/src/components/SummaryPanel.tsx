import React, { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { analysisApi } from '../services/api';
import { MarketBreadthChart } from './MarketBreadthChart';
import { cn } from '../utils/cn';
import { subYears, subMonths, subDays, parseISO, isAfter, format } from 'date-fns';
import { DetailedChartRow, InteractiveOptionChart } from '../pages/Dashboard';

const FetchingChartView = ({ row, type, runId, onClose }: { row: any, type: 'bull' | 'bear', runId: number | undefined, onClose: () => void }) => {
    // Fetch detailed data for this ticker
    const resultType = type === 'bull' ? 'cd_eval_custom_detailed' : 'mc_eval_custom_detailed';

    const { data: detailedData, isLoading } = useQuery({
        queryKey: ['detailedRowData', runId, resultType, row.ticker],
        queryFn: () => runId ? analysisApi.getResult(runId, resultType, row.ticker) : null,
        enabled: !!runId && !!row.ticker
    });

    // Find the matching interval row from detailed data, enriched with best metrics
    const detailedRow = useMemo(() => {
        if (!detailedData || !Array.isArray(detailedData)) return null;
        const match = detailedData.find((d: any) => d.interval === row.interval) || detailedData[0];
        if (match) {
            return { ...match, ...extractBestMetrics(match) };
        }
        return null;
    }, [detailedData, row.interval]);

    return (
        <div className="flex flex-col border rounded-lg bg-card overflow-hidden h-[800px] shadow-lg">
            <div className="p-3 border-b bg-muted/30 flex justify-between items-center sticky top-0 z-10 backdrop-blur">
                <div>
                    <span className="font-medium pl-2 text-lg">{row.ticker}</span>
                    <span className="text-muted-foreground text-sm ml-2">({row.interval}) - {type === 'bull' ? 'Bullish' : 'Bearish'}</span>
                </div>
                <button
                    onClick={onClose}
                    className="px-3 py-1.5 text-sm hover:bg-red-500/10 hover:text-red-500 rounded border border-transparent hover:border-red-200 transition-colors"
                >
                    Close
                </button>
            </div>
            <div className="p-4 flex-1 overflow-y-auto space-y-6">
                {isLoading ? (
                    <div className="flex items-center justify-center h-40 text-muted-foreground">
                        Loading detailed analysis...
                    </div>
                ) : detailedRow ? (
                    <>
                        <DetailedChartRow row={detailedRow} activeSubTab="summary" />

                        {/* Option Chart */}
                        <div style={{ height: '350px' }} className="p-4 border rounded-lg bg-card/50 mt-6">
                            <InteractiveOptionChart ticker={row.ticker} />
                        </div>
                    </>
                ) : (
                    <div className="flex flex-col items-center justify-center h-40 text-muted-foreground">
                        <p>No detailed data available.</p>
                        <p className="text-xs mt-2">Try checking the "Detailed Results" tab.</p>
                    </div>
                )}
            </div>
        </div>
    );
};

// Helper to extract best metrics from detailed row (copied from Dashboard.tsx logic)
const extractBestMetrics = (row: any) => {
    let maxSuccessRate = -1;
    let bestReturn = -1;
    let bestCount = 0;

    for (let i = 0; i <= 100; i++) {
        const rate = row[`success_rate_${i}`];
        const ret = row[`avg_return_${i}`];
        const count = row[`test_count_${i}`];

        if (rate !== undefined && ret !== undefined) {
            if (rate > maxSuccessRate || (rate === maxSuccessRate && ret > bestReturn)) {
                maxSuccessRate = rate;
                bestReturn = ret;
                bestCount = count;
            }
        }
    }

    return {
        success_rate: maxSuccessRate !== -1 ? maxSuccessRate : 0,
        avg_return: bestReturn !== -1 ? bestReturn : 0,
        test_count: bestCount
    };
};

// Chart view for 1234 signals - displays multiple intervals (1h, 2h, 3h + 1d)
const Fetching1234ChartView = ({ row, type, runId, onClose }: { row: any, type: 'bull' | 'bear', runId: number | undefined, onClose: () => void }) => {
    // Fetch detailed data for this ticker
    const resultType = type === 'bull' ? 'cd_eval_custom_detailed' : 'mc_eval_custom_detailed';

    const { data: detailedData, isLoading } = useQuery({
        queryKey: ['detailedRowData', runId, resultType, row.ticker],
        queryFn: () => runId ? analysisApi.getResult(runId, resultType, row.ticker) : null,
        enabled: !!runId && !!row.ticker
    });

    // Prepare rows for 1h, 2h, 3h, 1d sequence
    const detailedRows = useMemo(() => {
        if (!detailedData || !row.intervals) return [];

        // Parse intervals string (e.g., "1,2,3") and add 'h' suffix
        const intervalNumbers = row.intervals.toString().split(',').map((s: string) => s.trim());
        let intervals = intervalNumbers.map((n: string) => `${n}h`);

        // Explicitly add '1d' if not present
        if (!intervals.includes('1d')) {
            intervals.push('1d');
        }

        return intervals.map((interval: string) => {
            const match = detailedData.find((d: any) => d.interval === interval);
            if (match) {
                return { ...match, ...extractBestMetrics(match) };
            }
            // Return dummy if data missing (price chart will still work)
            return {
                ticker: row.ticker,
                interval: interval,
                success_rate: 0,
                avg_return: 0,
                test_count: 0
            };
        });
    }, [detailedData, row.intervals]);

    return (
        <div className="flex flex-col border rounded-lg bg-card overflow-hidden h-[800px] shadow-lg">
            <div className="p-3 border-b bg-muted/30 flex justify-between items-center sticky top-0 z-10 backdrop-blur">
                <div>
                    <span className="font-medium pl-2 text-lg">{row.ticker}</span>
                    <span className="text-muted-foreground text-sm ml-2">
                        (1234 Signal: {row.intervals}) - {type === 'bull' ? 'Bullish' : 'Bearish'}
                    </span>
                </div>
                <button
                    onClick={onClose}
                    className="px-3 py-1.5 text-sm hover:bg-red-500/10 hover:text-red-500 rounded border border-transparent hover:border-red-200 transition-colors"
                >
                    Close
                </button>
            </div>
            <div className="p-4 flex-1 overflow-y-auto space-y-6">
                {isLoading ? (
                    <div className="flex items-center justify-center h-40 text-muted-foreground">
                        Loading detailed analysis...
                    </div>
                ) : detailedRows.length > 0 ? (
                    <>
                        {detailedRows.map((dRow: any, index: number) => (
                            <DetailedChartRow
                                key={`${dRow.ticker}-${dRow.interval}-${index}`}
                                row={dRow}
                                activeSubTab="1234"
                            />
                        ))}

                        {/* Option Chart */}
                        <div style={{ height: '350px' }} className="p-4 border rounded-lg bg-card/50 mt-6">
                            <InteractiveOptionChart ticker={row.ticker} />
                        </div>
                    </>
                ) : (
                    <div className="flex flex-col items-center justify-center h-40 text-muted-foreground">
                        <p>No detailed data available.</p>
                        <p className="text-xs mt-2">Try checking the "1234 Model" tab.</p>
                    </div>
                )}
            </div>
        </div>
    );
};

interface SummaryPanelProps {
    runId: number | undefined;
    onRowClick?: (row: any, type: 'bull' | 'bear') => void;
}

export const SummaryPanel: React.FC<SummaryPanelProps> = ({ runId }) => {

    // --- Data Fetching ---

    // State for In-Line Chart (High Return Opportunities)
    const [selectedRow, setSelectedRow] = React.useState<any | null>(null);
    const [selectedType, setSelectedType] = React.useState<'bull' | 'bear' | null>(null);

    // State for 1234 Signals Chart
    const [selected1234Row, setSelected1234Row] = React.useState<any | null>(null);
    const [selected1234Type, setSelected1234Type] = React.useState<'bull' | 'bear' | null>(null);

    const handleRowClick = (row: any, type: 'bull' | 'bear') => {
        if (selectedRow?.ticker === row.ticker && selectedType === type) {
            setSelectedRow(null);
            setSelectedType(null);
        } else {
            setSelectedRow(row);
            setSelectedType(type);
        }
    };

    const handle1234RowClick = (row: any, type: 'bull' | 'bear') => {
        if (selected1234Row?.ticker === row.ticker && selected1234Type === type) {
            setSelected1234Row(null);
            setSelected1234Type(null);
        } else {
            setSelected1234Row(row);
            setSelected1234Type(type);
        }
    };

    // 1. SPX Data
    const { data: spxHistory } = useQuery({
        queryKey: ['priceHistory', '^SPX', '1d'], // Daily resolution for high level chart
        queryFn: () => analysisApi.getPriceHistory('^SPX', '1d'),
        staleTime: 1000 * 60 * 60, // 1 hour
    });

    // 1b. QQQ Data
    const { data: qqqHistory } = useQuery({
        queryKey: ['priceHistory', 'QQQ', '1d'],
        queryFn: () => analysisApi.getPriceHistory('QQQ', '1d'),
        staleTime: 1000 * 60 * 60, // 1 hour
    });

    // 1c. R2000 Data (using IWM)
    const { data: iwmHistory } = useQuery({
        queryKey: ['priceHistory', 'IWM', '1d'],
        queryFn: () => analysisApi.getPriceHistory('IWM', '1d'),
        staleTime: 1000 * 60 * 60, // 1 hour
    });

    // 1d. Dow Jones Data
    const { data: djiHistory } = useQuery({
        queryKey: ['priceHistory', '^DJI', '1d'],
        queryFn: () => analysisApi.getPriceHistory('^DJI', '1d'),
        staleTime: 1000 * 60 * 60, // 1 hour
    });

    // 2. Market Breadth Data - Index-specific queries
    // SPX -> stocks_sp500.tab
    const { data: spxBreadth } = useQuery({
        queryKey: ['marketBreadth', 'stocks_sp500.tab'],
        queryFn: () => analysisApi.getMarketBreadth('stocks_sp500.tab'),
        staleTime: 1000 * 60 * 5, // 5 minutes
    });
    // QQQ -> stocks_nasdaq100.tab
    const { data: qqqBreadth } = useQuery({
        queryKey: ['marketBreadth', 'stocks_nasdaq100.tab'],
        queryFn: () => analysisApi.getMarketBreadth('stocks_nasdaq100.tab'),
        staleTime: 1000 * 60 * 5,
    });
    // Dow Jones -> stocks_dowjones.tab
    const { data: djiBreadth } = useQuery({
        queryKey: ['marketBreadth', 'stocks_dowjones.tab'],
        queryFn: () => analysisApi.getMarketBreadth('stocks_dowjones.tab'),
        staleTime: 1000 * 60 * 5,
    });
    // IWM -> stocks_russell2000.tab
    const { data: iwmBreadth } = useQuery({
        queryKey: ['marketBreadth', 'stocks_russell2000.tab'],
        queryFn: () => analysisApi.getMarketBreadth('stocks_russell2000.tab'),
        staleTime: 1000 * 60 * 5,
    });

    // 2b. 1234 Signals for each index (from analysis results)
    const { data: spxSignals1234 } = useQuery({
        queryKey: ['signals1234', '^SPX'],
        queryFn: () => analysisApi.getSignals1234('^SPX'),
        staleTime: 1000 * 60 * 60,
    });
    const { data: qqqSignals1234 } = useQuery({
        queryKey: ['signals1234', 'QQQ'],
        queryFn: () => analysisApi.getSignals1234('QQQ'),
        staleTime: 1000 * 60 * 60,
    });
    const { data: iwmSignals1234 } = useQuery({
        queryKey: ['signals1234', 'IWM'],
        queryFn: () => analysisApi.getSignals1234('IWM'),
        staleTime: 1000 * 60 * 60,
    });
    const { data: djiSignals1234 } = useQuery({
        queryKey: ['signals1234', '^DJI'],
        queryFn: () => analysisApi.getSignals1234('^DJI'),
        staleTime: 1000 * 60 * 60,
    });

    // 3. High Return Opportunities (using good_signals / High Return Intervals)
    const { data: bestCD } = useQuery({
        queryKey: ['best', runId, 'cd_eval_good_signals'],
        queryFn: () => runId ? analysisApi.getResult(runId, 'cd_eval_good_signals') : null,
        enabled: !!runId
    });
    const { data: bestMC } = useQuery({
        queryKey: ['best', runId, 'mc_eval_good_signals'],
        queryFn: () => runId ? analysisApi.getResult(runId, 'mc_eval_good_signals') : null,
        enabled: !!runId
    });

    // 4. 1234 Signals Data for Summary Tab table
    const { data: cd1234Data } = useQuery({
        queryKey: ['1234signals', runId, 'cd_breakout_candidates_summary_1234'],
        queryFn: () => runId ? analysisApi.getResult(runId, 'cd_breakout_candidates_summary_1234') : null,
        enabled: !!runId
    });
    const { data: mc1234Data } = useQuery({
        queryKey: ['1234signals', runId, 'mc_breakout_candidates_summary_1234'],
        queryFn: () => runId ? analysisApi.getResult(runId, 'mc_breakout_candidates_summary_1234') : null,
        enabled: !!runId
    });

    // 5. Detailed data for calculating average returns in 1234 table
    const { data: cdDetailedData } = useQuery({
        queryKey: ['detailed', runId, 'cd_eval_custom_detailed'],
        queryFn: () => runId ? analysisApi.getResult(runId, 'cd_eval_custom_detailed') : null,
        enabled: !!runId
    });
    const { data: mcDetailedData } = useQuery({
        queryKey: ['detailed', runId, 'mc_eval_custom_detailed'],
        queryFn: () => runId ? analysisApi.getResult(runId, 'mc_eval_custom_detailed') : null,
        enabled: !!runId
    });

    // Date Filters
    const oneYearAgo = useMemo(() => subYears(new Date(), 1), []);

    // --- Helpers ---
    const formatPercent = (val: number) => `${val.toFixed(1)}%`;



    const TopTable = ({ data, title, type, onRowClick }: {
        data: any[],
        title: string,
        type: 'bull' | 'bear',
        onRowClick?: (row: any, type: 'bull' | 'bear') => void
    }) => {
        if (!data || data.length === 0) return null;

        // Take top 10 sorted by return magnitude, filtered by last 7 days
        const sorted = useMemo(() => {
            const cutoffDate = subDays(new Date(), 7);

            return [...data]
                .filter(row => {
                    if (!row.latest_signal) return false;
                    // Assuming latest_signal is ISO-like string. parseISO handles it.
                    // If it's just YYYY-MM-DD, it works too.
                    try {
                        const date = parseISO(row.latest_signal);
                        return isAfter(date, cutoffDate);
                    } catch (e) {
                        return false;
                    }
                })
                .sort((a, b) =>
                    type === 'bull' ? b.avg_return - a.avg_return : a.avg_return - b.avg_return
                )
                .slice(0, 10);
        }, [data, type]);

        if (sorted.length === 0) return null;

        return (
            <div className="flex flex-col border rounded-lg bg-card overflow-hidden">
                <div className="p-3 bg-muted/30 border-b font-medium flex justify-between">
                    <span>{title}</span>
                    <span className="text-xs text-muted-foreground font-normal mt-1">(Last 7 Days)</span>
                </div>
                <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                        <thead className="bg-muted/10 text-muted-foreground">
                            <tr>
                                <th className="p-2 text-left">Ticker</th>
                                <th className="p-2 text-left">Date</th>
                                <th className="p-2 text-left">Intv</th>
                                <th className="p-2 text-right">Return</th>
                                <th className="p-2 text-right">Win Rate</th>
                                <th className="p-2 text-right">Count</th>
                            </tr>
                        </thead>
                        <tbody>
                            {sorted.map((row, i) => (
                                <tr
                                    key={i}
                                    className="border-b last:border-0 hover:bg-muted/10 cursor-pointer transition-colors"
                                    onClick={() => onRowClick?.(row, type)}
                                >
                                    <td className="p-2 font-medium">{row.ticker}</td>
                                    <td className="p-2 text-muted-foreground text-xs">
                                        {row.latest_signal ? format(parseISO(row.latest_signal), 'MM-dd HH:mm') : '-'}
                                    </td>
                                    <td className="p-2 text-muted-foreground">{row.interval}</td>
                                    <td className={cn("p-2 text-right font-medium", row.avg_return >= 0 ? "text-green-500" : "text-red-500")}>
                                        {formatPercent(row.avg_return)}
                                    </td>
                                    <td className="p-2 text-right">{formatPercent(row.success_rate)}</td>
                                    <td className="p-2 text-right">{row.test_count}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </div>
        );
    };

    // 1234 Signals Table with average return calculation
    const Signals1234Table = ({ data, title, type, onRowClick, detailedData }: {
        data: any[],
        title: string,
        type: 'bull' | 'bear',
        onRowClick?: (row: any, type: 'bull' | 'bear') => void,
        detailedData: any[] | null
    }) => {
        if (!data || data.length === 0) return null;

        // Filter by last 7 days, calculate return, sort by return, take top 10
        const sorted = useMemo(() => {
            // Calculate average return for a row based on its intervals
            const calculateAvgReturn = (row: any) => {
                if (!detailedData || !row.intervals) return 0;

                // Parse intervals string (e.g., "1,2,3" -> ["1h", "2h", "3h"])
                const intervalNumbers = row.intervals.split(',').map((s: string) => s.trim());
                const intervalKeys = intervalNumbers.map((n: string) => `${n}h`);

                // Find matching rows in detailed data for this ticker
                const tickerData = detailedData.filter((d: any) => d.ticker === row.ticker);

                // Get returns for matching intervals (use 0 if not found)
                const returns: number[] = [];
                for (const interval of intervalKeys) {
                    const matchingRow = tickerData.find((d: any) => d.interval === interval);

                    if (matchingRow) {
                        const metrics = extractBestMetrics(matchingRow);
                        returns.push(metrics.avg_return);
                    } else {
                        returns.push(0);
                    }
                }

                // Calculate average (will be 0 if all intervals were missing)
                return returns.reduce((a, b) => a + b, 0) / returns.length;
            };

            const cutoffDate = subDays(new Date(), 7);

            const filtered = [...data]
                .filter(row => {
                    if (!row.date) return false;
                    try {
                        const date = parseISO(row.date);
                        return isAfter(date, cutoffDate);
                    } catch {
                        return false;
                    }
                })
                .map(row => {
                    const calculatedReturn = calculateAvgReturn(row);
                    return {
                        ...row,
                        calculatedReturn
                    };
                });

            return filtered
                .sort((a, b) => {
                    if (a.calculatedReturn !== null && b.calculatedReturn !== null) {
                        return type === 'bull'
                            ? (b.calculatedReturn ?? 0) - (a.calculatedReturn ?? 0)
                            : (a.calculatedReturn ?? 0) - (b.calculatedReturn ?? 0);
                    }
                    return new Date(b.date).getTime() - new Date(a.date).getTime();
                })
                .slice(0, 10);
        }, [data, detailedData, type]);

        if (sorted.length === 0) return null;

        return (
            <div className="flex flex-col border rounded-lg bg-card overflow-hidden">
                <div className="p-3 bg-muted/30 border-b font-medium flex justify-between">
                    <span>{title}</span>
                    <span className="text-xs text-muted-foreground font-normal mt-1">(Last 7 Days)</span>
                </div>
                <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                        <thead className="bg-muted/10 text-muted-foreground">
                            <tr>
                                <th className="p-2 text-left">Ticker</th>
                                <th className="p-2 text-left">Date</th>
                                <th className="p-2 text-left">Intervals</th>
                                <th className="p-2 text-right">Return</th>
                                <th className="p-2 text-center">NX 1D</th>
                                <th className="p-2 text-center">NX 30m</th>
                            </tr>
                        </thead>
                        <tbody>
                            {sorted.map((row, i) => (
                                <tr
                                    key={i}
                                    className="border-b last:border-0 hover:bg-muted/10 cursor-pointer transition-colors"
                                    onClick={() => onRowClick?.(row, type)}
                                >
                                    <td className="p-2 font-medium">{row.ticker}</td>
                                    <td className="p-2 text-muted-foreground text-xs">
                                        {row.date ? format(parseISO(row.date), 'MM-dd') : '-'}
                                    </td>
                                    <td className="p-2 text-muted-foreground">{row.intervals}</td>
                                    <td className={cn("p-2 text-right font-medium", (row.calculatedReturn ?? 0) >= 0 ? "text-green-500" : "text-red-500")}>
                                        {row.calculatedReturn !== null ? formatPercent(row.calculatedReturn) : '-'}
                                    </td>
                                    <td className={cn("p-2 text-center", row.nx_1d ? "text-green-500" : "text-red-500")}>
                                        {row.nx_1d ? '▲' : '▼'}
                                    </td>
                                    <td className={cn("p-2 text-center", row.nx_30m ? "text-green-500" : "text-red-500")}>
                                        {row.nx_30m ? '▲' : '▼'}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </div>
        );
    };

    return (
        <div className="p-4 md:p-6 h-full overflow-y-auto space-y-6">

            {/* Market Breadth Overview (Combined) */}
            <div className="grid grid-cols-1 xl:grid-cols-2 2xl:grid-cols-4 gap-4 w-full">
                <MarketBreadthChart
                    title="SPX"
                    spxData={spxHistory ?? []}
                    cdBreadth={spxBreadth?.cd_breadth ?? []}
                    mcBreadth={spxBreadth?.mc_breadth ?? []}
                    minDate={oneYearAgo}
                    signals1234={spxSignals1234}
                />
                <MarketBreadthChart
                    title="QQQ"
                    spxData={qqqHistory ?? []}
                    cdBreadth={qqqBreadth?.cd_breadth ?? []}
                    mcBreadth={qqqBreadth?.mc_breadth ?? []}
                    minDate={oneYearAgo}
                    signals1234={qqqSignals1234}
                />
                <MarketBreadthChart
                    title="Dow Jones"
                    spxData={djiHistory ?? []}
                    cdBreadth={djiBreadth?.cd_breadth ?? []}
                    mcBreadth={djiBreadth?.mc_breadth ?? []}
                    minDate={oneYearAgo}
                    signals1234={djiSignals1234}
                />
                <MarketBreadthChart
                    title="IWM"
                    spxData={iwmHistory ?? []}
                    cdBreadth={iwmBreadth?.cd_breadth ?? []}
                    mcBreadth={iwmBreadth?.mc_breadth ?? []}
                    minDate={oneYearAgo}
                    signals1234={iwmSignals1234}
                />
            </div>

            <div className="border-t border-border pt-6"></div>

            {/* 1234 Signals Section */}
            <div>
                <h2 className="text-xl font-bold mb-4">1234 Signals (Top 10)</h2>
                <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
                    {/* Left Column: CD 1234 Table OR Chart for MC Selection */}
                    {selected1234Type === 'bear' && selected1234Row ? (
                        <Fetching1234ChartView
                            row={selected1234Row}
                            type="bear"
                            runId={runId}
                            onClose={() => { setSelected1234Row(null); setSelected1234Type(null); }}
                        />
                    ) : (
                        <Signals1234Table
                            data={cd1234Data ?? []}
                            title="CD 1234 Bullish Signals"
                            type="bull"
                            onRowClick={handle1234RowClick}
                            detailedData={cdDetailedData ?? null}
                        />
                    )}

                    {/* Right Column: MC 1234 Table OR Chart for CD Selection */}
                    {selected1234Type === 'bull' && selected1234Row ? (
                        <Fetching1234ChartView
                            row={selected1234Row}
                            type="bull"
                            runId={runId}
                            onClose={() => { setSelected1234Row(null); setSelected1234Type(null); }}
                        />
                    ) : (
                        <Signals1234Table
                            data={mc1234Data ?? []}
                            title="MC 1234 Bearish Signals"
                            type="bear"
                            onRowClick={handle1234RowClick}
                            detailedData={mcDetailedData ?? null}
                        />
                    )}
                </div>
            </div>

            <div className="border-t border-border pt-6"></div>

            {/* High Return Opportunities */}
            <div>
                <h2 className="text-xl font-bold mb-4">High Return Opportunities (Top 10)</h2>
                <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
                    {/* Left Column: CD Table OR Chart for MC Selection */}
                    {selectedType === 'bear' && selectedRow ? (
                        <FetchingChartView
                            row={selectedRow}
                            type="bear"
                            runId={runId}
                            onClose={() => { setSelectedRow(null); setSelectedType(null); }}
                        />
                    ) : (
                        <TopTable
                            data={bestCD ?? []}
                            title="CD Bullish (Best Intervals)"
                            type="bull"
                            onRowClick={handleRowClick}
                        />
                    )}

                    {/* Right Column: MC Table OR Chart for CD Selection */}
                    {selectedType === 'bull' && selectedRow ? (
                        <FetchingChartView
                            row={selectedRow}
                            type="bull"
                            runId={runId}
                            onClose={() => { setSelectedRow(null); setSelectedType(null); }}
                        />
                    ) : (
                        <TopTable
                            data={bestMC ?? []}
                            title="MC Bearish (Best Intervals)"
                            type="bear"
                            onRowClick={handleRowClick}
                        />
                    )}
                </div>
            </div>
        </div>
    );
};
