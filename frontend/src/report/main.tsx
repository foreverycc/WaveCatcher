import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { parseISO } from 'date-fns';
import { IndexSummaryFigures } from '../components/IndexSummaryFigures';
import type { ReportFigure } from '../services/api';
import '../index.css';
import './report.css';

const payload = JSON.parse(document.getElementById('report-data')!.textContent!) as {
    figures: ReportFigure[]; start: string; end: string;
};
const client = new QueryClient({ defaultOptions: { queries: { enabled: false, retry: false } } });
payload.figures.forEach((figure, index) => {
    const element = document.getElementById(`figure-${index}`);
    if (!element) throw new Error(`Missing figure container ${index}`);
    createRoot(element).render(<QueryClientProvider client={client}>
        <IndexSummaryFigures {...figure} minDate={parseISO(payload.start)} maxDate={parseISO(payload.end)} expanded />
    </QueryClientProvider>);
});
