import React, { useState, useEffect } from 'react';
import { Maximize2, Minimize2, X } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { analysisApi } from '../services/api';
import { AnalysisTable } from '../components/AnalysisTable';
import { BoxplotChart } from '../components/BoxplotChart';
import { CandleChart } from '../components/CandleChart';
import { OptionOIChart } from '../components/OptionOIChart';
import { OptionAnalysisPanel } from '../components/OptionAnalysisPanel';
import { LogViewer } from '../components/LogViewer';
import { SummaryPanel } from '../components/SummaryPanel';
import { cn } from '../utils/cn';

interface DashboardProps {
    selectedStockList: string;
    showLogs: boolean;
    setShowLogs: (show: boolean) => void;
    dateRange: { start: string; end: string };
}

// Wrapper component to handle individual chart data fetching
export const DetailedChartRow = ({ row, activeSubTab: _activeSubTab }: { row: any, activeSubTab: string }) => {
    const [selectedInterval, setSelectedInterval] = React.useState(row.interval);

    // Reset selected interval when switching rows
    React.useEffect(() => {
        setSelectedInterval(row.interval);
    }, [row.interval]);

    const { data: priceHistory, isLoading } = useQuery({
        queryKey: ['priceHistory', row.ticker, selectedInterval],
        queryFn: () => analysisApi.getPriceHistory(row.ticker, selectedInterval),
        staleTime: 1000 * 60 * 60 * 24, // 24 hours
        enabled: !!row.ticker && !!selectedInterval
    });

    return (
        <div className="flex flex-col space-y-4 p-4 border rounded-lg bg-card/50">
            <div style={{ height: '350px' }}>
                <BoxplotChart
                    selectedRow={row}
                    title={`Returns Distribution - ${row.ticker} (${row.interval})`}
                    subtitle={`Success Rate: ${row.success_rate}% | Avg Return: ${row.avg_return}% | Signal Count: ${row.test_count || row.test_count_0 || 'N/A'}`}
                />
            </div>
            <div style={{ height: '350px' }} className="mt-4 border-t pt-4 border-border/50">
                {isLoading ? (
                    <div className="h-full flex items-center justify-center text-muted-foreground">Loading price history...</div>
                ) : (
                    <CandleChart
                        data={priceHistory || []}
                        ticker={row.ticker}
                        interval={selectedInterval}
                        onIntervalChange={setSelectedInterval}
                    />
                )}
            </div>
        </div>
    );
};

export const InteractiveOptionChart = ({ ticker }: { ticker: string }) => {
    const [priceRange, setPriceRange] = useState<{ min: number, max: number } | undefined>(undefined);

    // Reset range when ticker changes
    useEffect(() => {
        setPriceRange(undefined);
    }, [ticker]);

    return (
        <OptionOIChart
            ticker={ticker}
            priceRange={priceRange}
            onRangeChange={(min, max) => setPriceRange({ min, max })}
        />
    );
};

export const Dashboard: React.FC<DashboardProps> = ({
    selectedStockList,
    showLogs,
    setShowLogs,
    dateRange
}) => {
    const [activeTab, setActiveTab] = useState<'summary' | 'cd' | 'mc' | 'option'>('summary');
    const [activeSubTab, setActiveSubTab] = useState<string>('best_intervals_50');
    const [selectedRow, setSelectedRow] = useState<any>(null);
    const [searchQuery, setSearchQuery] = useState('');
    const [searchInput, setSearchInput] = useState('');

    // Fetch analysis runs
    const { data: runs, isLoading: isLoadingRuns } = useQuery({
        queryKey: ['analysisRuns'],
        queryFn: analysisApi.getRuns,
        refetchInterval: 30000
    });

    // Find latest run for selected stock list OR multi_index run
    const currentRun = React.useMemo(() => {
        if (!runs) return null;
        // First try to find a multi_index run (for summary and breadth)
        const multiIndexRun = runs.find(r => r.stock_list_name === 'multi_index' && r.status === 'completed');
        // Fall back to selected stock list run
        const stockListRun = selectedStockList ? runs.find(r => r.stock_list_name === selectedStockList) : null;
        // Prefer multi_index run if it exists
        return multiIndexRun || stockListRun || null;
    }, [runs, selectedStockList]);

    // Determine result type based on active tabs
    const transformResultType = (tab: string, subTab: string) => {
        // Handle 1234 and 5230 resonance models
        if (subTab === '1234' || subTab === '5230') {
            const prefix = tab === 'cd' ? 'cd_breakout_candidates_summary_' : 'mc_breakout_candidates_summary_';
            return prefix + subTab;
        } else {
            // Handle Best Intervals and Custom Detailed
            const prefix = tab === 'cd' ? 'cd_eval_' : 'mc_eval_';
            return prefix + subTab;
        }
    };

    const currentResultType = React.useMemo(() => {
        return transformResultType(activeTab, activeSubTab);
    }, [activeTab, activeSubTab]);

    // Fetch table data - CONDITIONAL
    // If "custom_detailed", we DO NOT fetch all results automatically. We use search.
    // For other tabs, we fetch all results.
    const isSearchMode = activeSubTab === 'custom_detailed';

    const { data: tableData, isLoading: isLoadingTable } = useQuery({
        queryKey: ['tableData', currentRun?.id, currentResultType, isSearchMode ? searchQuery : 'all'],
        queryFn: () => {
            if (!currentRun) return null;

            if (isSearchMode) {
                // Only fetch if we have a search query
                if (!searchQuery) return [];
                return analysisApi.getResult(currentRun.id, currentResultType, searchQuery.toUpperCase());
            }

            // For standard tabs, fetch all (the API supports "all" logic internally via blob)
            return analysisApi.getResult(currentRun.id, currentResultType);
        },
        enabled: !!currentRun && (!isSearchMode || !!searchQuery),
        retry: 2,
        staleTime: 0 // Always check for fresh data when keys change
    });

    // Filter table data by date
    const filteredTableData = React.useMemo(() => {
        if (!tableData) return [];
        // No filtering for search results (user explicitly asked for them)
        if (isSearchMode) return tableData;

        // Filter valid data
        return tableData.filter((row: any) => {
            // Check latest_signal or date (for 1234/5230 models)
            const dateStr = row.latest_signal || row.date;
            if (!dateStr) return false;

            // Allow string comparison YYYY-MM-DD
            const signalDate = String(dateStr).split(' ')[0]; // Extract YYYY-MM-DD
            return signalDate >= dateRange.start && signalDate <= dateRange.end;
        });
    }, [tableData, dateRange, isSearchMode]);


    // Determine detailed result type for chart data
    const detailedResultType = React.useMemo(() => {
        const prefix = activeTab === 'cd' ? 'cd_eval_custom_detailed' : 'mc_eval_custom_detailed';
        return prefix;
    }, [activeTab]);

    // Targeted query for detailed chart data
    const { data: detailedRowData, isLoading: isLoadingDetails } = useQuery({
        queryKey: ['detailedRowData', currentRun?.id, detailedResultType, selectedRow?.ticker],
        queryFn: () => {
            if (!currentRun || !selectedRow?.ticker) return null;
            return analysisApi.getResult(currentRun.id, detailedResultType, selectedRow.ticker);
        },
        enabled: !!currentRun && !!selectedRow?.ticker
    });

    // Find matching detailed row(s) for the selected row
    const detailedRows = React.useMemo(() => {
        if (!selectedRow || !detailedRowData || detailedRowData.length === 0) return [];

        // Helper to extract best metrics from detailed row
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

        if (activeSubTab === '1234' || activeSubTab === '5230') {
            const intervalsStr = selectedRow.intervals;
            if (!intervalsStr) return [];

            const intervalNumbers = intervalsStr.split(',').map((s: string) => s.trim());
            const suffix = activeSubTab === '1234' ? 'h' : 'm';
            let intervals = intervalNumbers.map((n: string) => n + suffix);

            // Add extra interval (1d for 1234, 1h for 5230)
            const extraInterval = activeSubTab === '1234' ? '1d' : '1h';

            // Explicitly add extra interval if not present (logic: show specific sequence requested)
            // Requested: intervals... then extra
            if (!intervals.includes(extraInterval)) {
                intervals.push(extraInterval);
            }

            const results = intervals.map((interval: any) => {
                const match = detailedRowData.find((d: any) =>
                    d.ticker === selectedRow.ticker && d.interval === interval
                );

                if (match) {
                    const metrics = extractBestMetrics(match);
                    return { ...match, ...metrics };
                }

                // If no match found (especially for extra interval), return dummy for Price Chart
                return {
                    ticker: selectedRow.ticker,
                    interval: interval,
                    success_rate: 0,
                    avg_return: 0,
                    test_count: 0
                };
            });

            return results.filter(Boolean);
        }

        const match = detailedRowData.find((d: any) =>
            d.ticker === selectedRow.ticker && d.interval === selectedRow.interval
        );

        if (match) {
            return [{
                ...match,
                success_rate: selectedRow.success_rate,
                avg_return: selectedRow.avg_return,
                test_count: selectedRow.test_count || selectedRow.test_count_0
            }];
        }
        return [];
    }, [selectedRow, detailedRowData, activeSubTab]);

    const [chartPanelWidth, setChartPanelWidth] = useState(50);
    const [isResizing, setIsResizing] = useState(false);
    const [isChartMaximized, setIsChartMaximized] = useState(false);

    // Reset maximized state when row changes
    useEffect(() => {
        if (!selectedRow) setIsChartMaximized(false);
    }, [selectedRow]);

    const startResizing = React.useCallback(() => {
        setIsResizing(true);
    }, []);

    const stopResizing = React.useCallback(() => {
        setIsResizing(false);
    }, []);

    const resize = React.useCallback((mouseMoveEvent: MouseEvent) => {
        if (isResizing) {
            const container = document.getElementById('dashboard-content-container');
            if (container) {
                const containerRect = container.getBoundingClientRect();
                const newWidthPx = containerRect.right - mouseMoveEvent.clientX;
                const newWidthPercent = (newWidthPx / containerRect.width) * 100;

                if (newWidthPercent >= 20 && newWidthPercent <= 80) {
                    setChartPanelWidth(newWidthPercent);
                }
            }
        }
    }, [isResizing]);

    useEffect(() => {
        window.addEventListener("mousemove", resize);
        window.addEventListener("mouseup", stopResizing);
        return () => {
            window.removeEventListener("mousemove", resize);
            window.removeEventListener("mouseup", stopResizing);
        };
    }, [resize, stopResizing]);

    return (
        <div className="p-4 md:p-6 h-full flex flex-col space-y-4 md:space-y-6">
            <LogViewer isOpen={showLogs} onClose={() => setShowLogs(false)} />

            {/* Main Content */}
            <div className="flex-1 flex flex-col bg-card rounded-xl border border-border shadow-sm overflow-hidden">
                {/* Tabs */}
                <div className="flex border-b border-border overflow-x-auto scrollbar-hide">
                    <button
                        onClick={() => setActiveTab('summary')}
                        className={cn(
                            "px-4 md:px-6 py-3 text-sm font-medium transition-colors relative whitespace-nowrap",
                            activeTab === 'summary'
                                ? "text-primary"
                                : "text-muted-foreground hover:text-foreground"
                        )}
                    >
                        Summary
                        {activeTab === 'summary' && <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary" />}
                    </button>
                    <button
                        onClick={() => setActiveTab('cd')}
                        className={cn(
                            "px-4 md:px-6 py-3 text-sm font-medium transition-colors relative whitespace-nowrap",
                            activeTab === 'cd'
                                ? "text-primary"
                                : "text-muted-foreground hover:text-foreground"
                        )}
                    >
                        CD Analysis (Buy)
                        {activeTab === 'cd' && <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary" />}
                    </button>
                    <button
                        onClick={() => setActiveTab('mc')}
                        className={cn(
                            "px-4 md:px-6 py-3 text-sm font-medium transition-colors relative whitespace-nowrap",
                            activeTab === 'mc'
                                ? "text-primary"
                                : "text-muted-foreground hover:text-foreground"
                        )}
                    >
                        MC Analysis (Sell)
                        {activeTab === 'mc' && <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary" />}
                    </button>
                    <button
                        onClick={() => setActiveTab('option')}
                        className={cn(
                            "px-4 md:px-6 py-3 text-sm font-medium transition-colors relative whitespace-nowrap",
                            activeTab === 'option'
                                ? "text-primary"
                                : "text-muted-foreground hover:text-foreground"
                        )}
                    >
                        Option Analysis
                        {activeTab === 'option' && <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary" />}
                    </button>
                </div>

                {activeTab === 'summary' ? (
                    <SummaryPanel
                        runId={currentRun?.id}
                        onRowClick={(row, type) => {
                            setActiveTab(type === 'bull' ? 'cd' : 'mc');
                            setActiveSubTab('best_intervals_50'); // Summary uses 50-period data
                            setSelectedRow(row);
                        }}
                    />
                ) : activeTab === 'option' ? (
                    <OptionAnalysisPanel />
                ) : (
                    <>
                        {/* Subtabs */}
                        <div className="flex gap-1 border-b border-border overflow-x-auto scrollbar-hide p-1">
                            {[
                                { value: 'best_intervals_50', label: 'Best Intervals (50)' },
                                { value: 'best_intervals_20', label: 'Best Intervals (20)' },
                                { value: 'best_intervals_100', label: 'Best Intervals (100)' },
                                { value: 'good_signals', label: 'High Return Intervals' },
                                { value: 'custom_detailed', label: 'Detailed Results' },
                                { value: '1234', label: '1234 Model' },
                                { value: '5230', label: '5230 Model' },
                            ].map((tab) => (
                                <button
                                    key={tab.value}
                                    onClick={() => {
                                        setActiveSubTab(tab.value);
                                        // Reset selection and search on tab change
                                        setSelectedRow(null);
                                        setSearchQuery('');
                                        setSearchInput('');
                                    }}
                                    className={cn(
                                        "px-3 md:px-4 py-2 text-xs md:text-sm font-medium transition-colors relative whitespace-nowrap rounded-md",
                                        activeSubTab === tab.value
                                            ? "text-primary bg-primary/10"
                                            : "text-muted-foreground hover:text-foreground hover:bg-muted"
                                    )}
                                >
                                    {tab.label}
                                </button>
                            ))}
                        </div>

                        {/* Search Bar for Custom Detailed */}
                        {isSearchMode && (
                            <div className="p-4 border-b border-border flex gap-2">
                                <input
                                    type="text"
                                    placeholder="Search Ticker (e.g. AAPL)"
                                    value={searchInput}
                                    onChange={(e) => setSearchInput(e.target.value)}
                                    onKeyDown={(e) => {
                                        if (e.key === 'Enter') setSearchQuery(searchInput);
                                    }}
                                    className="flex-1 px-4 py-2 rounded-md border border-input bg-background/50 focus:outline-none focus:ring-2 focus:ring-primary/50"
                                />
                                <button
                                    onClick={() => setSearchQuery(searchInput)}
                                    className="px-4 py-2 bg-primary text-primary-foreground rounded-md hover:bg-primary/90 transition-colors"
                                >
                                    Search
                                </button>
                            </div>
                        )}

                        {/* Content Area */}
                        <div id="dashboard-content-container" className="flex-1 flex overflow-hidden relative">
                            {/* Table */}
                            <div
                                className={cn("flex-1 border-r border-border overflow-hidden flex flex-col transition-all duration-300")}
                                style={{
                                    width: selectedRow && window.innerWidth >= 768
                                        ? (isChartMaximized ? '0%' : `${100 - chartPanelWidth}%`)
                                        : (selectedRow ? '0%' : '100%'),
                                    display: (selectedRow && isChartMaximized && window.innerWidth >= 768) ? 'none' : 'flex'
                                }}
                            >
                                {isLoadingTable || isLoadingRuns ? (
                                    <div className="h-full flex items-center justify-center text-muted-foreground">Loading data...</div>
                                ) : filteredTableData && filteredTableData.length > 0 ? (
                                    <AnalysisTable
                                        data={filteredTableData}
                                        onRowClick={setSelectedRow}
                                    />
                                ) : (
                                    <div className="h-full flex flex-col items-center justify-center text-muted-foreground p-4 text-center">
                                        {isSearchMode && !searchQuery ? (
                                            <p>Enter a ticker to search for detailed results</p>
                                        ) : (
                                            <>
                                                <p className="mb-2">No data available for {activeSubTab.replace(/_/g, ' ')}</p>
                                                <p className="text-xs opacity-70">
                                                    Date Range: {dateRange.start} to {dateRange.end} <br />
                                                    Stock List: {selectedStockList || 'None'} <br />
                                                    Latest Run: {currentRun ? new Date(currentRun.timestamp).toLocaleString() : 'Not Found'} <br />
                                                    Status: {currentRun?.status || 'N/A'}
                                                </p>
                                            </>
                                        )}
                                    </div>
                                )}
                            </div>

                            {/* Resizer Handle (Desktop Only) */}
                            {selectedRow && !isChartMaximized && (
                                <div
                                    className="hidden md:flex w-1 bg-border hover:bg-primary/50 cursor-col-resize transition-colors z-10 items-center justify-center"
                                    onMouseDown={startResizing}
                                >
                                    <div className="h-8 w-0.5 bg-muted-foreground/30 rounded-full" />
                                </div>
                            )}

                            {/* Chart / Details Panel */}
                            {selectedRow && (
                                <div
                                    className={cn(
                                        "flex flex-col bg-card overflow-hidden transition-all duration-300 h-full",
                                        // Mobile: Fixed overlay
                                        "fixed inset-0 z-50 md:static md:z-auto"
                                    )}
                                    style={{
                                        width: window.innerWidth >= 768
                                            ? (isChartMaximized ? '100%' : `${chartPanelWidth}%`)
                                            : '100%'
                                    }}
                                >
                                    <div className="p-4 border-b border-border flex justify-between items-center bg-muted/10">
                                        <h3 className="font-semibold truncate pr-2">{selectedRow.ticker} ({selectedRow.interval})</h3>
                                        <div className="flex items-center gap-1">
                                            <button
                                                onClick={() => setIsChartMaximized(!isChartMaximized)}
                                                className="p-2 text-muted-foreground hover:text-foreground rounded-md hover:bg-muted/50 transition-colors hidden md:block"
                                                title={isChartMaximized ? "Restore" : "Maximize"}
                                            >
                                                {isChartMaximized ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
                                            </button>
                                            <button
                                                onClick={() => setSelectedRow(null)}
                                                className="p-2 text-muted-foreground hover:text-foreground rounded-md hover:bg-muted/50 transition-colors"
                                                title="Close"
                                            >
                                                <X className="w-4 h-4" />
                                            </button>
                                        </div>
                                    </div>
                                    <div className="flex-1 p-4 overflow-y-auto bg-background md:bg-transparent">
                                        {/* Returns Distribution Boxplot(s) & Price History */}
                                        {isLoadingDetails ? (
                                            <div className="flex items-center justify-center h-full text-muted-foreground">
                                                Loading detailed analysis...
                                            </div>
                                        ) : detailedRows.length > 0 ? (
                                            <div className="space-y-6">
                                                {detailedRows.map((row: any, index: number) => (
                                                    <DetailedChartRow
                                                        key={`${row.ticker}-${row.interval}-${index}`}
                                                        row={row}
                                                        activeSubTab={activeSubTab}
                                                    />
                                                ))}

                                                {/* Single Option Chart at the bottom */}
                                                <div style={{ height: '350px' }} className="p-4 border rounded-lg bg-card/50">
                                                    <InteractiveOptionChart ticker={selectedRow.ticker} />
                                                </div>
                                            </div>
                                        ) : (
                                            <div className="flex items-center justify-center h-full text-muted-foreground">
                                                No detailed data available for this selection
                                            </div>
                                        )}
                                    </div>
                                </div>
                            )}
                        </div>
                    </>
                )}
            </div>
        </div>
    );
};
