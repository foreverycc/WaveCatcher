import { useEffect, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { analysisApi, reportsApi, type ReportSettings } from '../services/api';
import { RunNowReportButton } from './RunNowReportButton';

export function ReportSettingsPanel() {
    const queryClient = useQueryClient();
    const settings = useQuery({ queryKey: ['reportSettings'], queryFn: reportsApi.getSettings });
    const indices = useQuery({ queryKey: ['reportIndices'], queryFn: analysisApi.getIndices });
    const schedule = useQuery({ queryKey: ['reportSchedule'], queryFn: reportsApi.getSchedule, refetchInterval: 10000 });
    const reports = useQuery({ queryKey: ['reports'], queryFn: reportsApi.list, refetchInterval: 5000 });
    const [form, setForm] = useState<ReportSettings | null>(null);
    const [message, setMessage] = useState('');
    const [saving, setSaving] = useState(false);
    useEffect(() => { if (settings.data) setForm(settings.data); }, [settings.data]);
    const inputClass = 'w-full mt-1 px-3 py-2 rounded border border-input bg-background';

    const save = async () => {
        if (!form) return;
        setSaving(true); setMessage('');
        try {
            const saved = await reportsApi.saveSettings(form);
            queryClient.setQueryData(['reportSettings'], saved);
            setMessage('Saved. New settings apply to the next analysis run.');
            queryClient.invalidateQueries({ queryKey: ['reportSchedule'] });
        } catch (error) { setMessage(reportsApi.errorMessage(error)); }
        finally { setSaving(false); }
    };

    return <section className="bg-card rounded-xl border border-border shadow-sm p-5 space-y-5">
        <div><h3 className="font-semibold text-lg">Reports &amp; Schedule</h3>
            <p className="text-sm text-muted-foreground mt-1">Every completed analysis saves an offline HTML report with Summary charts, Market Breadth, Distribution, 1234 Signals and High Return Opportunities. Open a report to print or save as PDF.</p></div>
        {settings.isError && <p role="alert" className="text-red-500">Could not load report settings.</p>}
        {!form && settings.isLoading && <p>Loading settings…</p>}
        {form && <form className="space-y-4" onSubmit={e => { e.preventDefault(); void save(); }}>
            <label className="block text-sm">Save reports to folder
                <input required className={inputClass} value={form.output_directory} onChange={e => setForm({ ...form, output_directory: e.target.value })} placeholder="/Users/you/Library/CloudStorage/Dropbox/WaveCatcher Reports" />
                <span className="text-xs text-muted-foreground">Absolute path on the computer running the backend. For Dropbox, choose a folder inside your local Dropbox sync directory.</span>
            </label>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <label className="text-sm">Chart lookback (days)<input required type="number" min={7} max={730} className={inputClass} value={form.chart_days} onChange={e => setForm({ ...form, chart_days: Number(e.target.value) })} /></label>
                <label className="text-sm">Signal lookback (days)<input required type="number" min={1} max={365} className={inputClass} value={form.signal_days} onChange={e => setForm({ ...form, signal_days: Number(e.target.value) })} /></label>
            </div>
            <label className="flex items-center gap-2"><input type="checkbox" checked={form.schedule_enabled} onChange={e => setForm({ ...form, schedule_enabled: e.target.checked })} />Run analysis automatically every day</label>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <label className="text-sm">Daily time (24-hour)<input required type="time" className={inputClass} value={form.schedule_time} onChange={e => setForm({ ...form, schedule_time: e.target.value })} /></label>
                <label className="text-sm">Timezone<input required className={inputClass} value={form.timezone} onChange={e => setForm({ ...form, timezone: e.target.value })} /></label>
            </div>
            <fieldset><legend className="text-sm mb-2">Indices for scheduled analysis</legend><div className="flex flex-wrap gap-4">
                {indices.data?.indices.map(index => <label key={index.key} className="text-sm flex items-center gap-2"><input type="checkbox" checked={form.indices.includes(index.key)} onChange={e => setForm({ ...form, indices: e.target.checked ? [...form.indices, index.key] : form.indices.filter(key => key !== index.key) })} />{index.key}</label>)}
            </div></fieldset>
            <p className="text-xs text-muted-foreground">Keep the backend running and the computer awake. The browser may be closed. Runs wait if another analysis is active. Missed times while the backend is stopped are skipped. Daylight saving time follows the selected timezone.</p>
            <button disabled={saving} className="px-4 py-2 bg-primary text-primary-foreground rounded-md disabled:opacity-50">{saving ? 'Saving…' : 'Save report settings'}</button>
            {message && <p role="status" className="text-sm">{message}</p>}
        </form>}
        {settings.data && <div className="border-t pt-4 space-y-2">
            <RunNowReportButton indices={settings.data.indices} />
            <p className="text-xs text-muted-foreground">Uses saved settings. Save any changes above before running.</p>
        </div>}
        <div className="text-sm border-t pt-4">
            <p>Next scheduled run: {schedule.data?.next_run ? `${new Date(schedule.data.next_run).toLocaleString()} (your browser timezone)` : 'Disabled or starting…'}</p>
            {schedule.data && !schedule.data.running && <p className="text-amber-600">Scheduler is not active in this backend process.</p>}
            {schedule.data?.error && <p role="alert" className="text-red-500">{schedule.data.error}</p>}
        </div>
        <div><h4 className="font-medium mb-2">Recent reports</h4>
            {reports.isError && <p className="text-red-500">Could not load reports.</p>}
            {reports.data?.length === 0 && <p className="text-sm text-muted-foreground">Your next analysis will create the first report.</p>}
            <div className="space-y-3 max-h-80 overflow-auto">{reports.data?.map(report => <div className="border rounded-lg p-3 text-sm" key={report.id}>
                <div className="flex flex-wrap gap-3 items-center"><strong>Run #{report.run_id}</strong><span>{new Date(report.created_at).toLocaleString()}</span><span>{report.status}</span>
                    {report.status === 'completed' && <><a className="text-primary underline" href={reportsApi.fileUrl(report.id)} target="_blank" rel="noreferrer">Open report</a><a className="text-primary underline" href={reportsApi.fileUrl(report.id, true)}>Download</a></>}
                    {report.status === 'failed' && <button className="text-primary underline" onClick={async () => { try { await reportsApi.generate(report.run_id); queryClient.invalidateQueries({ queryKey: ['reports'] }); } catch (error) { setMessage(reportsApi.errorMessage(error)); } }}>Retry export</button>}
                </div>
                {report.path && <p className="text-xs text-muted-foreground break-all mt-1">{report.path}</p>}
                {report.error && <p role="alert" className="text-red-500 mt-1">{report.error}</p>}
            </div>)}</div>
        </div>
    </section>;
}
