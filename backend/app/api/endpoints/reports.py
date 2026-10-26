from pathlib import Path
from datetime import date
from typing import Optional
from pydantic import BaseModel, model_validator

from fastapi import APIRouter, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, JSONResponse, Response

from app.db.database import SessionLocal
from app.db.models import SavedReport, AnalysisRun
from app.services.report_settings import ReportSettings, load_settings, save_settings
from app.services.reports import generate_report, report_dict, load_results
from app.services.summary_data import summary_figures
from app.services.scheduler import scheduler

router = APIRouter()


@router.get('/settings')
def settings():
    return load_settings().model_dump()


@router.put('/settings')
def update_settings(body: ReportSettings):
    try:
        return save_settings(body).model_dump()
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get('/schedule')
def schedule_status():
    return scheduler.status()


@router.get('')
def list_reports():
    with SessionLocal() as db:
        return [report_dict(r) for r in db.query(SavedReport).order_by(SavedReport.created_at.desc()).limit(100)]


class DateRange(BaseModel):
    start: date
    end: date

    @model_validator(mode='after')
    def check_order(self):
        if self.start > self.end:
            raise ValueError('Start date must be before end date')
        return self


class ReportView(BaseModel):
    indices: list[str]
    date_range: DateRange
    breadth_date_range: DateRange


# (run id, run time) -> encoded figures; a completed run's results and snapshot never change
_figures_cache = {}


@router.get('/runs/{run_id}/figures')
def run_figures(run_id: int):
    with SessionLocal() as db:
        run = db.get(AnalysisRun, run_id)
        if not run or run.status != 'completed':
            raise HTTPException(status_code=404, detail='Completed run not found')
        cache_key = (run_id, run.timestamp)  # ids can be reused after a database cleanup
        if cache_key not in _figures_cache:
            try:
                figures = summary_figures(load_results(db, run_id, tables=False))
            except ValueError as exc:
                raise HTTPException(status_code=404, detail=str(exc))
            if len(_figures_cache) >= 4:
                _figures_cache.pop(next(iter(_figures_cache)))
            _figures_cache[cache_key] = JSONResponse(jsonable_encoder(figures)).body
        return Response(_figures_cache[cache_key], media_type='application/json')


@router.post('/runs/{run_id}')
def export_run(run_id: int, view: Optional[ReportView] = None):
    try:
        return generate_report(run_id, view=view.model_dump(mode='json') if view else None)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get('/{report_id}/file')
def report_file(report_id: str, download: bool = False):
    with SessionLocal() as db:
        record = db.get(SavedReport, report_id)
        if not record or record.status != 'completed' or not record.path or not Path(record.path).is_file():
            raise HTTPException(status_code=404, detail='Report file not found')
        return FileResponse(record.path, media_type='text/html', filename=Path(record.path).name,
                            content_disposition_type='attachment' if download else 'inline')
