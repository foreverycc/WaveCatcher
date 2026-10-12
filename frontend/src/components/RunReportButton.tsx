import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { reportsApi, type ReportView } from '../services/api';
import { Download, ExternalLink, FileOutput, Loader2 } from 'lucide-react';

const reportActionClass = 'inline-flex h-9 items-center justify-center gap-2 whitespace-nowrap rounded-md border border-input bg-background px-3 text-sm font-medium text-foreground no-underline transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50';

export function RunReportButton({ runId, view }: { runId?: number; view: ReportView }) {
    const qc = useQueryClient();
    const reports = useQuery({ queryKey: ['reports'], queryFn: reportsApi.list, refetchInterval: 10000 });
    const report = reports.data?.find(item => item.run_id === runId);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState('');
    return <div className="rounded-lg border bg-card p-3 text-sm flex flex-wrap items-center gap-3">
        <strong>Analysis report</strong>
        <div className="flex flex-wrap items-center gap-2">
        {report?.status === 'completed' && <><a href={reportsApi.fileUrl(report.id)} target="_blank" rel="noreferrer" className={reportActionClass}><ExternalLink aria-hidden="true" className="h-4 w-4" />Open HTML / Save as PDF</a><a href={reportsApi.fileUrl(report.id, true)} className={reportActionClass}><Download aria-hidden="true" className="h-4 w-4" />Download</a></>}
        <button type="button" disabled={!runId || busy} className={reportActionClass} onClick={async () => {
            if (!runId) return;
            setBusy(true); setError('');
            try { const result = await reportsApi.generate(runId, view); if (result.error) setError(result.error); qc.invalidateQueries({ queryKey: ['reports'] }); }
            catch (err) { setError(reportsApi.errorMessage(err)); }
            finally { setBusy(false); }
        }}>{busy ? <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin" /> : <FileOutput aria-hidden="true" className="h-4 w-4" />}{busy ? 'Exporting…' : 'Export saved results'}</button>
        </div>
        <span className="text-muted-foreground">Folder and daily schedule: Configuration → Reports &amp; Schedule</span>
        {(error || report?.error) && <p role="alert" className="w-full text-red-500">{error || report?.error}</p>}
    </div>;
}
