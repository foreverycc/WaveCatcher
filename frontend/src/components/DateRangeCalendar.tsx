import React, { useState, useEffect, useRef, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { ChevronLeft, ChevronRight, Calendar } from 'lucide-react';
import {
    format,
    addMonths,
    subMonths,
    startOfMonth,
    endOfMonth,
    startOfWeek,
    endOfWeek,
    isSameMonth,
    isSameDay,
    addDays,
    parseISO,
    isValid,
    isToday
} from 'date-fns';
import { cn } from '../utils/cn';

interface DateRangeCalendarProps {
    startDate: string;
    endDate: string;
    onChange: (range: { start: string; end: string }) => void;
}

// Mini calendar popover for picking a single date
const CalendarPopover = ({
    value,
    onSelect,
    onClose,
    anchorRef
}: {
    value: Date | null;
    onSelect: (date: Date) => void;
    onClose: () => void;
    anchorRef: React.RefObject<HTMLElement | null>;
}) => {
    const [currentMonth, setCurrentMonth] = useState(value || new Date());
    const popoverRef = useRef<HTMLDivElement>(null);
    const [coords, setCoords] = useState({ bottom: -9999, left: -9999 });

    // Calculate position
    useEffect(() => {
        if (anchorRef.current) {
            const rect = anchorRef.current.getBoundingClientRect();
            setCoords({
                bottom: window.innerHeight - rect.top + 4,
                left: rect.left + window.scrollX
            });
        }
    }, [anchorRef]);

    // Close on click outside or escape key
    useEffect(() => {
        const handleClick = (e: MouseEvent) => {
            if (
                popoverRef.current && !popoverRef.current.contains(e.target as Node) &&
                anchorRef.current && !anchorRef.current.contains(e.target as Node)
            ) {
                onClose();
            }
        };
        const handleKeyDown = (e: KeyboardEvent) => {
            if (e.key === 'Escape') onClose();
        };
        document.addEventListener('mousedown', handleClick);
        document.addEventListener('keydown', handleKeyDown);
        return () => {
            document.removeEventListener('mousedown', handleClick);
            document.removeEventListener('keydown', handleKeyDown);
        };
    }, [onClose, anchorRef]);

    const monthStart = startOfMonth(currentMonth);
    const monthEnd = endOfMonth(monthStart);
    const calStart = startOfWeek(monthStart);
    const calEnd = endOfWeek(monthEnd);

    const weeks: Date[][] = [];
    let day = calStart;
    while (day <= calEnd) {
        const week: Date[] = [];
        for (let i = 0; i < 7; i++) {
            week.push(day);
            day = addDays(day, 1);
        }
        weeks.push(week);
    }

    const popoverContent = (
        <div
            ref={popoverRef}
            style={{ bottom: coords.bottom, left: coords.left }}
            className="absolute z-[9999] bg-card border border-border rounded-lg shadow-xl p-3 w-[240px]"
        >
            {/* Header */}
            <div className="flex items-center justify-between mb-2">
                <button
                    onClick={() => setCurrentMonth(subMonths(currentMonth, 1))}
                    className="p-1 hover:bg-muted rounded-full transition-colors"
                >
                    <ChevronLeft className="w-4 h-4 text-muted-foreground" />
                </button>
                <span className="text-sm font-bold text-foreground tracking-wide">
                    {format(currentMonth, 'MMM yyyy').toUpperCase()}
                </span>
                <button
                    onClick={() => setCurrentMonth(addMonths(currentMonth, 1))}
                    className="p-1 hover:bg-muted rounded-full transition-colors"
                >
                    <ChevronRight className="w-4 h-4 text-muted-foreground" />
                </button>
            </div>

            {/* Day headers */}
            <div className="grid grid-cols-7 mb-2">
                {['S', 'M', 'T', 'W', 'T', 'F', 'S'].map((d, i) => (
                    <div key={i} className="text-center text-[10px] font-semibold text-muted-foreground">
                        {d}
                    </div>
                ))}
            </div>

            {/* Date cells */}
            <div className="space-y-1">
                {weeks.map((week, wi) => (
                    <div key={wi} className="grid grid-cols-7 gap-1">
                        {week.map((d, di) => {
                            const inMonth = isSameMonth(d, monthStart);
                            const selected = value && isSameDay(d, value);
                            const today = isToday(d);

                            return (
                                <button
                                    key={di}
                                    onClick={() => {
                                        onSelect(d);
                                        onClose();
                                    }}
                                    className={cn(
                                        "h-8 w-full flex items-center justify-center text-xs rounded-md transition-all",
                                        selected ? "bg-primary text-primary-foreground font-bold shadow-sm" : "hover:bg-muted",
                                        !inMonth && "text-muted-foreground/30",
                                        inMonth && !selected && "text-foreground",
                                        today && !selected && "ring-1 ring-inset ring-red-500 text-red-500 font-semibold"
                                    )}
                                >
                                    {format(d, 'd')}
                                </button>
                            );
                        })}
                    </div>
                ))}
            </div>
        </div>
    );

    return createPortal(popoverContent, document.body);
};

export const DateRangeCalendar: React.FC<DateRangeCalendarProps> = ({
    startDate,
    endDate,
    onChange
}) => {
    const [openPicker, setOpenPicker] = useState<'start' | 'end' | null>(null);
    const startRef = useRef<HTMLButtonElement>(null);
    const endRef = useRef<HTMLButtonElement>(null);

    const parsedStart = startDate ? parseISO(startDate) : null;
    const parsedEnd = endDate ? parseISO(endDate) : null;

    const handleSelectStart = useCallback((date: Date) => {
        onChange({
            start: format(date, 'yyyy-MM-dd'),
            end: endDate || format(date, 'yyyy-MM-dd')
        });
    }, [endDate, onChange]);

    const handleSelectEnd = useCallback((date: Date) => {
        onChange({
            start: startDate || format(date, 'yyyy-MM-dd'),
            end: format(date, 'yyyy-MM-dd')
        });
    }, [startDate, onChange]);

    return (
        <div className="flex items-center gap-2">
            {/* Start Date */}
            <div className="relative flex-1">
                <button
                    ref={startRef}
                    onClick={() => setOpenPicker(openPicker === 'start' ? null : 'start')}
                    className={cn(
                        "w-full flex items-center gap-1.5 px-2.5 py-1.5 rounded-md border text-xs transition-colors",
                        openPicker === 'start'
                            ? "border-primary bg-primary/5 text-foreground"
                            : "border-border bg-card text-foreground hover:bg-muted"
                    )}
                >
                    <Calendar className="w-3 h-3 text-muted-foreground shrink-0" />
                    <span className={parsedStart && isValid(parsedStart) ? "font-medium" : "text-muted-foreground"}>
                        {parsedStart && isValid(parsedStart) ? format(parsedStart, 'MM/dd/yyyy') : 'Start'}
                    </span>
                </button>
                {openPicker === 'start' && (
                    <CalendarPopover
                        value={parsedStart}
                        onSelect={handleSelectStart}
                        onClose={() => setOpenPicker(null)}
                        anchorRef={startRef}
                    />
                )}
            </div>

            <span className="text-xs text-muted-foreground">–</span>

            {/* End Date */}
            <div className="relative flex-1">
                <button
                    ref={endRef}
                    onClick={() => setOpenPicker(openPicker === 'end' ? null : 'end')}
                    className={cn(
                        "w-full flex items-center gap-1.5 px-2.5 py-1.5 rounded-md border text-xs transition-colors",
                        openPicker === 'end'
                            ? "border-primary bg-primary/5 text-foreground"
                            : "border-border bg-card text-foreground hover:bg-muted"
                    )}
                >
                    <Calendar className="w-3 h-3 text-muted-foreground shrink-0" />
                    <span className={parsedEnd && isValid(parsedEnd) ? "font-medium" : "text-muted-foreground"}>
                        {parsedEnd && isValid(parsedEnd) ? format(parsedEnd, 'MM/dd/yyyy') : 'End'}
                    </span>
                </button>
                {openPicker === 'end' && (
                    <CalendarPopover
                        value={parsedEnd}
                        onSelect={handleSelectEnd}
                        onClose={() => setOpenPicker(null)}
                        anchorRef={endRef}
                    />
                )}
            </div>
        </div>
    );
};
