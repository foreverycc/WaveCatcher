"""One daily local-time run while the backend is alive; persisted deduplication."""
import fcntl
import json
import logging
import threading
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.services.report_settings import ROOT, atomic_json, load_settings

logger = logging.getLogger(__name__)
STATE_PATH = ROOT / 'backend/data/schedule_state.json'
LOCK_PATH = ROOT / 'backend/data/scheduler.lock'


def next_occurrence(settings, after):
    zone = ZoneInfo(settings.timezone)
    local = after.astimezone(zone)
    hour, minute = map(int, settings.schedule_time.split(':'))
    for offset in range(3):
        day = local.date() + timedelta(days=offset)
        candidate = datetime(day.year, day.month, day.day, hour, minute, tzinfo=zone)
        # Round-trip normalizes a nonexistent DST time to the next valid time.
        candidate = candidate.astimezone(timezone.utc).astimezone(zone)
        if candidate.astimezone(timezone.utc) > after.astimezone(timezone.utc):
            return candidate
    raise ValueError('Could not determine next scheduled run')


class DailyScheduler:
    def __init__(self):
        self.stop_event = threading.Event()
        self.thread = None
        self.next_run = None
        self.signature = None
        self.last_error = None
        self.lock_file = None

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
        self.lock_file = LOCK_PATH.open('a+')
        try:
            fcntl.flock(self.lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.lock_file.close()
            self.lock_file = None
            logger.warning('Scheduler is already running in another backend process')
            return
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._loop, daemon=True, name='daily-analysis')
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=5)
        if self.lock_file:
            self.lock_file.close()
            self.lock_file = None

    def _loop(self):
        while not self.stop_event.is_set():
            try:
                self.tick(datetime.now(timezone.utc))
            except Exception as exc:
                self.last_error = str(exc)
                logger.exception('Daily schedule failed')
            self.stop_event.wait(10)

    def tick(self, now):
        from app.services.engine import job_manager
        settings = load_settings()
        signature = (settings.schedule_enabled, settings.schedule_time, settings.timezone, tuple(settings.indices))
        if signature != self.signature:
            self.signature = signature
            self.next_run = next_occurrence(settings, now) if settings.schedule_enabled else None
            self.last_error = None
        if not self.next_run or now < self.next_run:
            return
        slot_date = self.next_run.date().isoformat()
        state = json.loads(STATE_PATH.read_text()) if STATE_PATH.exists() else {}
        if state.get('last_date') == slot_date:
            self.next_run = next_occurrence(settings, now)
            return
        current = job_manager.get_current_job()
        if current and current.status in ('pending', 'running'):
            # Wait for the running job, without overlapping or dropping today's run.
            return
        from app.services.index_config import load_index_config
        if not settings.indices or set(settings.indices) - set(load_index_config()):
            raise ValueError('Scheduled indices changed. Update Reports & Schedule settings.')
        # Claim before dispatch; a restart cannot accidentally dispatch the same slot twice.
        state = {'last_date': slot_date, 'status': 'dispatching', 'claimed_at': now.isoformat()}
        atomic_json(STATE_PATH, state)
        try:
            job_id = job_manager.start_multi_index_analysis(settings.indices)
        except Exception:
            # A manual job may have won the race. Release claim and retry later.
            atomic_json(STATE_PATH, {})
            raise
        state.update(status='started', job_id=job_id)
        atomic_json(STATE_PATH, state)
        self.last_error = None
        self.next_run = next_occurrence(settings, now)

    def status(self):
        return {'running': bool(self.thread and self.thread.is_alive()),
                'next_run': self.next_run.isoformat() if self.next_run else None,
                'error': self.last_error}


scheduler = DailyScheduler()
