import React, { useState, useEffect, useRef } from 'react';
import { QueryClient, QueryClientProvider, useQuery, useQueryClient, useMutation } from '@tanstack/react-query';
import { Sidebar } from './components/Sidebar';
import { Dashboard } from './pages/Dashboard';
import { Configuration } from './pages/Configuration';
import { analysisApi, stocksApi } from './services/api';
import { subDays, subYears, format } from 'date-fns';

const queryClient = new QueryClient();

function AppContent() {
  const qc = useQueryClient();
  const [activePage, setActivePage] = useState<'dashboard' | 'configuration'>('dashboard');
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);

  // State lifted from Dashboard
  const [selectedStockList, setSelectedStockList] = useState<string>(() => {
    return localStorage.getItem('selectedStockList') || '';
  });
  const [showLogs, setShowLogs] = useState(false);

  // Multi-index selection state
  const [selectedIndices, setSelectedIndices] = useState<string[]>(() => {
    const stored = localStorage.getItem('selectedIndices');
    return stored ? JSON.parse(stored) : ['SPX', 'QQQ', 'DJI', 'IWM'];
  });

  // Signal Date Range State (default: last 7 days) — for 1234 Signals, High Return, CD/MC tabs
  const [dateRange, setDateRange] = useState<{ start: string; end: string }>({
    start: format(subDays(new Date(), 7), 'yyyy-MM-dd'),
    end: format(new Date(), 'yyyy-MM-dd')
  });

  // Breadth Date Range State (default: last 1 year) — for Market Breadth / Index Summary Cards
  const [breadthDateRange, setBreadthDateRange] = useState<{ start: string; end: string }>({
    start: format(subYears(new Date(), 1), 'yyyy-MM-dd'),
    end: format(new Date(), 'yyyy-MM-dd')
  });

  // Auto-collapse sidebar on mobile
  useEffect(() => {
    const handleResize = () => {
      if (window.innerWidth < 768) {
        setIsSidebarCollapsed(true);
      }
    };

    // Initial check
    handleResize();

    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // Fetch stock lists
  const { data: stockLists } = useQuery({
    queryKey: ['stockFiles'],
    queryFn: stocksApi.list
  });

  // Persist selection
  useEffect(() => {
    if (selectedStockList) {
      localStorage.setItem('selectedStockList', selectedStockList);
    }
  }, [selectedStockList]);

  // Set default stock list (only if nothing selected yet)
  useEffect(() => {
    if (stockLists && stockLists.length > 0 && !selectedStockList) {
      // If we have a stored value that matches the list, use it (handled by init state, but verify specific validity?)
      // For now, init state handles it. If init state was '' (empty storage), proceed to default.
      if (stockLists.includes('00-stocks_hot.tab')) {
        setSelectedStockList('00-stocks_hot.tab');
      } else {
        setSelectedStockList(stockLists[0]);
      }
    }
  }, [stockLists, selectedStockList]);

  // Persist selected indices
  useEffect(() => {
    localStorage.setItem('selectedIndices', JSON.stringify(selectedIndices));
  }, [selectedIndices]);

  // Fetch available indices
  const { data: availableIndices } = useQuery({
    queryKey: ['availableIndices'],
    queryFn: async () => {
      const data = await analysisApi.getIndices();
      return data.indices;
    },
    staleTime: 1000 * 30  // 30s — refreshes after config page changes
  });

  // Fetch job status
  const { data: jobStatus, refetch: refetchStatus } = useQuery({
    queryKey: ['jobStatus'],
    queryFn: analysisApi.getStatus,
    refetchInterval: (query) => (query.state.data?.status === 'running' ? 1000 : false)
  });

  // Auto-refresh data when job completes (without reloading the page)
  const lastProcessedJobRef = useRef<string | null>(
    localStorage.getItem('lastProcessedJobId')
  );

  useEffect(() => {
    if (jobStatus?.status === 'completed' && jobStatus.job_id) {
      if (lastProcessedJobRef.current !== jobStatus.job_id) {
        console.log("Job completed, invalidating queries for fresh data...");
        lastProcessedJobRef.current = jobStatus.job_id;
        localStorage.setItem('lastProcessedJobId', jobStatus.job_id);
        // Invalidate all queries so React Query re-fetches fresh data
        qc.invalidateQueries();
      }
    }
  }, [jobStatus, qc]);

  // Run analysis mutation

  // Run analysis mutation
  const runAnalysisMutation = useMutation({
    mutationFn: () => analysisApi.run(selectedStockList),
    onSuccess: () => {
      refetchStatus();
    },
    onError: (error) => alert(`Error starting analysis: ${error}`)
  });

  const handleRunAnalysis = () => {
    if (selectedStockList) {
      runAnalysisMutation.mutate();
    }
  };

  // Run multi-index analysis mutation
  const runMultiIndexMutation = useMutation({
    mutationFn: () => analysisApi.runMultiIndex(selectedIndices),
    onSuccess: () => {
      refetchStatus();
    },
    onError: (error) => alert(`Error starting multi-index analysis: ${error}`)
  });

  const handleRunMultiIndexAnalysis = () => {
    if (selectedIndices.length > 0) {
      runMultiIndexMutation.mutate();
    }
  };

  // Fetch analysis runs to derive latest update time
  const { data: runs } = useQuery({
    queryKey: ['analysisRuns'],
    queryFn: analysisApi.getRuns,
    refetchInterval: 30000
  });

  const latestUpdate = {
    timestamp: runs?.find(r => r.stock_list_name === selectedStockList)?.timestamp
      ? new Date(runs.find(r => r.stock_list_name === selectedStockList)!.timestamp).getTime() / 1000
      : null
  };

  return (
    <div className="flex h-screen bg-background text-foreground overflow-hidden">
      <Sidebar
        activePage={activePage}
        onNavigate={setActivePage}
        isCollapsed={isSidebarCollapsed}
        onToggle={() => setIsSidebarCollapsed(!isSidebarCollapsed)}

        // Analysis control props
        jobStatus={jobStatus}
        latestUpdate={latestUpdate}
        showLogs={showLogs}
        setShowLogs={setShowLogs}
        dateRange={dateRange}
        setDateRange={setDateRange}
        breadthDateRange={breadthDateRange}
        setBreadthDateRange={setBreadthDateRange}

        // Multi-index props
        availableIndices={availableIndices}
        selectedIndices={selectedIndices}
        setSelectedIndices={setSelectedIndices}
        handleRunMultiIndexAnalysis={handleRunMultiIndexAnalysis}
      />

      <main className="flex-1 overflow-auto bg-secondary/30 flex flex-col">
        {activePage === 'dashboard' ? (
          <Dashboard
            selectedStockList={selectedStockList}
            showLogs={showLogs}
            setShowLogs={setShowLogs}
            dateRange={dateRange}
            breadthDateRange={breadthDateRange}
            selectedIndices={selectedIndices}
            availableIndices={availableIndices}
          />
        ) : (
          <Configuration />
        )}
      </main>
    </div>
  );
}

class ErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { hasError: boolean; error: Error | null }
> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error('ErrorBoundary caught:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: 40, fontFamily: 'monospace', color: '#ff4444', background: '#111', minHeight: '100vh' }}>
          <h1>⚠️ App Crashed</h1>
          <pre style={{ whiteSpace: 'pre-wrap', marginTop: 20, color: '#ff8888' }}>
            {this.state.error?.message}
          </pre>
          <pre style={{ whiteSpace: 'pre-wrap', marginTop: 10, color: '#888', fontSize: 12 }}>
            {this.state.error?.stack}
          </pre>
          <button
            onClick={() => window.location.reload()}
            style={{ marginTop: 20, padding: '10px 20px', cursor: 'pointer', background: '#333', color: '#fff', border: '1px solid #555', borderRadius: 4 }}
          >
            Reload Page
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ErrorBoundary>
        <AppContent />
      </ErrorBoundary>
    </QueryClientProvider>
  );
}

export default App;
