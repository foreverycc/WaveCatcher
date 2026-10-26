import { flushSync } from 'react-dom';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MarketLevels, type LevelIndex } from '../components/MarketLevels';
import { indexMarks, type FirstDates } from '../utils/marketBreadth';
import type { ReportFigure } from '../services/api';
import '../index.css';
import './report.css';

const payload = JSON.parse(document.getElementById('report-data')!.textContent!) as {
    figures: ReportFigure[]; start: string; end: string; firstDates?: FirstDates;
};
const LEVELS: Record<1 | 2 | 3, string> = { 1: 'Market Trend', 2: 'Stock Heatmaps', 3: 'Index Cards · Market Breadth / Distributions' };
const DEFAULT_WEIGHTS = { '1h': 1, '2h': 2, '3h': 4, '4h': 8, '1d': 32 };

const indices: LevelIndex[] = payload.figures.map(figure => {
    const card = { ...figure, firstDates: payload.firstDates, offline: true };
    return {
        key: figure.title,
        card,
        group: {
            key: figure.title,
            symbol: figure.indexTicker ?? '',
            tickers: figure.tickers ?? [],
            weights: figure.tickerWeights,
            cdCompanyBreadth: figure.cdCompanyBreadth ?? [],
            mcCompanyBreadth: figure.mcCompanyBreadth ?? [],
            tradingDays: (figure.spxData ?? []).map((d: { time?: string }) => String(d.time ?? '').split('T')[0]).filter(Boolean),
            firstDates: payload.firstDates,
            capHistory: figure.capHistory,
            marks: indexMarks(figure.spxData, figure.signals1234),
        },
    };
});

// The report opens every index's heatmap and card; the levels stay as interactive as in Summary
const client = new QueryClient({ defaultOptions: { queries: { enabled: false, retry: false } } });
flushSync(() => createRoot(document.getElementById('report-levels')!).render(<QueryClientProvider client={client}>
    <MarketLevels
        indices={indices}
        intervalWeights={payload.figures[0]?.intervalWeights ?? DEFAULT_WEIGHTS}
        dateRange={{ start: payload.start, end: payload.end }}
        openAll
        renderLevel={(level, content) => (
            <section id={`level-${level}`} className={`report-level report-level-${level}`}>
                <a className="report-back" href="#report-top">↑ Back to contents</a>
                <h2>Level {level} · {LEVELS[level]}</h2>
                {content}
            </section>
        )}
    />
</QueryClientProvider>));

function followSectionLink() {
    const target = document.getElementById(window.location.hash.slice(1));
    if (!target) return;
    requestAnimationFrame(() => target.scrollIntoView({ block: 'start' }));
}
window.addEventListener('hashchange', followSectionLink);
document.addEventListener('click', event => {
    const link = (event.target as Element).closest('a[href^="#"]');
    if (link && link.getAttribute('href') === window.location.hash) followSectionLink();
});
followSectionLink();
