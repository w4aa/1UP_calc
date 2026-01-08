# 1UP_calc

Football 1UP pricing engine and analysis tools.

This repository contains engines and scrapers used to compute early-payout (1UP) pricing from bookmaker markets.

Contents
- `src/engine` — pricing engines
- `src/scraper` — market scrapers for Sporty, Pawa, Bet9ja
- `scripts/` — utility scripts
- `config/` — configuration for markets, tournaments, and engine settings
- `reports/` — generated analysis CSVs

Quick start

1. Create and activate a Python virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Install dependencies (add SciPy if you want optimizer improvements):

```powershell
pip install -r requirements.txt
# optional: pip install scipy
```

3. Run the engine analysis:

```powershell
python main.py --engines
```

License: MIT (see LICENSE)
