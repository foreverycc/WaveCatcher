# WaveCatcher

WaveCatcher is a full-stack stock signal analysis platform designed to identify market opportunities using advanced models like Waikiki and Resonance. It features a modern React frontend and a robust FastAPI backend.

## 🚀 Features

- **Advanced Signal Analysis**:
  - **CD (抄底)**: Bottom-fishing opportunities with period performance analysis.
  - **MC (卖出)**: Sell signal timing analysis.
- **Multiple Models**:
  - **Waikiki**: Best interval analysis with calculated period returns.
  - **Resonance**: Dynamic breakout pattern detection (1234 and 5230 patterns).
- **Backtesting Support**: Analyze how signals would have performed using historical data up to any specific date.
- **Real-time Data**: Integrated with `yfinance` for global markets and `akshare` for automatic Chinese stock name resolution.
- **Modern UI**: High-performance dashboard featuring interactive charts (Recharts) and professional data grids (ag-grid).

## 🛠 Technology Stack

### Backend
- **Framework**: FastAPI (Python 3.9+)
- **Database**: SQLAlchemy (SQLite for easy setup)
- **Data Fetching**: yfinance, akshare
- **Processing**: pandas, numpy, multiprocess (for parallel analysis)

### Frontend
- **Framework**: React 19 (managed by Vite)
- **Styling**: Tailwind CSS, Framer Motion (for smooth UI transitions)
- **State Management**: TanStack Query (React Query)
- **Visualization**: Recharts, ag-grid-react

## 📦 Getting Started

### Prerequisites
- Python 3.9 or higher
- Node.js 18 or higher
- npm or yarn

### Installation & Setup

#### 1. Backend Setup
```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
python -m app.main
```
The backend server will run at `http://localhost:8000`. You can access the API documentation at `http://localhost:8000/docs`.

#### 2. Frontend Setup
```bash
cd frontend
npm install
npm run dev
```
The frontend application will be available at `http://localhost:5173`.

## 📂 Project Structure

```text
WaveCatcher/
├── backend/            # FastAPI Backend
│   ├── app/            # Source code
│   │   ├── api/        # REST endpoints and routers
│   │   ├── core/       # Global configuration
│   │   ├── db/         # Database models, engine, and session management
│   │   ├── logic/      # Core analysis models and trading algorithms
│   │   └── services/   # Shared business logic services
│   └── data/           # Local CSV/Tab data storage
├── frontend/           # React Frontend
│   ├── src/            # Application source
│   │   ├── components/ # Shared UI components (Sidebar, Charts, Grids)
│   │   ├── pages/      # Main views (Dashboard, Configuration)
│   │   ├── services/   # API client modules
│   │   └── utils/      # Utility helpers and formatters
│   └── public/         # Static assets
└── requirements.txt    # Root legacy dependency list
```

## Reports and daily runs

Each successful analysis now exports a self-contained HTML report. It includes
each selected index's actual Summary card, Market Breadth view, eight distribution
charts, and the Summary's 1234 Signals and High Return Opportunities tables
(Top 10 for each direction). The dashboard and report share the same React chart
components and saved analysis data, including candlesticks, moving averages,
volume, signals, interval weights, and constituent normalization. **Export saved
results** uses the Summary's selected indices and date ranges. Automatic reports
use the configured lookbacks: 365 days for charts and 7 days for signals by default.
Market Breadth and Distribution start collapsed in the HTML report; click each
heading to expand or collapse it. Expand the sections you want before printing.

Open **Configuration → Reports & Schedule** to change the absolute output folder,
lookbacks, scheduled indices, daily time, or timezone. The default schedule is
**13:30 America/Los_Angeles**, every day, for SPX, QQQ, DJI, and IWM. Settings are
saved on the backend computer. The initial output folder is `reports/` in the
project. To sync reports to Dropbox, select a folder under that computer's
existing Dropbox desktop sync directory, for example
`/Users/you/Library/CloudStorage/Dropbox/WaveCatcher Reports`. A Dropbox connection
in a chat does not give the standalone backend Dropbox credentials.

The backend must remain running and the computer awake; the browser may close.
Use one backend worker. Daylight saving time follows the configured timezone.
Missed times while the backend is stopped are skipped; if another analysis is
running at the scheduled time, the scheduled run waits. Daily dispatches are
recorded to prevent duplicate runs after restart. This is an application
scheduler, not an operating-system wake or auto-start service.

Use **Summary → Analysis report** or the recent report list in Configuration to
open/download a report. In an open HTML report, **Print / Save as PDF** uses your
browser's PDF printer; automatic output is HTML. Files embed their chart renderer,
styles, and data and work offline with JavaScript enabled. `npm run build` includes
the report renderer; export also rebuilds it when missing or outdated (Node/npm
and installed frontend dependencies are required for rebuilding).
Unique filenames prevent overwrites. Export failures
are shown independently and can be retried without rerunning market analysis.

To create a report immediately, click **Run now & generate report** in Summary
or **Configuration → Reports & Schedule**. Summary uses the indices selected in
the sidebar; Configuration uses the saved scheduled indices and report settings.
The button shows progress, prevents overlapping jobs, and links to the saved
report when complete. **Export saved results** exports an already completed run
without downloading fresh market data. Manual runs do not change the daily schedule.

Runs now retain their history, constituent membership, daily prices, and report
scoring configuration, so later analyses cannot change an exported report. Runs
created before this feature lack those snapshots and require a fresh analysis.
Database cleanup still removes source runs; already exported HTML files remain.

Offline regression checks (from the repository root):

```bash
PYTHONPATH=backend python -m unittest discover -s backend/tests -p test_reports.py -v
cd frontend
npm run build
```

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.
