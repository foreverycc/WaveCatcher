/**
 * Parse data into array - handles:
 * 1. Arrays: [1, 2, 3]
 * 2. Objects: { "0": 1, "1": 2 } (sorted by key)
 * 3. Strings: "[1, 2]" or "{0: 1}" (CSV formats)
 */
export function parseArrayString(str: any): number[] {
    if (str === null || str === undefined) return [];

    // 1. Handle arrays (JSON direct)
    if (Array.isArray(str)) {
        return str.map(n => {
            if (n === null || n === undefined) return NaN;
            return Number(n);
        }).filter(n => !isNaN(n));
    }

    // 2. Handle objects (JSON dicts like price_history)
    if (typeof str === 'object') {
        // Sort by integer keys to ensure correct order
        const entries = Object.entries(str)
            .map(([k, v]) => [parseInt(k), v] as [number, any])
            .filter(([k]) => !isNaN(k))
            .sort((a, b) => a[0] - b[0]);

        return entries.map(([_, v]) => {
            if (v === null || v === undefined) return NaN;
            return Number(v);
        }).filter(n => !isNaN(n));
    }

    // 3. Handle strings (CSV legacy)
    if (typeof str === 'string') {
        try {
            const cleaned = str.trim();
            if (!cleaned) return [];

            // Handle Python dict format: {0: 1.5, 1: 2.3, ...}
            if (cleaned.startsWith('{')) {
                const dictMatch = cleaned.match(/\{([^}]+)\}/);
                if (!dictMatch) return [];
                const entries = dictMatch[1].split(',').map(entry => {
                    const parts = entry.split(':');
                    if (parts.length !== 2) return NaN;
                    return parseFloat(parts[1].trim());
                });
                return entries.filter(n => !isNaN(n));
            }

            // Handle array format: [1.5, 2.3, ...]
            const arrayMatch = cleaned.replace(/[\[\]]/g, '').trim();
            if (!arrayMatch) return [];
            return arrayMatch.split(',').map(s => parseFloat(s.trim())).filter(n => !isNaN(n));
        } catch {
            return [];
        }
    }

    return [];
}

/**
 * Calculate boxplot statistics for an array of values
 * Uses the "Median of lower/upper halves" method (excluding median if n is odd)
 * This matches the user's requirement:
 * n=2 {a,b}: Median=(a+b)/2, Q1=a, Q3=b
 * n=3 {a,b,c}: Median=b, Q1=a, Q3=c
 */
export function calculateBoxplotStats(values: number[]) {
    if (values.length === 0) return null;

    const sorted = [...values].sort((a, b) => a - b);
    const n = sorted.length;

    const min = sorted[0];
    const max = sorted[n - 1];

    // Helper to calculate median of an array
    const getMedian = (arr: number[]) => {
        if (arr.length === 0) return 0;
        const mid = Math.floor(arr.length / 2);
        if (arr.length % 2 === 0) {
            return (arr[mid - 1] + arr[mid]) / 2;
        } else {
            return arr[mid];
        }
    };

    const median = getMedian(sorted);

    let lowerHalf: number[] = [];
    let upperHalf: number[] = [];

    if (n % 2 === 0) {
        // Even: Split down the middle
        lowerHalf = sorted.slice(0, n / 2);
        upperHalf = sorted.slice(n / 2);
    } else {
        // Odd: Exclude the median
        const midIndex = Math.floor(n / 2);
        lowerHalf = sorted.slice(0, midIndex);
        upperHalf = sorted.slice(midIndex + 1);
    }

    const q1 = getMedian(lowerHalf);
    const q3 = getMedian(upperHalf);

    return {
        min,
        q1,
        median,
        q3,
        max,
        count: n
    };
}

/**
 * Process row data from custom_detailed CSV into boxplot format
 * Input: Selected row object with returns_N, volumes_N, price_history, volume_history columns
 * Output: Array of boxplot data per period
 */
export function processRowDataForChart(rowData: any, maxPeriod: number = 100) {
    const chartData = [];

    // Check if this is a detailed file (has returns_0 column)
    if (!('returns_0' in rowData)) {
        console.log('Not a detailed file, returning empty array');
        return [];
    }

    for (let period = 0; period <= maxPeriod; period++) {
        const returnsKey = `returns_${period}`;
        const volumesKey = `volumes_${period}`;
        const avgVolumeKey = `avg_volume_${period}`;

        // Skip if this period doesn't have data
        if (!(returnsKey in rowData)) break;

        // Parse historical returns and volumes for this period
        const returns = parseArrayString(rowData[returnsKey]);
        const volumes = parseArrayString(rowData[volumesKey]);

        if (returns.length === 0) continue;

        // Calculate boxplot stats from historical data only
        const stats = calculateBoxplotStats(returns);
        const avgVolume = rowData[avgVolumeKey] || (volumes.reduce((a, b) => a + b, 0) / volumes.length);

        chartData.push({
            period,
            ...stats,
            avgVolume: Math.round(avgVolume)
        });
    }

    console.log(`processRowDataForChart: processed ${chartData.length} periods`);
    return chartData;
}

/**
 * Extract current signal trajectory from row data
 */
export function extractCurrentTrajectory(rowData: any) {
    const priceHistory = parseArrayString(rowData.price_history);
    const volumeHistory = parseArrayString(rowData.volume_history);

    // Calculate returns from price history
    const returns = [];
    if (priceHistory.length > 0) {
        const signalPrice = parseFloat(rowData.latest_signal_price) || priceHistory[0];
        returns.push(0); // Period 0 always returns 0

        for (let i = 1; i < priceHistory.length; i++) {
            const ret = ((priceHistory[i] - signalPrice) / signalPrice) * 100;
            returns.push(ret);
        }
    }

    return {
        returns,
        volumes: volumeHistory
    };
}
// ... (previous content)

/**
 * Format large numbers with K/M/B suffixes
 * e.g. 1500 -> 1.5k, 2500000 -> 2.5m
 */
export function formatNumberShort(value: number, decimals: number = 1): string {
    if (value === 0) return '0';

    const absVal = Math.abs(value);

    // Billion
    if (absVal >= 1.0e+9) {
        return (value / 1.0e+9).toFixed(decimals) + 'b';
    }

    // Million
    if (absVal >= 1.0e+6) {
        return (value / 1.0e+6).toFixed(decimals) + 'm';
    }

    // Thousand
    if (absVal >= 1.0e+3) {
        return (value / 1.0e+3).toFixed(decimals) + 'k';
    }

    // Default
    return value.toLocaleString(undefined, { maximumFractionDigits: decimals });
}
