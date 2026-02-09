import React, { useState, useEffect, useRef } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
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
    eachDayOfInterval,
    isWithinInterval,
    parseISO,
    isValid,
    isBefore,
    isAfter,
    isToday
} from 'date-fns';
import { cn } from '../utils/cn';

interface DateRangeCalendarProps {
    startDate: string;
    endDate: string;
    onChange: (range: { start: string; end: string }) => void;
}

export const DateRangeCalendar: React.FC<DateRangeCalendarProps> = ({
    startDate,
    endDate,
    onChange
}) => {
    const [currentMonth, setCurrentMonth] = useState(new Date());

    // Internal state
    const [selection, setSelection] = useState<{ start: Date | null; end: Date | null }>({
        start: startDate ? parseISO(startDate) : null,
        end: endDate ? parseISO(endDate) : null
    });

    const [dragMode, setDragMode] = useState<'create' | 'start' | 'end' | null>(null);
    const containerRef = useRef<HTMLDivElement>(null);

    // Sync props to state
    useEffect(() => {
        if (startDate && endDate && !dragMode) {
            const s = parseISO(startDate);
            const e = parseISO(endDate);
            if (isValid(s) && isValid(e)) {
                setSelection({ start: s, end: e });
            }
        }
    }, [startDate, endDate, dragMode]);

    // Global mouse up
    useEffect(() => {
        const handleGlobalMouseUp = () => {
            if (dragMode) {
                setDragMode(null);
                // Finalize selection
                if (selection.start && selection.end) {
                    let start = selection.start;
                    let end = selection.end;
                    if (isAfter(start, end)) {
                        [start, end] = [end, start];
                    }
                    onChange({
                        start: format(start, 'yyyy-MM-dd'),
                        end: format(end, 'yyyy-MM-dd')
                    });
                    // Update internal state to normalized
                    setSelection({ start, end });
                }
            }
        };

        if (dragMode) {
            window.addEventListener('mouseup', handleGlobalMouseUp);
        }
        return () => {
            window.removeEventListener('mouseup', handleGlobalMouseUp);
        };
    }, [dragMode, selection, onChange]);


    const handleMouseDown = (day: Date, e: React.MouseEvent) => {
        // Determine mode based on what was clicked
        // If clicking exactly on start or end, enter adjust mode.
        // But if start == end, treat as create/re-select to avoid ambiguity? 
        // User says "drag left one... drag right one". 
        // If start!=end:
        if (selection.start && isSameDay(day, selection.start) && selection.end && !isSameDay(selection.start, selection.end)) {
            setDragMode('start');
            e.stopPropagation();
            return;
        }
        if (selection.end && isSameDay(day, selection.end) && selection.start && !isSameDay(selection.start, selection.end)) {
            setDragMode('end');
            e.stopPropagation();
            return;
        }

        // Default: Create new range
        setDragMode('create');
        setSelection({ start: day, end: day });
    };

    const handleMouseEnter = (day: Date) => {
        if (!dragMode) return;

        if (dragMode === 'create') {
            setSelection(prev => ({ ...prev, end: day }));
        } else if (dragMode === 'start') {
            setSelection(prev => ({ ...prev, start: day }));
        } else if (dragMode === 'end') {
            setSelection(prev => ({ ...prev, end: day }));
        }
    };

    const nextMonth = () => setCurrentMonth(addMonths(currentMonth, 1));
    const prevMonth = () => setCurrentMonth(subMonths(currentMonth, 1));

    const renderHeader = () => {
        return (
            <div className="flex items-center justify-between mb-4 px-2">
                <span className="text-sm font-bold text-foreground">
                    {format(currentMonth, 'MMM yyyy').toUpperCase()}
                </span>
                <div className="flex gap-2">
                    <button onClick={prevMonth} className="p-1 hover:bg-muted rounded-full">
                        <ChevronLeft className="w-4 h-4 text-muted-foreground" />
                    </button>
                    <button onClick={nextMonth} className="p-1 hover:bg-muted rounded-full">
                        <ChevronRight className="w-4 h-4 text-muted-foreground" />
                    </button>
                </div>
            </div>
        );
    };

    const renderDays = () => {
        const days = ['S', 'M', 'T', 'W', 'T', 'F', 'S'];
        return (
            <div className="grid grid-cols-7 mb-2">
                {days.map(day => (
                    <div key={day} className="text-center text-[10px] font-medium text-muted-foreground">
                        {day}
                    </div>
                ))}
            </div>
        );
    };

    const renderCells = () => {
        const monthStart = startOfMonth(currentMonth);
        const monthEnd = endOfMonth(monthStart);
        const startDate = startOfWeek(monthStart);
        const endDate = endOfWeek(monthEnd);

        const dateFormat = "d";
        const rows = [];
        let days = [];
        let day = startDate;
        let formattedDate = "";

        while (day <= endDate) {
            for (let i = 0; i < 7; i++) {
                formattedDate = format(day, dateFormat);
                const cloneDay = day;

                // Normalize selection for display check
                let displayStart = selection.start;
                let displayEnd = selection.end;

                // Visually normalize for "Range" highlighting, but keep identifying logic
                // If sorting strictly for display:
                if (displayStart && displayEnd && isAfter(displayStart, displayEnd)) {
                    [displayStart, displayEnd] = [displayEnd, displayStart];
                }

                const isSelectedStart = displayStart && isSameDay(day, displayStart);
                const isSelectedEnd = displayEnd && isSameDay(day, displayEnd);
                const isInRange = displayStart && displayEnd &&
                    isWithinInterval(day, { start: displayStart, end: displayEnd });

                const isCurrentMonth = isSameMonth(day, monthStart);
                const isDayToday = isToday(day);

                days.push(
                    <div
                        key={day.toString()}
                        className={cn(
                            "relative h-8 w-full flex items-center justify-center text-xs cursor-pointer select-none", // select-none vital for drag
                            // Range Background
                            isInRange && !isSelectedStart && !isSelectedEnd && "bg-primary/20",
                            (isSelectedStart) && "bg-gradient-to-r from-transparent to-primary/20 rounded-l-full",
                            (isSelectedEnd) && "bg-gradient-to-l from-transparent to-primary/20 rounded-r-full",
                            // Start/End circle wrapper overrides background
                            (isSelectedStart || isSelectedEnd) && "before:absolute before:inset-0 before:z-0",
                            // Fix for full rounded if start == end
                            (isSelectedStart && isSelectedEnd) && "rounded-full bg-none"
                        )}
                        onMouseDown={(e) => handleMouseDown(cloneDay, e)}
                        onMouseEnter={() => handleMouseEnter(cloneDay)}
                    >
                        <div className={cn(
                            "z-10 w-7 h-7 flex items-center justify-center rounded-full transition-colors relative",
                            (isSelectedStart || isSelectedEnd) ? "bg-primary text-primary-foreground font-semibold shadow-sm" : "hover:bg-muted",
                            !isCurrentMonth && "text-muted-foreground/30",
                            !isSelectedStart && !isSelectedEnd && isCurrentMonth && "text-foreground",
                            // Today marker: Red ring
                            isDayToday && !isSelectedStart && !isSelectedEnd && "ring-1 ring-red-500 text-red-500 font-semibold"
                        )}>
                            {formattedDate}
                        </div>

                        {/* Connecting strip */}
                        {isSelectedStart && displayEnd && !isSameDay(displayStart, displayEnd) && (
                            <div className="absolute right-0 top-0 bottom-0 w-1/2 bg-primary/20 -z-0" />
                        )}
                        {isSelectedEnd && displayStart && !isSameDay(displayStart, displayEnd) && (
                            <div className="absolute left-0 top-0 bottom-0 w-1/2 bg-primary/20 -z-0" />
                        )}

                    </div>
                );
                day = addDays(day, 1);
            }
            rows.push(
                <div className="grid grid-cols-7" key={day.toString()}>
                    {days}
                </div>
            );
            days = [];
        }
        return <div className="space-y-1">{rows}</div>;
    };

    return (
        <div ref={containerRef} className="bg-card border border-border rounded-xl p-4 shadow-sm select-none">
            {renderHeader()}
            {renderDays()}
            {renderCells()}
        </div>
    );
};
