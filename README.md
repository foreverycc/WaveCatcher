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

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.