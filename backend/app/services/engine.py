import os
import sys
import threading
import time
import uuid
import logging
from datetime import datetime
from typing import Dict, Optional

# Add logic directory to sys.path to ensure imports work
logic_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../logic"))
if logic_path not in sys.path:
    sys.path.append(logic_path)

from app.logic.stock_analyzer import analyze_stocks

logger = logging.getLogger(__name__)

class AnalysisJob:
    def __init__(self, job_id: str, stock_list_file: str, end_date: Optional[str] = None):
        self.job_id = job_id
        self.stock_list_file = stock_list_file
        self.end_date = end_date
        self.status = "pending"  # pending, running, completed, failed
        self.start_time = None
        self.end_time = None
        self.error = None
        self.progress = 0

class JobManager:
    def __init__(self):
        self.jobs: Dict[str, AnalysisJob] = {}
        self.current_job_id: Optional[str] = None
        self.lock = threading.Lock()

    def start_analysis(self, stock_list_file: str, end_date: Optional[str] = None) -> str:
        with self.lock:
            if self.current_job_id and self.jobs[self.current_job_id].status == "running":
                raise Exception("An analysis is already running")
            
            job_id = datetime.now().strftime("%Y%m%d%H%M%S")
            job = AnalysisJob(job_id, stock_list_file, end_date)
            self.jobs[job_id] = job
            self.current_job_id = job_id
            
            # Start background thread
            thread = threading.Thread(target=self._run_analysis, args=(job_id,))
            thread.daemon = True
            thread.start()
            
            logger.info(f"Started analysis job {job_id} for {stock_list_file}")
            return job_id

    def _run_analysis(self, job_id: str):
        job = self.jobs[job_id]
        
        try:
            job.status = "running"
            job.start_time = datetime.now()
            job.progress = 0
            logger.info(f"Job {job_id}: Status set to running")

            # Define a progress callback
            def update_progress(p):
                job.progress = int(p)

            # We need to pass the absolute path to the data file
            # The stock_analyzer expects the path to the file
            data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../data"))
            file_path = os.path.join(data_dir, job.stock_list_file)

            # Run analysis
            logger.info(f"Job {job_id}: Calling analyze_stocks with file: {file_path}")
            analyze_stocks(file_path, end_date=job.end_date, progress_callback=update_progress)
            
            job.status = "completed"
            job.progress = 100
            job.end_time = datetime.now()
            logger.info(f"Job {job_id}: Completed successfully")
            
        except Exception as e:
            job.status = "failed"
            job.error = str(e)
            job.end_time = datetime.now()
            logger.error(f"Job {job_id}: Failed with error: {e}", exc_info=True)
        finally:
            # The finally block is not strictly necessary here as end_time is set in both try/except
            # but keeping it for consistency if future changes add cleanup logic
            pass 

    def get_job(self, job_id: str) -> Optional[AnalysisJob]:
        return self.jobs.get(job_id)

    def get_current_job(self) -> Optional[AnalysisJob]:
        if self.current_job_id:
            return self.jobs[self.current_job_id]
        return None

job_manager = JobManager()
