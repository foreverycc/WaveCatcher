"""Self-contained HTML reports: no browser, CDN, or live data request required."""
import html
import json
import subprocess
import threading
import math
import os
import statistics
import tempfile
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

from app.db.database import SessionLocal
from app.db.models import AnalysisRun, AnalysisResult, SavedReport
from app.services.report_settings import load_settings, ROOT
from app.services.summary_data import summary_figures

INTERVALS = ['1h', '2h', '3h', '4h', '1d']
COLORS = ['#079669', '#dc5263', '#437be2']
METRICS = [
    ('CD/MC', 'signal_breadth_by_interval', 'count', False),
    ('CD/MC Score', 'score_breadth_by_interval', 'score', False),
    ('CD/MC HQ', 'market_breadth_1234', 'count', True),
    ('CD/MC HQ Score', 'breakthrough_score_by_interval', 'score', True),
]


def esc(value):
    return html.escape(str(value), quote=True)


def number(value):
    try:
        v = float(value)
        return v if math.isfinite(v) else 0.0
    except (TypeError, ValueError):
        return 0.0


def fmt(value):
    return f'{number(value):,.2f}'


def top_rows(results, side, kind, allowed, start, end):
    rows = results.get((f'{side}_{kind}', 'ALL'), [])
    field = 'date' if '1234' in kind else 'latest_signal'
    filtered = [dict(r) for r in rows if r.get('ticker') in allowed and start <= str(r.get(field, ''))[:10] <= end]
    if field == 'date':
        details = {(r.get('ticker'), r.get('interval')): r for r in results.get((f'{side}_eval_custom_detailed', 'ALL'), [])}
        for r in filtered:
            returns = []
            for interval in str(r.get('intervals') or '').split(','):
                detail = details.get((r['ticker'], interval.strip() + 'h'), {})
                candidates = [(number(detail[f'success_rate_{i}']), number(detail[f'avg_return_{i}'])) for i in range(101) if f'success_rate_{i}' in detail and f'avg_return_{i}' in detail]
                returns.append(max(candidates)[1] if candidates else 0)
            r['avg_return'] = statistics.mean(returns) if returns else 0
    return sorted(filtered, key=lambda r: number(r.get('avg_return')), reverse=side == 'cd')[:10]


def table(title, rows, signal=False):
    fields = [('ticker', 'Ticker'), ('date' if signal else 'latest_signal', 'Date'), ('intervals' if signal else 'interval', 'Intervals'), ('avg_return', 'Return')]
    fields += [('nx_1d', 'NX 1D')] if signal else [('success_rate', 'Win Rate'), ('test_count', 'Count')]
    parts = [f'<article><h3>{esc(title)}</h3><table><thead><tr>' + ''.join(f'<th>{label}</th>' for _, label in fields) + '</tr></thead><tbody>']
    for row in rows:
        parts.append('<tr>')
        for key, _ in fields:
            value = row.get(key, '—')
            if key in ('avg_return', 'success_rate'):
                value = fmt(value) + '%'
            elif key == 'nx_1d':
                value = '▲' if value else '▼'
            parts.append(f'<td>{esc(value)}</td>')
        parts.append('</tr>')
    if not rows:
        parts.append(f'<tr><td colspan="{len(fields)}">No signals in this date range.</td></tr>')
    return ''.join(parts) + '</tbody></table></article>'


_asset_lock = threading.Lock()


def report_assets():
    """Build the shared React renderer when its source changes; never fall back to substitutes."""
    frontend = ROOT / 'frontend'
    output = frontend / 'dist-report'
    with _asset_lock:
        sources = list((frontend / 'src').rglob('*')) + [frontend / 'vite.report.config.ts', frontend / 'tailwind.config.js', frontend / 'package.json']
        newest = max(p.stat().st_mtime for p in sources if p.is_file())
        assets = [output / 'report.js', output / 'report.css']
        if any(not p.exists() or p.stat().st_mtime < newest for p in assets):
            built = subprocess.run(['npm', 'run', 'build:report'], cwd=frontend, capture_output=True, text=True, timeout=180)
            if built.returncode:
                raise RuntimeError('Could not build Summary report renderer: ' + built.stderr[-1500:])
        return assets[0].read_text(), assets[1].read_text()


def load_results(db, run_id):
    required_types = {'report_snapshot', 'data_quality_warnings'}
    for side in ('cd', 'mc'):
        required_types.update(f'{side}_{suffix}' for _, suffix, _, _ in METRICS)
        required_types.update(f'{side}_{suffix}' for suffix in (
            'breakout_candidates_summary_1234', 'eval_good_signals', 'eval_custom_detailed'))
    return {(r.result_type, r.ticker): r.data for r in db.query(AnalysisResult)
            .filter_by(run_id=run_id).filter(AnalysisResult.result_type.in_(required_types))
            .order_by(AnalysisResult.id).all()}


def render_report(run, results, settings, view=None):
    payload = summary_figures(results)
    snapshot = results[('report_snapshot', 'ALL')]
    view = view or {}
    end = date.fromisoformat(snapshot['as_of'][:10])
    chart_range = view.get('breadth_date_range') or {'start': (end - timedelta(days=settings.chart_days)).isoformat(), 'end': end.isoformat()}
    signal_range = view.get('date_range') or {'start': (end - timedelta(days=settings.signal_days)).isoformat(), 'end': end.isoformat()}
    selected = view.get('indices')
    if selected is not None:
        available = {figure['title'] for figure in payload['figures']}
        if not selected or set(selected) - available:
            raise ValueError('The selected indices are not all available in this run. Run analysis for those indices first.')
        payload['figures'] = [figure for figure in payload['figures'] if figure['title'] in selected]
    payload.update(start=chart_range['start'], end=chart_range['end'])
    script, css = report_assets()
    parts = ['<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
             f'<title>WaveCatcher · {esc(end)} · Run {run.id}</title><style>{css}</style></head><body><main class="report-shell">',
             f'<header id="report-top" class="report-header"><div>WAVECATCHER / SUMMARY REPORT</div><h1>Market signals · {esc(end)}</h1><p>Run #{run.id} · {esc(run.stock_list_name)}</p><p>Charts: {esc(chart_range["start"])} – {esc(chart_range["end"])} · Signals: {esc(signal_range["start"])} – {esc(signal_range["end"])}</p><button onclick="window.print()">Print / Save as PDF</button></header>',
             '<noscript>This report requires JavaScript to render the same interactive charts as Summary. Open it in your browser.</noscript>']
    parts.append('<nav class="report-contents" aria-label="Report contents"><h2>Contents</h2><ul>')
    for i, figure in enumerate(payload['figures']):
        parts.append(f'<li><a href="#sector-{i}">{esc(figure["title"])}</a><span><a href="#sector-{i}-breadth">Market Breadth</a> · <a href="#sector-{i}-distribution">Distribution</a></span></li>')
    parts.append('<li><a href="#signals-1234">1234 Signals</a></li><li><a href="#high-return">High Return Opportunities</a></li></ul></nav>')
    quality = results.get(('data_quality_warnings', 'ALL'), {})
    failed = snapshot.get('failed_tickers', [])
    warnings = quality.get('warnings', [])
    if failed or warnings:
        parts.append(f'<p class="report-warning">Data quality: {len(failed)} failed tickers; {len(warnings)} warnings. Failed: {esc(", ".join(failed) or "none")}</p>')
        if warnings:
            parts.append('<details><summary>Data quality details</summary><ul>' + ''.join(f'<li>{esc(w)}</li>' for w in warnings) + '</ul></details>')
    for i, figure in enumerate(payload['figures']):
        parts.append(f'<section id="sector-{i}" class="report-sector"><a class="report-back" href="#report-top">↑ Back to contents</a><h2>{esc(figure["title"])}</h2><div id="figure-{i}"></div></section>')
    allowed = {ticker for figure in payload['figures'] for ticker in figure['tickers']}
    parts.append('<section class="report-tables"><a class="report-back" href="#report-top">↑ Back to contents</a><h2 id="signals-1234">1234 Signals · Top 10</h2><div class="report-table-grid">')
    for side in ['cd', 'mc']:
        parts.append(table(f'{side.upper()} 1234 Signals', top_rows(results, side, 'breakout_candidates_summary_1234', allowed, signal_range['start'], signal_range['end']), True))
    parts.append('</div><a class="report-back" href="#report-top">↑ Back to contents</a><h2 id="high-return">High Return Opportunities · Top 10</h2><div class="report-table-grid">')
    for side in ['cd', 'mc']:
        parts.append(table(f'{side.upper()} High Return Opportunities', top_rows(results, side, 'eval_good_signals', allowed, signal_range['start'], signal_range['end'])))
    parts.append('</div></section><footer class="mt-8 text-sm text-muted-foreground">WaveCatcher · Saved run data, rendered by the Summary tab’s chart components.</footer></main>')
    # Escape '<' to keep untrusted tickers/names from closing the JSON script element.
    serialized = json.dumps(payload, ensure_ascii=False, allow_nan=False).replace('<', '\\u003c')
    parts.append(f'<script type="application/json" id="report-data">{serialized}</script><script>{script}</script></body></html>')
    return ''.join(parts)


def generate_report(run_id, settings=None, view=None):
    settings = settings or load_settings()
    report_id = uuid.uuid4().hex
    with SessionLocal() as db:
        run = db.get(AnalysisRun, run_id)
        if not run or run.status != 'completed':
            raise ValueError('A completed analysis run is required')
        record = SavedReport(id=report_id, run_id=run_id, status='generating')
        db.add(record)
        db.commit()
        temporary = None
        try:
            results = load_results(db, run_id)
            content = render_report(run, results, settings, view)
            folder = Path(settings.output_directory)
            folder.mkdir(parents=True, exist_ok=True)
            filename = f'WaveCatcher_{datetime.utcnow():%Y-%m-%d_%H%M%S}_run-{run_id}_{report_id[:8]}.html'
            destination = folder / filename
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=folder, suffix='.tmp', delete=False) as file:
                temporary = file.name
                file.write(content)
            os.replace(temporary, destination)
            record.status, record.path = 'completed', str(destination)
        except Exception as exc:
            record.status, record.error = 'failed', str(exc)
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)
            db.commit()
        return report_dict(record)


def report_dict(record):
    return {'id': record.id, 'run_id': record.run_id, 'created_at': record.created_at.isoformat() + 'Z',
            'status': record.status, 'path': record.path, 'error': record.error}
