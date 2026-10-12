import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { reportsApi, type ReportView } from '../services/api';
import { RunNowReportButton } from './RunNowReportButton';

export function RunReportButton({ runId, indices, view }: { runId?: number; indices: string[]; view: ReportView }) {
    const qc = useQueryClient();
    const reports = useQuery({ queryKey: ['reports'], queryFn: reportsApi.list, refetchInterval: 10000 });
    const report = reports.data?.find(item => item.run_id === runId);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState('');
    return <div className="rounded-lg border bg-card p-3 text-sm flex flex-wrap items-center gap-3">
        <strong>Analysis report</strong>
        <div className="w-full"><RunNowReportButton indices={indices} /></div>
        {report?.status === 'completed' && <><a href={reportsApi.fileUrl(report.id)} target="_blank" rel="noreferrer" className="text-primary underline">Open HTML / Save as PDF</a><a href={reportsApi.fileUrl(report.id, true)} className="text-primary underline">Download</a></>}
        <button disabled={!runId || busy} className="border rounded px-3 py-1 disabled:opacity-50" onClick={async () => {
            if (!runId) return;
            setBusy(true); setError('');
            try { const result = await reportsApi.generate(runId, view); if (result.error) setError(result.error); qc.invalidateQueries({ queryKey: ['reports'] }); }
            catch (err) { setError(reportsApi.errorMessage(err)); }
            finally { setBusy(false); }
        }}>{busy ? 'Exporting…' : 'Export saved results'}</button>
        <span className="text-muted-foreground">Folder and daily schedule: Configuration → Reports &amp; Schedule</span>
        {(error || report?.error) && <p role="alert" className="w-full text-red-500">{error || report?.error}</p>}
    </div>;
}
