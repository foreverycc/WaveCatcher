"""Offline regression tests; no market downloads or writes to the user's database."""
import tempfile
import json
import re
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.db.models import AnalysisRun, AnalysisResult, SavedReport
from app.services.report_settings import ReportSettings
from app.services import reports, scheduler, engine


def fixture_results():
    return {
        ('report_snapshot', 'ALL'): {
            'as_of': '2026-10-09',
            'indices': [{'key': 'TEST', 'symbol': 'TEST', 'tickers': ['AAA', 'BBB'], 'breadth_key': 'test.tab'}],
            'prices': {'TEST': [{'date': f'2026-10-0{i}', 'close': 100 + i, 'volume': 1000 * i} for i in range(1, 10)]},
            'scoring': {'interval_weights': dict(zip(reports.INTERVALS, [1, 2, 4, 8, 32]))},
            'failed_tickers': ['<script>alert(1)</script>'],
        },
        ('cd_signal_breadth_by_interval', 'test.tab'): [{'date': '2026-10-09', 'count_1h': 2}],
        ('cd_company_breadth', 'test.tab'): [{'date': '2026-10-09', 'count': 1, 'tickers': ['AAA']}],
        ('cd_breakout_candidates_summary_1234', 'ALL'): [
            {'ticker': 'AAA', 'date': '2026-10-09', 'intervals': '1,2', 'nx_1d': True},
            {'ticker': 'WRONG_INDEX', 'date': '2026-10-09', 'intervals': '1'},
            {'ticker': 'BBB', 'date': '2025-01-01', 'intervals': '1'},
        ],
        ('cd_eval_custom_detailed', 'ALL'): [
            {'ticker': 'AAA', 'interval': '1h', 'success_rate_0': 90, 'avg_return_0': 5, 'success_rate_1': 90, 'avg_return_1': 9},
            {'ticker': 'AAA', 'interval': '2h', 'success_rate_0': 80, 'avg_return_0': 3},
        ],
        ('mc_eval_good_signals', 'ALL'): [
            {'ticker': 'AAA', 'latest_signal': '2026-10-09', 'interval': '1d', 'avg_return': -4, 'success_rate': 80, 'test_count': 12},
            {'ticker': 'BBB', 'latest_signal': '2026-10-09', 'interval': '1h', 'avg_return': -10, 'success_rate': 90, 'test_count': 20},
        ],
    }


class ReportTests(unittest.TestCase):
    def test_render_uses_summary_payload_and_embedded_assets(self):
        from app.services.summary_data import summary_figures
        results = fixture_results()
        output = reports.render_report(SimpleNamespace(id=42, stock_list_name='multi_index'), results, ReportSettings())
        encoded = re.search(r'<script type="application/json" id="report-data">(.*?)</script>', output, re.S).group(1)
        payload = json.loads(encoded)
        level_keys = {'cdCompanyBreadth', 'mcCompanyBreadth'}
        self.assertEqual([{k: v for k, v in f.items() if k not in level_keys} for f in payload['figures']], summary_figures(results)['figures'])
        self.assertEqual(payload['figures'][0]['cdCompanyBreadth'], [{'date': '2026-10-09', 'count': 1, 'tickers': ['AAA']}])
        for level in ('level-1', 'level-2', 'level-3'):
            self.assertIn(f'href="#{level}"', output)
        self.assertIn('id="report-levels"', output)
        self.assertNotIn('<script>alert(1)</script>', output)
        self.assertNotRegex(output, r'<script[^>]+src=')
        self.assertNotRegex(output, r'<link[^>]+href=')
        self.assertIn('Market Breadth', output)
        self.assertIn('6.00%', output)
        self.assertNotIn('Summary · Daily close', output)

    def test_prices_include_candles_moving_averages_and_signals(self):
        from app.services.summary_data import summary_figures
        figure = summary_figures(fixture_results())['figures'][0]
        self.assertEqual(figure['cdSignalBreadth'], [{'date': '2026-10-09', 'count_1h': 2}])
        self.assertEqual(figure['intervalWeights']['1d'], 32)
        self.assertEqual(figure['tickers'], ['AAA', 'BBB'])
        self.assertEqual(figure['spxData'][-1]['close'], 109)
        for key in ['time', 'open', 'high', 'low', 'volume', 'ema_20', 'sma_50', 'sma_100', 'sma_200', 'cd_signal', 'mc_signal', 'cd_1234_signal', 'mc_1234_signal']:
            self.assertIn(key, figure['spxData'][-1])

    def test_export_uses_visible_date_ranges_and_rejects_missing_index(self):
        view = {'indices': ['TEST'], 'breadth_date_range': {'start': '2026-10-05', 'end': '2026-10-08'}, 'date_range': {'start': '2026-10-05', 'end': '2026-10-08'}}
        output = reports.render_report(SimpleNamespace(id=42, stock_list_name='multi_index'), fixture_results(), ReportSettings(), view)
        payload = json.loads(re.search(r'<script type="application/json" id="report-data">(.*?)</script>', output, re.S).group(1))
        self.assertEqual((payload['start'], payload['end']), ('2026-10-05', '2026-10-08'))
        self.assertNotIn('6.00%', output)
        view['indices'] = ['MISSING']
        with self.assertRaisesRegex(ValueError, 'not all available'):
            reports.render_report(SimpleNamespace(id=42), fixture_results(), ReportSettings(), view)

    def test_report_embeds_list_data_and_first_dates(self):
        extras = {'firstDates': {'BBB': '2026-10-05'}, 'lists': {'test.tab': {'tickerWeights': {'AAA': 2.0}, 'capHistory': {'dates': [], 'ratios': {}}, 'dmaBreadth': []}}}
        results = fixture_results()
        results[('report_snapshot', 'ALL')]['indices'][0]['stock_list'] = 'test.tab'
        output = reports.render_report(SimpleNamespace(id=42, stock_list_name='multi_index'), results, ReportSettings(), None, extras)
        payload = json.loads(re.search(r'<script type="application/json" id="report-data">(.*?)</script>', output, re.S).group(1))
        self.assertEqual(payload['firstDates'], {'BBB': '2026-10-05'})
        self.assertEqual(payload['figures'][0]['tickerWeights'], {'AAA': 2.0})
        self.assertEqual(payload['figures'][0]['dmaBreadth'], [])

    def test_payload_cannot_close_script_element(self):
        results = fixture_results()
        results[('report_snapshot', 'ALL')]['indices'][0]['key'] = '</script><script>alert(1)</script>'
        output = reports.render_report(SimpleNamespace(id=42, stock_list_name='multi_index'), results, ReportSettings())
        encoded = re.search(r'<script type="application/json" id="report-data">(.*?)</script>', output, re.S).group(1)
        self.assertNotIn('<', encoded)
        self.assertEqual(json.loads(encoded)['figures'][0]['title'], '</script><script>alert(1)</script>')

    def test_tables_match_summary_filters_and_bearish_order(self):
        rows = reports.top_rows(fixture_results(), 'cd', 'breakout_candidates_summary_1234', {'AAA', 'BBB'}, '2026-10-02', '2026-10-09')
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['avg_return'], 6)
        rows = reports.top_rows(fixture_results(), 'mc', 'eval_good_signals', {'AAA', 'BBB'}, '2026-10-02', '2026-10-09')
        self.assertEqual([r['ticker'] for r in rows], ['BBB', 'AAA'])

    def test_file_creation_repeat_export_and_write_failure(self):
        db_engine = create_engine('sqlite://', poolclass=StaticPool)
        Base.metadata.create_all(db_engine)
        sessions = sessionmaker(bind=db_engine)
        with sessions() as db:
            db.add(AnalysisRun(id=42, status='completed', stock_list_name='multi_index'))
            for (kind, ticker), data in fixture_results().items():
                db.add(AnalysisResult(run_id=42, result_type=kind, ticker=ticker, data=data))
            db.commit()
        with tempfile.TemporaryDirectory() as folder, patch.object(reports, 'SessionLocal', sessions):
            settings = ReportSettings(output_directory=folder)
            first = reports.generate_report(42, settings)
            second = reports.generate_report(42, settings)
            self.assertEqual(first['status'], 'completed')
            self.assertNotEqual(first['path'], second['path'])
            self.assertTrue(Path(first['path']).is_file())
            blocked = Path(folder) / 'not-a-folder'
            blocked.write_text('x')
            failure = reports.generate_report(42, ReportSettings(output_directory=str(blocked)))
            self.assertEqual(failure['status'], 'failed')
            self.assertTrue(failure['error'])
            with sessions() as db:
                self.assertEqual(db.get(AnalysisRun, 42).status, 'completed')
                self.assertEqual(db.query(SavedReport).count(), 3)
        db_engine.dispose()

    def test_old_runs_fail_explicitly(self):
        with self.assertRaisesRegex(ValueError, 'no report snapshot'):
            reports.render_report(SimpleNamespace(id=1), {}, ReportSettings())

    def test_job_uses_returned_run_id_for_report(self):
        manager = engine.JobManager()
        job = engine.AnalysisJob('job', 'multi_index', indices=['SPX'])
        manager.jobs['job'] = job
        with patch.object(engine, 'analyze_multi_index', return_value=73), patch.object(reports, 'generate_report', return_value={'status': 'completed'}) as generate:
            manager._run_multi_index_analysis('job')
        generate.assert_called_once_with(73, job.report_settings)
        self.assertEqual(job.status, 'completed')
        self.assertEqual(job.run_id, 73)

    def test_snapshot_retains_membership_and_prices(self):
        import pandas as pd
        from app.services import report_snapshot
        prices = pd.DataFrame({'Open': [10], 'High': [12], 'Low': [9], 'Close': [11], 'Volume': [500]}, index=pd.to_datetime(['2026-10-09']))
        with patch.object(report_snapshot, 'save_analysis_result') as save:
            report_snapshot.save_report_snapshot(42, [{'symbol': 'TEST', 'tickers': ['AAA']}], {'TEST': {'1d': prices}}, '2026-10-09', [])
        snapshot = save.call_args.args[-1]
        self.assertEqual(snapshot['prices']['TEST'][0]['close'], 11)
        self.assertEqual(snapshot['indices'][0]['tickers'], ['AAA'])
        self.assertEqual(snapshot['as_of'], '2026-10-09')

    def test_settings_validation(self):
        for kwargs in [{'schedule_time': '25:00'}, {'timezone': 'Bad/Zone'}, {'output_directory': 'relative'}, {'chart_days': 0}]:
            with self.assertRaises(ValueError):
                ReportSettings(**kwargs)

    def test_no_overlapping_pending_job(self):
        manager = engine.JobManager()
        manager.current_job_id = 'pending'
        manager.jobs['pending'] = SimpleNamespace(status='pending')
        with self.assertRaisesRegex(Exception, 'already running'):
            manager.start_multi_index_analysis(['SPX'])
        with self.assertRaisesRegex(Exception, 'already running'):
            manager.start_analysis('test.tab')

    def test_report_failure_does_not_fail_analysis(self):
        job = SimpleNamespace(run_id=42, report_settings=ReportSettings())
        with patch.object(reports, 'generate_report', side_effect=OSError('disk full')):
            engine.JobManager()._generate_report(job)
        self.assertEqual(job.report['status'], 'failed')
        self.assertEqual(job.report['error'], 'disk full')


class ScheduleTests(unittest.TestCase):
    def test_dst_adjusts_utc_time(self):
        settings = ReportSettings()
        summer = scheduler.next_occurrence(settings, datetime(2026, 10, 10, tzinfo=timezone.utc))
        winter = scheduler.next_occurrence(settings, datetime(2026, 11, 10, tzinfo=timezone.utc))
        self.assertEqual(summer.hour, 13)
        self.assertEqual(winter.hour, 13)
        self.assertEqual(summer.astimezone(timezone.utc).hour, 20)
        self.assertEqual(winter.astimezone(timezone.utc).hour, 21)

    def test_startup_skips_missed_slot(self):
        result = scheduler.next_occurrence(ReportSettings(), datetime(2026, 10, 10, 22, tzinfo=timezone.utc))
        self.assertEqual(result.date().isoformat(), '2026-10-11')

    def test_dst_gap_and_repeated_hour(self):
        result = scheduler.next_occurrence(ReportSettings(schedule_time='02:30'), datetime(2026, 3, 8, 8, tzinfo=timezone.utc))
        self.assertEqual(result.hour, 3)
        result = scheduler.next_occurrence(ReportSettings(schedule_time='01:30'), datetime(2026, 11, 1, 9, tzinfo=timezone.utc))
        self.assertEqual(result.date().isoformat(), '2026-11-02')

    def test_busy_wait_dedup_restart_and_disable(self):
        worker = scheduler.DailyScheduler()
        settings = ReportSettings()
        with tempfile.TemporaryDirectory() as directory, patch.object(scheduler, 'STATE_PATH', Path(directory) / 'state.json'), patch.object(scheduler, 'load_settings', return_value=settings), patch.object(engine, 'job_manager') as manager:
            manager.get_current_job.return_value = None
            manager.start_multi_index_analysis.return_value = 'scheduled-job'
            worker.tick(datetime(2026, 10, 10, 20, 29, tzinfo=timezone.utc))
            manager.get_current_job.return_value = SimpleNamespace(status='running')
            worker.tick(datetime(2026, 10, 10, 20, 30, tzinfo=timezone.utc))
            manager.start_multi_index_analysis.assert_not_called()
            manager.get_current_job.return_value = None
            worker.tick(datetime(2026, 10, 10, 20, 31, tzinfo=timezone.utc))
            worker.tick(datetime(2026, 10, 10, 20, 32, tzinfo=timezone.utc))
            self.assertEqual(manager.start_multi_index_analysis.call_count, 1)
            restarted = scheduler.DailyScheduler()
            restarted.tick(datetime(2026, 10, 10, 20, 29, tzinfo=timezone.utc))
            restarted.tick(datetime(2026, 10, 10, 20, 30, tzinfo=timezone.utc))
            self.assertEqual(manager.start_multi_index_analysis.call_count, 1)
            settings.schedule_enabled = False
            worker.tick(datetime(2026, 10, 11, 20, 31, tzinfo=timezone.utc))
            self.assertIsNone(worker.next_run)


if __name__ == '__main__':
    unittest.main()
