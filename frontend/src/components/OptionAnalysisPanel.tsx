import React, { useState, useMemo } from 'react';
import { OptionOIChart } from './OptionOIChart';
import { Search, Upload, AlertCircle } from 'lucide-react';
import { cn } from '../utils/cn';

export const OptionAnalysisPanel: React.FC = () => {
    const [mode, setMode] = useState<'live' | 'csv'>('live');
    const [tickerInput, setTickerInput] = useState('');
    const [activeTicker, setActiveTicker] = useState('');

    // CSV Data State
    const [csvData, setCsvData] = useState<any[] | null>(null);
    const [csvMeta, setCsvMeta] = useState<{
        currentPrice?: number;
        maxPain?: number;
        filename?: string;
    }>({});
    const [csvError, setCsvError] = useState<string | null>(null);

    // Filter State
    const [filterMin, setFilterMin] = useState<string>('');
    const [filterMax, setFilterMax] = useState<string>('');

    const handleSearch = () => {
        if (!tickerInput.trim()) return;
        setActiveTicker(tickerInput.toUpperCase());
        setCsvData(null); // Clear CSV if switching to search
    };

    const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;

        const reader = new FileReader();
        reader.onload = (event) => {
            try {
                const text = event.target?.result as string;
                const lines = text.split('\n');
                if (lines.length < 2) throw new Error("File empty or invalid");

                const header = lines[0].toLowerCase();
                const headers = header.split(',').map(h => h.trim());

                // Detection Logic
                const isLongFormat = headers.includes('strike') && headers.includes('open_interest') && (headers.includes('option_type') || headers.includes('type'));

                // Fallback detection for Wide Format
                const colMap = { strike: -1, calls: -1, puts: -1 };
                headers.forEach((h, i) => {
                    if (h.includes('strike')) colMap.strike = i;
                    else if (h.includes('call') || h.includes('call volume') || h.includes('call open interest') || h === 'c') colMap.calls = i;
                    else if (h.includes('put') || h.includes('put volume') || h.includes('put open interest') || h === 'p') colMap.puts = i;
                });
                const isWideFormat = colMap.strike !== -1 && (colMap.calls !== -1 || colMap.puts !== -1);

                if (!isLongFormat && !isWideFormat) {
                    throw new Error("Could not detect valid columns. Need 'Strike' and ('Calls'/'Puts' OR 'Open Interest' + 'Option Type'/'Type').");
                }

                let parsedData: any[] = [];
                let minStrike = Infinity;
                let maxStrike = -Infinity;

                // Helper to split CSV line respecting quotes
                const splitCSV = (str: string) => {
                    const result = [];
                    let current = '';
                    let inQuote = false;
                    for (let i = 0; i < str.length; i++) {
                        const char = str[i];
                        if (char === '"') {
                            inQuote = !inQuote;
                        } else if (char === ',' && !inQuote) {
                            result.push(current);
                            current = '';
                        } else {
                            current += char;
                        }
                    }
                    result.push(current);
                    return result;
                };

                // Helper to clean number string (remove quotes, commas)
                const parseNumber = (val: string) => {
                    if (!val) return NaN;
                    return parseFloat(val.replace(/["',]/g, '').trim());
                };

                if (isLongFormat) {
                    // Long Format Parsing (Aggregation)
                    const strikeIdx = headers.indexOf('strike');
                    const oiIdx = headers.indexOf('open_interest');
                    const typeIdx = headers.indexOf('option_type') !== -1 ? headers.indexOf('option_type') : headers.indexOf('type');

                    const strikeMap: Record<number, { strike: number, calls: number, puts: number }> = {};

                    for (let i = 1; i < lines.length; i++) {
                        const line = lines[i].trim();
                        if (!line) continue;

                        const cols = splitCSV(line);

                        // Safety check
                        if (cols.length < headers.length) continue;

                        const strike = parseNumber(cols[strikeIdx]);
                        const oi = parseNumber(cols[oiIdx]);
                        const type = cols[typeIdx]?.toUpperCase().trim().replace(/["']/g, ''); // Clean quotes from type too

                        if (isNaN(strike) || isNaN(oi)) continue;

                        if (!strikeMap[strike]) strikeMap[strike] = { strike, calls: 0, puts: 0 };

                        if (type && (type.includes('CALL') || type === 'C')) {
                            strikeMap[strike].calls += oi;
                        } else if (type && (type.includes('PUT') || type === 'P')) {
                            strikeMap[strike].puts += oi;
                        }
                    }
                    parsedData = Object.values(strikeMap).sort((a, b) => a.strike - b.strike);
                    if (parsedData.length > 0) {
                        minStrike = parsedData[0].strike;
                        maxStrike = parsedData[parsedData.length - 1].strike;
                    }

                } else {
                    // Wide Format Parsing (Original)
                    for (let i = 1; i < lines.length; i++) {
                        const line = lines[i].trim();
                        if (!line) continue;
                        const cols = splitCSV(line);

                        const strike = parseNumber(cols[colMap.strike]);
                        let calls = colMap.calls !== -1 ? parseNumber(cols[colMap.calls]) : 0;
                        let puts = colMap.puts !== -1 ? parseNumber(cols[colMap.puts]) : 0;

                        if (isNaN(strike)) continue;
                        if (isNaN(calls)) calls = 0;
                        if (isNaN(puts)) puts = 0;

                        parsedData.push({ strike, calls, puts });
                        if (strike < minStrike) minStrike = strike;
                        if (strike > maxStrike) maxStrike = strike;
                    }
                }

                // Frontend Pain Calculation
                const dataWithPain = calculatePain(parsedData);
                const maxPainStrike = calculateMaxPainStrike(dataWithPain);

                setCsvData(dataWithPain);
                setCsvMeta({
                    filename: file.name,
                    maxPain: maxPainStrike,
                    // Try to guess current price? Average? No, leave empty.
                });
                setCsvError(null);

                // Auto-set range?
                // setFilterMin(minStrike.toString());
                // setFilterMax(maxStrike.toString());

            } catch (err: any) {
                setCsvError(err.message);
                setCsvData(null);
            }
        };
        reader.readAsText(file);
    };

    const calculatePain = (data: any[]) => {
        // Clone data
        const newData = data.map(d => ({ ...d }));

        // Brute force pain calculation (N^2), fine for limited options (~hundreds)
        newData.forEach(point => {
            let totalPain = 0;
            newData.forEach(other => {
                // If price expires at 'point.strike'
                // Calls at 'other.strike' < point.strike are ITM. Value = (point - other) * callOI
                if (other.strike < point.strike) {
                    totalPain += (point.strike - other.strike) * other.calls * 100;
                }
                // Puts at 'other.strike' > point.strike are ITM. Value = (other - point) * putOI
                if (other.strike > point.strike) {
                    totalPain += (other.strike - point.strike) * other.puts * 100;
                }
            });
            point.pain = totalPain;
        });
        return newData;
    };

    const calculateMaxPainStrike = (data: any[]) => {
        if (data.length === 0) return 0;
        let minPain = Infinity;
        let strike = 0;
        data.forEach(d => {
            if (d.pain < minPain) {
                minPain = d.pain;
                strike = d.strike;
            }
        });
        return strike;
    };

    const activePriceRange = useMemo(() => {
        const min = filterMin ? parseFloat(filterMin) : undefined;
        const max = filterMax ? parseFloat(filterMax) : undefined;
        if (min !== undefined && max !== undefined) return { min, max };
        return undefined;
    }, [filterMin, filterMax]);

    return (
        <div className="flex flex-col gap-4 p-4 h-full">
            {/* Control Bar */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-center bg-card p-4 rounded-lg border border-border">

                {/* Left: Mode Selection */}
                <div className="flex justify-center md:justify-start">
                    <div className="flex gap-2 bg-muted/30 p-1 rounded-lg">
                        <button
                            onClick={() => setMode('live')}
                            className={cn("px-4 py-2 rounded-md text-sm font-medium transition-colors", mode === 'live' ? "bg-background shadow text-foreground" : "text-muted-foreground hover:text-foreground")}
                        >
                            Live Ticker
                        </button>
                        <button
                            onClick={() => setMode('csv')}
                            className={cn("px-4 py-2 rounded-md text-sm font-medium transition-colors", mode === 'csv' ? "bg-background shadow text-foreground" : "text-muted-foreground hover:text-foreground")}
                        >
                            Import CSV
                        </button>
                    </div>
                </div>

                {/* Center: Input */}
                <div className="flex justify-center w-full">
                    {mode === 'live' && (
                        <div className="flex gap-2 w-full md:w-auto">
                            <input
                                type="text"
                                placeholder="Enter Ticker (e.g. SPY)"
                                value={tickerInput}
                                onChange={(e) => setTickerInput(e.target.value)}
                                onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                                className="px-3 py-2 bg-background border border-input rounded-md text-sm w-full md:w-48 focus:outline-none focus:ring-2 focus:ring-primary/50"
                            />
                            <button onClick={handleSearch} className="px-3 py-2 bg-primary text-primary-foreground rounded-md hover:bg-primary/90">
                                <Search className="w-4 h-4" />
                            </button>
                        </div>
                    )}

                    {mode === 'csv' && (
                        <div className="flex flex-col gap-1 w-full md:w-auto">
                            <div className="flex gap-2 items-center">
                                <label className="cursor-pointer px-4 py-2 bg-muted hover:bg-muted/80 rounded-md text-sm font-medium flex items-center gap-2">
                                    <Upload className="w-4 h-4" />
                                    {csvMeta.filename ? 'Change File' : 'Upload CSV'}
                                    <input type="file" accept=".csv" onChange={handleFileUpload} className="hidden" />
                                </label>
                                {csvMeta.filename && <span className="text-xs text-muted-foreground truncate max-w-[150px]">{csvMeta.filename}</span>}
                            </div>
                            {csvError && <span className="text-xs text-red-500 flex items-center gap-1"><AlertCircle className="w-3 h-3" /> {csvError}</span>}
                        </div>
                    )}
                </div>

                {/* Right: Spacer */}
                <div className="hidden md:block" />

            </div>

            {/* Chart Area */}
            <div className="flex-1 bg-card rounded-lg border border-border p-4 min-h-[500px]">
                {mode === 'live' ? (
                    activeTicker ? (
                        <OptionOIChart
                            ticker={activeTicker}
                            priceRange={activePriceRange}
                            onRangeChange={(min, max) => {
                                setFilterMin(Math.floor(min).toString());
                                setFilterMax(Math.ceil(max).toString());
                            }}
                        />
                    ) : (
                        <div className="h-full flex flex-col items-center justify-center text-muted-foreground opacity-50">
                            <Search className="w-12 h-12 mb-2" />
                            <span>Enter a ticker to view live options analysis</span>
                        </div>
                    )
                ) : (
                    csvData ? (
                        <OptionOIChart
                            data={csvData}
                            maxPain={csvMeta.maxPain}
                            priceRange={activePriceRange}
                            onRangeChange={(min, max) => {
                                setFilterMin(Math.floor(min).toString());
                                setFilterMax(Math.ceil(max).toString());
                            }}
                        />
                    ) : (
                        <div className="h-full flex flex-col items-center justify-center text-muted-foreground opacity-50">
                            <Upload className="w-12 h-12 mb-2" />
                            <span>Upload a CSV file from OptionCharts</span>
                        </div>
                    )
                )}
            </div>
        </div>
    );
};
