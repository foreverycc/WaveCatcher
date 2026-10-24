import axios from 'axios';
import type { IndexSummaryCardProps } from '../components/IndexSummaryCard';

export type ReportFigure = Omit<IndexSummaryCardProps, 'minDate' | 'maxDate' | 'staticSummary'>;
export interface ReportView {
    indices: string[];
    date_range: { start: string; end: string };
    breadth_date_range: { start: string; end: string };
}

// Use relative path to leverage Vite proxy (configured in vite.config.ts)
// This ensures requests work correctly whether accessed via localhost or IP address
const API_BASE_URL = `/api`;

export const api = axios.create({
    baseURL: API_BASE_URL,
    headers: {
        'Content-Type': 'application/json',
    },
});

export interface ScoringConfig {
    cd_component_weights: { divergence: number; price_position: number; volume: number };
    mc_component_weights: { divergence: number; price_position: number; volume: number };
    interval_weights: { '1h': number; '2h': number; '3h': number; '4h': number; '1d': number };
    cd_threshold: number;
    mc_threshold: number;
    hq_algorithm: 'breakthrough' | 'high_return' | 'trend_regime';
    hq_high_return: {
        lookback_signals: number;
        lookback_bars: number;
        cd_return_threshold: number;
        mc_return_threshold: number;
    };
    hq_trend_regime: {
        stock_ema: number;
        cd_below_ema_pct: { '1h': number; '2h': number; '3h': number; '4h': number; '1d': number };
        use_market_cd: boolean;
        use_market_mc: boolean;
        market_symbol: string;
        market_ema: number;
        market_max_above_ema_pct: number;
    };
    evaluation: {
        lookback_days: { '1h': number; '2h': number; '3h': number; '4h': number; '1d': number };
        max_signals: number;
        min_samples: number;
        min_excess_return: number;
        min_success_rate: number;
        min_oos_count: number;
        min_prior_signals: number;
    };
}

export interface ScoreDistribution {
    bin_width: number;
    bins: number[];  // lower edge of each score bin
    tickers: number;
    cd: Record<string, number[]>;  // interval -> count per bin
    mc: Record<string, number[]>;
    run_id: number;
    run_timestamp: string | null;
}

export interface QuarterlyFundamentals {
    period_end: string;
    quarter?: string;
    companies?: number;
    revenue: number | null;
    gross_profit: number | null;
    net_income: number | null;
    eps?: number | null;
    eps_up_pct?: number | null;
}

export interface StockList {
    filename: string;
    count: number;
    preview: string[];
    content?: string;
}

export interface JobStatus {
    job_id: string;
    status: 'pending' | 'running' | 'completed' | 'failed';
    progress: number;
    error?: string;
    start_time?: string;
    end_time?: string;
    run_id?: number;
    report?: SavedReport;
}

export interface ReportSettings {
    output_directory: string;
    chart_days: number;
    signal_days: number;
    schedule_enabled: boolean;
    schedule_time: string;
    timezone: string;
    indices: string[];
}

export interface SavedReport {
    id: string;
    run_id: number;
    created_at: string;
    status: string;
    path?: string;
    error?: string;
}

export const reportsApi = {
    getSettings: async () => (await api.get<ReportSettings>('/reports/settings')).data,
    saveSettings: async (settings: ReportSettings) => (await api.put<ReportSettings>('/reports/settings', settings)).data,
    getSchedule: async () => (await api.get<{ running: boolean; next_run: string | null; error: string | null }>('/reports/schedule')).data,
    list: async () => (await api.get<SavedReport[]>('/reports')).data,
    generate: async (runId: number, view?: ReportView) => (await api.post<SavedReport>(`/reports/runs/${runId}`, view)).data,
    figures: async (runId: number) => (await api.get<{ figures: ReportFigure[]; as_of: string }>(`/reports/runs/${runId}/figures`)).data,
    fileUrl: (id: string, download = false) => `/api/reports/${encodeURIComponent(id)}/file?download=${download}`,
    errorMessage: (error: unknown) => {
        if (axios.isAxiosError(error)) {
            const detail = error.response?.data?.detail;
            return typeof detail === 'string' ? detail : error.message;
        }
        return error instanceof Error ? error.message : 'Request failed';
    },
};

export interface AnalysisRun {
    id: number;
    timestamp: string;
    status: string;
    stock_list_name: string;
}

export const stocksApi = {
    list: async () => {
        const response = await api.get<string[]>('/stocks/');
        return response.data;
    },
    get: async (filename: string) => {
        const response = await api.get<StockList>(`/stocks/${filename}`);
        return response.data;
    },
    create: async (name: string, content: string, extension: string = '.tab') => {
        const response = await api.post('/stocks/', { name, content, extension });
        return response.data;
    },
    update: async (filename: string, content: string) => {
        const response = await api.put(`/stocks/${filename}`, { content });
        return response.data;
    },
    delete: async (filename: string) => {
        const response = await api.delete(`/stocks/${filename}`);
        return response.data;
    },
    getWeights: async (filename: string) => {
        const response = await api.get<{ weights: Record<string, number> }>(`/stocks/${filename}/weights`);
        return response.data.weights;
    },
    saveWeights: async (filename: string, weights: Record<string, number>) => {
        const response = await api.put<{ weights: Record<string, number> }>(`/stocks/${filename}/weights`, { weights });
        return response.data.weights;
    },
    fillWeightsByMarketCap: async (filename: string) => {
        const response = await api.post<{ weights: Record<string, number>, missing: string[] }>(`/stocks/${filename}/weights/market_cap`);
        return response.data;
    },
    validateTickers: async (tickers: string[]) => {
        const response = await api.post<{ bad_tickers: string[], good_tickers: string[] }>(
            '/stocks/validate', { tickers }
        );
        return response.data;
    },
};

export const analysisApi = {
    run: async (stock_list_file: string, end_date?: string) => {
        const response = await api.post<JobStatus>('/analysis/run', { stock_list_file, end_date });
        return response.data;
    },
    getStatus: async () => {
        const response = await api.get<JobStatus | null>('/analysis/status/current');
        return response.data;
    },
    getRuns: async () => {
        const response = await api.get<AnalysisRun[]>('/analysis/runs');
        return response.data;
    },
    updateIndices: (indices?: string[]) => {
        const body = indices && indices.length > 0 ? { indices } : {};
        return fetch(`${API_BASE_URL}/analysis/update-indices`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        }).then(res => res.json());
    },
    getResult: async (runId: number, resultType: string, ticker?: string) => {
        const response = await api.get<any[]>(`/analysis/runs/${runId}/results/${resultType}`, {
            params: { ticker }
        });
        return response.data;
    },
    getLogs: async (lines: number = 50) => {
        const response = await api.get<{ logs: string[] }>('/analysis/logs', { params: { lines } });
        return response.data;
    },
    getPriceHistory: async (ticker: string, interval: string) => {
        const response = await api.get<any[]>(`/analysis/price_history/${ticker}/${interval}`);
        return response.data;
    },

    getOptions: async (ticker: string) => {
        const response = await axios.get(`${API_BASE_URL}/analysis/options/${ticker}`);
        return response.data;
    },

    getSignals1234: async (ticker: string, stockList?: string) => {
        const response = await api.get<{ cd_dates: string[], mc_dates: string[] }>(`/analysis/signals_1234/${ticker}`,
            stockList ? { params: { stock_list: stockList } } : undefined);
        return response.data;
    },

    getTickerSignals: async (ticker: string) => {
        const response = await api.get<{
            cd_breadth: { date: string, count_1h: number, count_2h: number, count_3h: number, count_4h: number, count_1d: number }[],
            mc_breadth: { date: string, count_1h: number, count_2h: number, count_3h: number, count_4h: number, count_1d: number }[],
            cd_signal_breadth: { date: string, count_1h: number, count_2h: number, count_3h: number, count_4h: number, count_1d: number }[],
            mc_signal_breadth: { date: string, count_1h: number, count_2h: number, count_3h: number, count_4h: number, count_1d: number }[],
            cd_score_breadth: { date: string, score_1h: number, score_2h: number, score_3h: number, score_4h: number, score_1d: number, total_score: number }[],
            mc_score_breadth: { date: string, score_1h: number, score_2h: number, score_3h: number, score_4h: number, score_1d: number, total_score: number }[],
            cd_breakthrough_score_breadth: { date: string, score_1h: number, score_2h: number, score_3h: number, score_4h: number, score_1d: number, total_score: number }[],
            mc_breakthrough_score_breadth: { date: string, score_1h: number, score_2h: number, score_3h: number, score_4h: number, score_1d: number, total_score: number }[],
            cd_company_breadth?: { date: string, count: number, tickers?: string[], scores?: Record<string, Record<string, number>> }[],
            mc_company_breadth?: { date: string, count: number, tickers?: string[], scores?: Record<string, Record<string, number>> }[],
        }>(`/analysis/ticker_signals/${ticker}`);
        return response.data;
    },

    getFundamentals: async (ticker: string) => {
        const response = await api.get<QuarterlyFundamentals[]>(`/analysis/fundamentals/${ticker}`);
        return response.data;
    },

    getFundamentalsAggregate: async (tickers: string[]) => {
        const response = await api.post<QuarterlyFundamentals[]>('/analysis/fundamentals/aggregate', { tickers });
        return response.data;
    },

    getMarketBreadth: async (stockList: string) => {
        const response = await api.get<{
            cd_breadth: { date: string, count_1h: number, count_2h: number, count_3h: number, count_4h: number, count_1d: number }[],
            mc_breadth: { date: string, count_1h: number, count_2h: number, count_3h: number, count_4h: number, count_1d: number }[],
            cd_signal_breadth: { date: string, count_1h: number, count_2h: number, count_3h: number, count_4h: number, count_1d: number }[],
            mc_signal_breadth: { date: string, count_1h: number, count_2h: number, count_3h: number, count_4h: number, count_1d: number }[],
            cd_score_breadth: { date: string, score_1h: number, score_2h: number, score_3h: number, score_4h: number, score_1d: number, total_score: number }[],
            mc_score_breadth: { date: string, score_1h: number, score_2h: number, score_3h: number, score_4h: number, score_1d: number, total_score: number }[],
            cd_breakthrough_score_breadth: { date: string, score_1h: number, score_2h: number, score_3h: number, score_4h: number, score_1d: number, total_score: number }[],
            mc_breakthrough_score_breadth: { date: string, score_1h: number, score_2h: number, score_3h: number, score_4h: number, score_1d: number, total_score: number }[],
            cd_company_breadth?: { date: string, count: number, tickers?: string[], scores?: Record<string, Record<string, number>> }[],
            mc_company_breadth?: { date: string, count: number, tickers?: string[], scores?: Record<string, Record<string, number>> }[],
            data_quality: { warnings: string[], failed_tickers: string[], total_tickers: number, successful_tickers: number } | null,
            run_id: number | null
        }>(`/analysis/market_breadth/${encodeURIComponent(stockList)}`);
        return response.data;
    },

    getIndices: async () => {
        const response = await api.get<{
            indices: { key: string, symbol: string, stock_list: string, whitelist?: string[], tickers: string[] }[]
        }>('/analysis/indices');
        return response.data;
    },

    upsertIndex: async (key: string, symbol: string, stock_list: string, whitelist?: string[]) => {
        const response = await api.post(`/analysis/indices/${encodeURIComponent(key)}`, { symbol, stock_list, whitelist });
        return response.data;
    },

    deleteIndex: async (key: string) => {
        const response = await api.delete(`/analysis/indices/${encodeURIComponent(key)}`);
        return response.data;
    },

    runMultiIndex: async (indices: string[], end_date?: string) => {
        const response = await api.post<JobStatus>('/analysis/run_multi_index', { indices, end_date });
        return response.data;
    },

    getScoreDistribution: async () => {
        const response = await api.get<ScoreDistribution | null>('/analysis/score_distribution');
        return response.data;
    },

    getScoringConfig: async () => {
        const response = await api.get<ScoringConfig>('/analysis/config/scoring');
        return response.data;
    },

    updateScoringConfig: async (config: Partial<ScoringConfig>) => {
        const response = await api.put<ScoringConfig>('/analysis/config/scoring', config);
        return response.data;
    },

    getScoringConfigDefaults: async () => {
        const response = await api.get<ScoringConfig>('/analysis/config/scoring/defaults');
        return response.data;
    },
    cleanupDatabase: async (tables?: string[]) => {
        const params = tables && tables.length > 0 ? { tables: tables.join(',') } : {};
        const response = await api.delete('/analysis/cleanup-database', { params });
        return response.data;
    },
};
