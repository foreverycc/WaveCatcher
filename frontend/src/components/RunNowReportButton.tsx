import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Play, Loader2 } from 'lucide-react';
import { analysisApi, reportsApi } from '../services/api';

/** Shared by Summary and Configuration; uses the same job as the sidebar/scheduler. */
export function RunNowReportButton({ indices }: { indices: string[] }) {
    const qc = useQueryClient();
    const job = useQuery({
        queryKey: ['jobStatus'],
        queryFn: analysisApi.getStatus,
        refetchInterval: query => ['pending', 'running'].includes(query.state.data?.status || '') ? 1000 : 10000,
    });
    const start = useMutation({
        mutationFn: () => analysisApi.runMultiIndex(indices),
        onSuccess: status => {
            qc.setQueryData(['jobStatus'], status);
            qc.invalidateQueries({ queryKey: ['analysisRuns'] });
        },
    });
    const active = start.isPending || ['pending', 'running'].includes(job.data?.status || '');
    const unavailable = job.isPending || job.isError;
    const label = start.isPending ? 'Starting…' : active
        ? (job.data?.progress === 100 ? 'Generating report…' : `Analyzing… ${job.data?.progress ?? 0}%`)
        : 'Run now & generate report';
    return <div className="space-y-2">
        <button type="button" disabled={active || unavailable || indices.length === 0}
            onClick={() => start.mutate()}
            className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 font-medium text-primary-foreground disabled:opacity-50">
            {active ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
            {label}
        </button>
        <p className="text-xs text-muted-foreground">
            {indices.length ? `Fresh analysis for ${indices.join(', ')}. Saves a report automatically to your configured folder.` : 'Select at least one index to run.'}
        </p>
        {active && <p role="status" className="text-xs text-muted-foreground">You can leave this page open to follow progress.</p>}
        {job.isError && <p role="alert" className="text-sm text-red-500">Cannot reach the backend. Reconnect before starting a run.</p>}
        {start.isError && <p role="alert" className="text-sm text-red-500">{reportsApi.errorMessage(start.error)}</p>}
        {!active && job.data?.status === 'failed' && <p role="alert" className="text-sm text-red-500">Last analysis failed: {job.data.error}</p>}
        {!active && job.data?.report?.error && <p role="alert" className="text-sm text-red-500">Analysis finished, but the report could not be saved: {job.data.report.error}</p>}
        {!active && job.data?.status === 'completed' && job.data.report?.status === 'completed' && <p role="status" className="text-sm">
            Report saved. <a className="text-primary underline" href={reportsApi.fileUrl(job.data.report.id)} target="_blank" rel="noreferrer">Open report</a>
        </p>}
    </div>;
}
