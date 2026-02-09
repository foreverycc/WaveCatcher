import axios from 'axios';

// Use relative path to leverage Vite proxy (configured in vite.config.ts)
// This ensures requests work correctly whether accessed via localhost or IP address
const API_BASE_URL = `/api`;

export const api = axios.create({
    baseURL: API_BASE_URL,
    headers: {
        'Content-Type': 'application/json',
    },
});

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
}

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
    updateIndices: () => fetch(`${API_BASE_URL}/analysis/update-indices`, { method: 'POST' }).then(res => res.json()),
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

    getSignals1234: async (ticker: string) => {
        const response = await api.get<{ cd_dates: string[], mc_dates: string[] }>(`/analysis/signals_1234/${ticker}`);
        return response.data;
    },

    getMarketBreadth: async (stockList: string) => {
        const response = await api.get<{
            cd_breadth: { date: string, count: number }[],
            mc_breadth: { date: string, count: number }[],
            run_id: number | null
        }>(`/analysis/market_breadth/${encodeURIComponent(stockList)}`);
        return response.data;
    }
};
