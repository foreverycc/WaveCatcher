import React, { useState, useEffect, useRef, useCallback } from 'react';
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

    // Close on click outside
    useEffect(() => {
        const handleClick = (e: MouseEvent) => {
            if (
                popoverRef.current && !popoverRef.current.contains(e.target as Node) &&
                anchorRef.current && !anchorRef.current.contains(e.target as Node)
            ) {
                onClose();
            }
        };
        document.addEventListener('mousedown', handleClick);
        return () => document.removeEventListener('mousedown', handleClick);
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

    return (
        <div
            ref={popoverRef}
            className="absolute top-full left-0 mt-1 z-50 bg-card border border-border rounded-lg shadow-lg p-3 w-[240px]"
        >
            {/* Header */}
            <div className="flex items-center justify-between mb-2">
                <button
                    onClick={() => setCurrentMonth(subMonths(currentMonth, 1))}
                    className="p-1 hover:bg-muted rounded-full"
                >
                    <ChevronLeft className="w-3.5 h-3.5 text-muted-foreground" />
                </button>
                <span className="text-xs font-bold text-foreground">
                    {format(currentMonth, 'MMM yyyy').toUpperCase()}
                </span>
                <button
                    onClick={() => setCurrentMonth(addMonths(currentMonth, 1))}
                    className="p-1 hover:bg-muted rounded-full"
                >
                    <ChevronRight className="w-3.5 h-3.5 text-muted-foreground" />
                </button>
            </div>

            {/* Day headers */}
            <div className="grid grid-cols-7 mb-1">
                {['S', 'M', 'T', 'W', 'T', 'F', 'S'].map((d, i) => (
                    <div key={i} className="text-center text-[10px] font-medium text-muted-foreground">
                        {d}
                    </div>
                ))}
            </div>

            {/* Date cells */}
            <div className="space-y-0.5">
                {weeks.map((week, wi) => (
                    <div key={wi} className="grid grid-cols-7">
                        {week.map((d, di) => {
                            const inMonth = isSameMonth(d, monthStart);
                            const selected = value && isSameDay(d, value);
                            const today = isToday(d);

                            return (
                                <div
                                    key={di}
                                    className={cn(
                                        "h-7 w-full flex items-center justify-center text-xs cursor-pointer rounded-full transition-colors",
                                        selected ? "bg-primary text-primary-foreground font-semibold" : "hover:bg-muted",
                                        !inMonth && "text-muted-foreground/30",
                                        inMonth && !selected && "text-foreground",
                                        today && !selected && "ring-1 ring-red-500 text-red-500 font-semibold"
                                    )}
                                    onClick={() => {
                                        onSelect(d);
                                        onClose();
                                    }}
                                >
                                    {format(d, 'd')}
                                </div>
                            );
                        })}
                    </div>
                ))}
            </div>
        </div>
    );
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
