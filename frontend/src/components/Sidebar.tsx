import React from 'react';
import { LayoutDashboard, Settings, Activity, ChevronLeft, ChevronRight, Play, RefreshCw, Clock, AlertCircle, Terminal } from 'lucide-react';
import { cn } from '../utils/cn';
import { DateRangeCalendar } from './DateRangeCalendar';

interface SidebarProps {
    activePage: 'dashboard' | 'configuration';
    onNavigate: (page: 'dashboard' | 'configuration') => void;
    isCollapsed: boolean;
    onToggle: () => void;

    // Analysis control props
    jobStatus: any;
    latestUpdate: any;
    showLogs: boolean;
    setShowLogs: (show: boolean) => void;
    dateRange?: { start: string; end: string };
    setDateRange?: (range: { start: string; end: string }) => void;

    // Multi-index props
    availableIndices?: { key: string; symbol: string; stock_list: string }[];
    selectedIndices: string[];
    setSelectedIndices: (indices: string[]) => void;
    handleRunMultiIndexAnalysis: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
    activePage,
    onNavigate,
    isCollapsed,
    onToggle,
    jobStatus,
    latestUpdate,
    showLogs,
    setShowLogs,
    dateRange,
    setDateRange,
    availableIndices,
    selectedIndices,
    setSelectedIndices,
    handleRunMultiIndexAnalysis
}) => {
    return (
        <div
            className={cn(
                "bg-card border-r border-border h-screen flex flex-col transition-all duration-300 ease-in-out relative",
                isCollapsed ? "w-20" : "w-72"
            )}
        >
            {/* Toggle Button */}
            <button
                onClick={onToggle}
                className="absolute -right-3 top-9 bg-primary text-primary-foreground rounded-full p-1 shadow-md hover:bg-primary/90 transition-colors z-50"
            >
                {isCollapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
            </button>

            <div className={cn("p-6 border-b border-border flex items-center", isCollapsed ? "justify-center px-2" : "")}>
                <div className="flex items-center gap-2 text-primary overflow-hidden whitespace-nowrap">
                    <Activity className="w-6 h-6 shrink-0" />
                    <span className={cn("font-bold text-xl transition-opacity duration-300", isCollapsed ? "opacity-0 w-0" : "opacity-100")}>
                        WaveCatcher Pro
                    </span>
                </div>
            </div>

            <nav className="flex-1 p-4 space-y-2 overflow-y-auto">
                <button
                    onClick={() => onNavigate('dashboard')}
                    className={cn(
                        "w-full flex items-center gap-3 px-4 py-3 rounded-lg transition-colors overflow-hidden whitespace-nowrap",
                        activePage === 'dashboard'
                            ? "bg-primary/10 text-primary font-medium"
                            : "text-muted-foreground hover:bg-muted hover:text-foreground",
                        isCollapsed ? "justify-center px-2" : ""
                    )}
                    title={isCollapsed ? "Dashboard" : undefined}
                >
                    <LayoutDashboard className="w-5 h-5 shrink-0" />
                    <span className={cn("transition-opacity duration-300", isCollapsed ? "opacity-0 w-0" : "opacity-100")}>
                        Dashboard
                    </span>
                </button>

                <button
                    onClick={() => onNavigate('configuration')}
                    className={cn(
                        "w-full flex items-center gap-3 px-4 py-3 rounded-lg transition-colors overflow-hidden whitespace-nowrap",
                        activePage === 'configuration'
                            ? "bg-primary/10 text-primary font-medium"
                            : "text-muted-foreground hover:bg-muted hover:text-foreground",
                        isCollapsed ? "justify-center px-2" : ""
                    )}
                    title={isCollapsed ? "Configuration" : undefined}
                >
                    <Settings className="w-5 h-5 shrink-0" />
                    <span className={cn("transition-opacity duration-300", isCollapsed ? "opacity-0 w-0" : "opacity-100")}>
                        Configuration
                    </span>
                </button>

                {/* Separator */}
                <div className="my-4 border-t border-border" />

                {/* Analysis Controls - Only show when expanded or show minimal icons when collapsed */}
                <div className={cn("space-y-4", isCollapsed ? "flex flex-col items-center space-y-4" : "")}>

                    {/* Multi-Index Selector */}
                    {!isCollapsed && availableIndices && (
                        <div className="space-y-2">
                            <label className="text-xs font-medium text-muted-foreground px-1">Market Indices</label>
                            <div className="space-y-1 bg-muted/50 rounded-md p-2">
                                {availableIndices.map(idx => (
                                    <label key={idx.key} className="flex items-center gap-2 cursor-pointer hover:bg-muted rounded px-1 py-0.5">
                                        <input
                                            type="checkbox"
                                            checked={selectedIndices.includes(idx.key)}
                                            onChange={(e) => {
                                                if (e.target.checked) {
                                                    setSelectedIndices([...selectedIndices, idx.key]);
                                                } else {
                                                    setSelectedIndices(selectedIndices.filter(k => k !== idx.key));
                                                }
                                            }}
                                            className="w-3.5 h-3.5 rounded border-input accent-primary"
                                        />
                                        <span className="text-sm">{idx.key}</span>
                                        <span className="text-xs text-muted-foreground">({idx.symbol})</span>
                                    </label>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Run Analysis Button */}
                    {jobStatus?.status === 'running' ? (
                        <div
                            className={cn(
                                "flex items-center gap-3 bg-primary/10 text-primary rounded-lg border border-primary/20 cursor-pointer hover:bg-primary/20 transition-colors",
                                isCollapsed ? "p-2 justify-center" : "px-4 py-3"
                            )}
                            onClick={() => setShowLogs(true)}
                            title="Analysis Running"
                        >
                            <RefreshCw className="w-4 h-4 animate-spin shrink-0" />
                            {!isCollapsed && (
                                <div className="flex flex-col overflow-hidden">
                                    <span className="text-sm font-medium whitespace-nowrap">Running...</span>
                                    <span className="text-xs opacity-80 whitespace-nowrap">{jobStatus.progress}%</span>
                                </div>
                            )}
                        </div>
                    ) : (
                        <button
                            onClick={handleRunMultiIndexAnalysis}
                            disabled={selectedIndices.length === 0}
                            className={cn(
                                "flex items-center gap-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-all shadow-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed",
                                isCollapsed ? "p-3 justify-center" : "w-full px-4 py-3 justify-center"
                            )}
                            title="Run Multi-Index Analysis"
                        >
                            <Play className="w-4 h-4 shrink-0" />
                            {!isCollapsed && <span>Run Analysis</span>}
                        </button>
                    )}

                    {/* Logs Button */}
                    <button
                        onClick={() => setShowLogs(!showLogs)}
                        className={cn(
                            "flex items-center gap-2 bg-secondary text-secondary-foreground rounded-lg hover:bg-secondary/80 transition-all shadow-sm",
                            isCollapsed ? "p-3 justify-center" : "w-full px-4 py-2 justify-center"
                        )}
                        title="View Logs"
                    >
                        <Terminal className="w-4 h-4 shrink-0" />
                        {!isCollapsed && <span className="text-sm">View Logs</span>}
                    </button>

                    {/* Date Range Picker - Moved to bottom */}
                    {!isCollapsed ? (
                        <div className="px-2">
                            <label className="text-xs font-medium text-muted-foreground px-1 mb-2 block">Date Range</label>
                            <DateRangeCalendar
                                startDate={dateRange?.start || ''}
                                endDate={dateRange?.end || ''}
                                onChange={(range) => setDateRange?.(range)}
                            />
                        </div>
                    ) : (
                        <div title={`Range: ${dateRange?.start} - ${dateRange?.end}`} className="w-10 h-10 flex items-center justify-center rounded-lg bg-muted text-muted-foreground">
                            <Clock className="w-4 h-4" />
                        </div>
                    )}

                    {/* Status Indicators */}
                    {!isCollapsed && latestUpdate?.timestamp && (
                        <div className="flex items-center gap-2 text-xs text-muted-foreground px-1">
                            <Clock className="w-3 h-3" />
                            <span>Updated: {(() => {
                                const d = new Date(latestUpdate.timestamp * 1000);
                                const year = d.getFullYear();
                                const month = d.toLocaleString('en-US', { month: 'short' });
                                const day = d.getDate().toString().padStart(2, '0');
                                const time = d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', second: '2-digit', hour12: true }).toLowerCase();
                                return `${year} ${month} ${day} ${time}`;
                            })()}</span>
                        </div>
                    )}

                    {!isCollapsed && jobStatus?.status === 'failed' && (
                        <div className="flex items-center gap-2 text-destructive text-xs font-medium bg-destructive/10 px-3 py-2 rounded-lg border border-destructive/20">
                            <AlertCircle className="w-4 h-4 shrink-0" />
                            <span className="truncate">Failed: {jobStatus.error || 'Error'}</span>
                        </div>
                    )}
                </div>
            </nav>

            <div className="p-4 border-t border-border text-xs text-muted-foreground text-center overflow-hidden whitespace-nowrap">
                <span className={cn("transition-opacity duration-300", isCollapsed ? "opacity-0 hidden" : "opacity-100")}>
                    v1.0.0 Production Ready
                </span>
                {isCollapsed && <span className="text-[10px]">v1.0</span>}
            </div>
        </div>
    );
};
