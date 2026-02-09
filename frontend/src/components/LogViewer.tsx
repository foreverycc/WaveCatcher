import React, { useEffect, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { analysisApi } from '../services/api';
import { Terminal, X } from 'lucide-react';


interface LogViewerProps {
    isOpen: boolean;
    onClose: () => void;
    autoScroll?: boolean;
}

export const LogViewer: React.FC<LogViewerProps> = ({ isOpen, onClose, autoScroll = true }) => {
    const scrollRef = useRef<HTMLDivElement>(null);

    const { data: logsData } = useQuery({
        queryKey: ['logs'],
        queryFn: () => analysisApi.getLogs(100),
        refetchInterval: isOpen ? 2000 : false, // Poll every 2s when open
        enabled: isOpen
    });

    useEffect(() => {
        if (autoScroll && scrollRef.current && logsData?.logs) {
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        }
    }, [logsData, autoScroll]);

    if (!isOpen) return null;

    return (
        <div className="fixed bottom-4 right-4 w-[600px] h-[400px] bg-card border border-border rounded-xl shadow-2xl flex flex-col overflow-hidden z-50 animate-in slide-in-from-bottom-10 fade-in">
            <div className="flex justify-between items-center p-3 border-b border-border bg-muted/50">
                <div className="flex items-center gap-2 text-sm font-semibold">
                    <Terminal className="w-4 h-4" />
                    Backend Logs
                </div>
                <button
                    onClick={onClose}
                    className="p-1 hover:bg-muted rounded-md transition-colors"
                >
                    <X className="w-4 h-4" />
                </button>
            </div>

            <div
                ref={scrollRef}
                className="flex-1 overflow-y-auto p-4 bg-black text-green-400 font-mono text-xs space-y-1"
            >
                {logsData?.logs.length === 0 ? (
                    <div className="text-muted-foreground italic">No logs available...</div>
                ) : (
                    logsData?.logs.map((log, i) => (
                        <div key={i} className="break-all whitespace-pre-wrap">{log}</div>
                    ))
                )}
            </div>
        </div>
    );
};
