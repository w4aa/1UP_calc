"""
Engine Comparison Report Generator

Generates comprehensive comparison reports for all 1UP pricing engines
in both CSV and HTML formats.

Features:
- Weighted metrics (time to match, odds similarity)
- Comparison with Poisson-Calibrated engine
- Underdog vs Favorite analysis
- Beautiful HTML report with charts

Usage:
    python generate_engine_report.py
    python generate_engine_report.py --output-dir reports
"""

import sys
import csv
import math
import statistics
import argparse
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Tuple

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.db.manager import DatabaseManager
from src.config import ConfigLoader
from src.engine.poisson_calibrated import CalibratedPoissonEngine
from src.engine.base import simulate_1up_probabilities, devig_two_way
from src.engine.poisson_calibrated import correct_1up_probabilities


def get_actual_fair_odds(actual_home: float, actual_away: float) -> Tuple[float, float]:
    """Convert actual 1UP odds (with margin) to fair odds."""
    if not actual_home or not actual_away:
        return None, None

    # Use centralized de-vigging function from base.py
    fair_prob_home = devig_two_way(actual_home, actual_away)
    fair_prob_away = 1.0 - fair_prob_home

    return 1 / fair_prob_home, 1 / fair_prob_away


def calculate_time_weight(start_time_str: str, scraped_at_str: str) -> float:
    """Calculate weight based on time to match start."""
    try:
        for fmt in ['%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%SZ']:
            try:
                start_time = datetime.strptime(start_time_str.replace('Z', ''), fmt.replace('Z', ''))
                break
            except ValueError:
                continue
        else:
            return 0.5
        
        for fmt in ['%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%SZ']:
            try:
                scraped_at = datetime.strptime(scraped_at_str.replace('Z', ''), fmt.replace('Z', ''))
                break
            except ValueError:
                continue
        else:
            return 0.5
        
        hours_to_start = (start_time - scraped_at).total_seconds() / 3600
        hours_to_start = max(0, hours_to_start)
        return 1.0 / (1.0 + hours_to_start / 24.0)
    except Exception:
        return 0.5


def calculate_odds_similarity_weight(sporty_1x2: tuple, pawa_1x2: tuple) -> float:
    """Calculate weight based on how similar pawa and sporty 1X2 odds are."""
    try:
        if not all(sporty_1x2) or not all(pawa_1x2):
            return 0.5
        
        diffs = []
        for s, p in zip(sporty_1x2, pawa_1x2):
            if s and p and s > 0:
                rel_diff = abs(s - p) / s
                diffs.append(rel_diff)
        
        if not diffs:
            return 0.5
        
        avg_diff = sum(diffs) / len(diffs)
        return 1.0 / (1.0 + avg_diff * 5)
    except Exception:
        return 0.5


class EngineReportGenerator:
    """Generates comprehensive engine comparison reports."""
    
    def __init__(self, db: DatabaseManager, config: ConfigLoader):
        self.db = db
        self.config = config
        self.timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Initialize calibrated engine
        sim_config = config.get_engine_simulation_settings()
        self.calibrated_engine = CalibratedPoissonEngine(
            n_sims=sim_config['n_sims'],
            match_minutes=sim_config['match_minutes'],
            margin_pct=0.0,
        )
    
    def get_all_calculations(self) -> list:
        """Get all engine calculations from database with event info."""
        cursor = self.db.conn.cursor()
        cursor.execute("""
            SELECT
                ec.id,
                ec.sportradar_id,
                ec.scraping_history_id,
                ec.engine_name,
                ec.bookmaker,
                ec.lambda_home,
                ec.lambda_away,
                ec.lambda_total,
                ec.p_home_1up,
                ec.p_away_1up,
                ec.fair_home,
                ec.fair_away,
                ec.fair_draw,
                ec.actual_sporty_home,
                ec.actual_sporty_away,
                ec.actual_sporty_draw,
                ec.calculated_at,
                e.home_team,
                e.away_team,
                e.start_time,
                sh.scraped_at
            FROM engine_calculations ec
            JOIN events e ON ec.sportradar_id = e.sportradar_id
            LEFT JOIN scraping_history sh ON ec.scraping_history_id = sh.id
            WHERE ec.bookmaker = 'pawa'
            ORDER BY ec.sportradar_id, ec.scraping_history_id, ec.engine_name
        """)
        return [dict(row) for row in cursor.fetchall()]
    
    def get_market_data_for_calc(self, sportradar_id: str, scraping_history_id: int) -> dict:
        """Get market data for a specific calculation."""
        cursor = self.db.conn.cursor()
        
        if scraping_history_id:
            cursor.execute("""
                SELECT market_name, specifier,
                       sporty_outcome_1_odds, sporty_outcome_2_odds, sporty_outcome_3_odds,
                       pawa_outcome_1_odds, pawa_outcome_2_odds, pawa_outcome_3_odds
                FROM market_snapshots
                WHERE scraping_history_id = ?
            """, (scraping_history_id,))
        else:
            cursor.execute("""
                SELECT market_name, specifier,
                       sporty_outcome_1_odds, sporty_outcome_2_odds, sporty_outcome_3_odds,
                       pawa_outcome_1_odds, pawa_outcome_2_odds, pawa_outcome_3_odds
                FROM markets
                WHERE sportradar_id = ?
            """, (sportradar_id,))
        
        markets = {}
        for row in cursor.fetchall():
            key = (row['market_name'], row['specifier'])
            markets[key] = dict(row)
        return markets
    
    def compute_calibrated_for_calc(self, calc: dict) -> dict:
        """Compute calibrated engine result for comparison."""
        lambda_home = calc['lambda_home']
        lambda_away = calc['lambda_away']
        
        if not lambda_home or not lambda_away:
            return None
        
        p_home_raw, p_away_raw = simulate_1up_probabilities(
            lambda_home, lambda_away,
            n_sims=30000,
            match_minutes=95
        )
        
        p_home_cal, p_away_cal = correct_1up_probabilities(
            p_home_raw, p_away_raw,
            lambda_home, lambda_away
        )
        
        fair_home_cal = 1 / p_home_cal if p_home_cal > 0 else None
        fair_away_cal = 1 / p_away_cal if p_away_cal > 0 else None
        
        return {
            'fair_home': fair_home_cal,
            'fair_away': fair_away_cal,
            'p_home_1up': p_home_cal,
            'p_away_1up': p_away_cal,
        }
    
    def analyze(self) -> Dict:
        """Run comprehensive analysis."""
        print("Loading calculations from database...")
        calculations = self.get_all_calculations()
        print(f"Found {len(calculations)} calculations")
        
        engine_results = defaultdict(lambda: {
            'weighted_home_errors': [],
            'weighted_away_errors': [],
            'weighted_underdog_errors': [],
            'weighted_favorite_errors': [],
            'unweighted_home_errors': [],
            'unweighted_away_errors': [],
            'unweighted_underdog_errors': [],
            'unweighted_favorite_errors': [],
            'weights': [],
            'time_weights': [],
            'odds_weights': [],
            'count': 0,
        })
        
        calibrated_results = {
            'weighted_home_errors': [],
            'weighted_away_errors': [],
            'weighted_underdog_errors': [],
            'weighted_favorite_errors': [],
            'unweighted_home_errors': [],
            'unweighted_away_errors': [],
            'unweighted_underdog_errors': [],
            'unweighted_favorite_errors': [],
            'weights': [],
            'time_weights': [],
            'odds_weights': [],
            'count': 0,
        }
        
        # Detailed records for CSV
        detailed_records = []
        
        processed = 0
        calibrated_computed = 0
        
        for i, calc in enumerate(calculations):
            if i % 100 == 0:
                print(f"  Processing {i}/{len(calculations)}...")
            
            if not calc['actual_sporty_home'] or not calc['actual_sporty_away']:
                continue

            actual_fair_home, actual_fair_away = get_actual_fair_odds(
                calc['actual_sporty_home'], calc['actual_sporty_away']
            )
            
            if not actual_fair_home or not actual_fair_away:
                continue
            
            if not calc['fair_home'] or not calc['fair_away']:
                continue
            
            home_error = calc['fair_home'] - actual_fair_home
            away_error = calc['fair_away'] - actual_fair_away
            
            is_home_underdog = actual_fair_home > actual_fair_away
            underdog_error = home_error if is_home_underdog else away_error
            favorite_error = away_error if is_home_underdog else home_error
            
            markets = self.get_market_data_for_calc(
                calc['sportradar_id'], 
                calc['scraping_history_id']
            )
            
            start_time = calc['start_time'] or ''
            scraped_at = calc['scraped_at'] or calc['calculated_at'] or ''
            time_weight = calculate_time_weight(start_time, scraped_at)
            
            x1x2_key = ('1X2', '')
            if x1x2_key in markets:
                m = markets[x1x2_key]
                sporty_1x2 = (m['sporty_outcome_1_odds'], m['sporty_outcome_2_odds'], m['sporty_outcome_3_odds'])
                pawa_1x2 = (m['pawa_outcome_1_odds'], m['pawa_outcome_2_odds'], m['pawa_outcome_3_odds'])
                odds_weight = calculate_odds_similarity_weight(sporty_1x2, pawa_1x2)
            else:
                sporty_1x2 = (None, None, None)
                pawa_1x2 = (None, None, None)
                odds_weight = 0.5
            
            weight = time_weight * odds_weight
            
            engine = calc['engine_name']
            engine_results[engine]['weighted_home_errors'].append(abs(home_error) * weight)
            engine_results[engine]['weighted_away_errors'].append(abs(away_error) * weight)
            engine_results[engine]['weighted_underdog_errors'].append(abs(underdog_error) * weight)
            engine_results[engine]['weighted_favorite_errors'].append(abs(favorite_error) * weight)
            engine_results[engine]['unweighted_home_errors'].append(home_error)
            engine_results[engine]['unweighted_away_errors'].append(away_error)
            engine_results[engine]['unweighted_underdog_errors'].append(underdog_error)
            engine_results[engine]['unweighted_favorite_errors'].append(favorite_error)
            engine_results[engine]['weights'].append(weight)
            engine_results[engine]['time_weights'].append(time_weight)
            engine_results[engine]['odds_weights'].append(odds_weight)
            engine_results[engine]['count'] += 1
            
            processed += 1
            
            # Compute calibrated for Poisson comparisons
            cal_result = None
            if engine == 'Poisson':
                cal_result = self.compute_calibrated_for_calc(calc)
                if cal_result and cal_result['fair_home'] and cal_result['fair_away']:
                    cal_home_error = cal_result['fair_home'] - actual_fair_home
                    cal_away_error = cal_result['fair_away'] - actual_fair_away
                    cal_underdog_error = cal_home_error if is_home_underdog else cal_away_error
                    cal_favorite_error = cal_away_error if is_home_underdog else cal_home_error
                    
                    calibrated_results['weighted_home_errors'].append(abs(cal_home_error) * weight)
                    calibrated_results['weighted_away_errors'].append(abs(cal_away_error) * weight)
                    calibrated_results['weighted_underdog_errors'].append(abs(cal_underdog_error) * weight)
                    calibrated_results['weighted_favorite_errors'].append(abs(cal_favorite_error) * weight)
                    calibrated_results['unweighted_home_errors'].append(cal_home_error)
                    calibrated_results['unweighted_away_errors'].append(cal_away_error)
                    calibrated_results['unweighted_underdog_errors'].append(cal_underdog_error)
                    calibrated_results['unweighted_favorite_errors'].append(cal_favorite_error)
                    calibrated_results['weights'].append(weight)
                    calibrated_results['time_weights'].append(time_weight)
                    calibrated_results['odds_weights'].append(odds_weight)
                    calibrated_results['count'] += 1
                    calibrated_computed += 1
            
            # Store detailed record
            detailed_records.append({
                'sportradar_id': calc['sportradar_id'],
                'home_team': calc['home_team'],
                'away_team': calc['away_team'],
                'engine': engine,
                'lambda_home': calc['lambda_home'],
                'lambda_away': calc['lambda_away'],
                'fair_home': calc['fair_home'],
                'fair_away': calc['fair_away'],
                'actual_fair_home': actual_fair_home,
                'actual_fair_away': actual_fair_away,
                'home_error': home_error,
                'away_error': away_error,
                'underdog_error': underdog_error,
                'favorite_error': favorite_error,
                'is_home_underdog': is_home_underdog,
                'time_weight': time_weight,
                'odds_weight': odds_weight,
                'combined_weight': weight,
                'calibrated_fair_home': cal_result['fair_home'] if cal_result else None,
                'calibrated_fair_away': cal_result['fair_away'] if cal_result else None,
            })
        
        print(f"\nProcessed {processed} calculations")
        print(f"Computed {calibrated_computed} calibrated comparisons")
        
        return {
            'engines': dict(engine_results),
            'calibrated': calibrated_results,
            'detailed': detailed_records,
            'timestamp': self.timestamp,
            'total_calculations': len(calculations),
            'processed': processed,
        }
    
    def compute_summary_metrics(self, results: Dict) -> List[Dict]:
        """Compute summary metrics for each engine."""
        rows = []
        
        all_engines = list(results['engines'].keys())
        
        for engine in sorted(all_engines):
            data = results['engines'][engine]
            if data['count'] == 0:
                continue
            
            w_sum = sum(data['weights'])
            
            rows.append({
                'engine': engine,
                'count': data['count'],
                'weighted_mae_home': sum(data['weighted_home_errors']) / w_sum if w_sum > 0 else 0,
                'weighted_mae_away': sum(data['weighted_away_errors']) / w_sum if w_sum > 0 else 0,
                'weighted_mae_underdog': sum(data['weighted_underdog_errors']) / w_sum if w_sum > 0 else 0,
                'weighted_mae_favorite': sum(data['weighted_favorite_errors']) / w_sum if w_sum > 0 else 0,
                'avg_home_diff': statistics.mean(data['unweighted_home_errors']),
                'avg_away_diff': statistics.mean(data['unweighted_away_errors']),
                'avg_underdog_diff': statistics.mean(data['unweighted_underdog_errors']),
                'avg_favorite_diff': statistics.mean(data['unweighted_favorite_errors']),
                'avg_time_weight': statistics.mean(data['time_weights']),
                'avg_odds_weight': statistics.mean(data['odds_weights']),
                'avg_combined_weight': statistics.mean(data['weights']),
            })
        
        # Add calibrated
        cal_data = results['calibrated']
        if cal_data['count'] > 0:
            w_sum = sum(cal_data['weights'])
            rows.append({
                'engine': 'Poisson-Calibrated',
                'count': cal_data['count'],
                'weighted_mae_home': sum(cal_data['weighted_home_errors']) / w_sum if w_sum > 0 else 0,
                'weighted_mae_away': sum(cal_data['weighted_away_errors']) / w_sum if w_sum > 0 else 0,
                'weighted_mae_underdog': sum(cal_data['weighted_underdog_errors']) / w_sum if w_sum > 0 else 0,
                'weighted_mae_favorite': sum(cal_data['weighted_favorite_errors']) / w_sum if w_sum > 0 else 0,
                'avg_home_diff': statistics.mean(cal_data['unweighted_home_errors']),
                'avg_away_diff': statistics.mean(cal_data['unweighted_away_errors']),
                'avg_underdog_diff': statistics.mean(cal_data['unweighted_underdog_errors']),
                'avg_favorite_diff': statistics.mean(cal_data['unweighted_favorite_errors']),
                'avg_time_weight': statistics.mean(cal_data['time_weights']),
                'avg_odds_weight': statistics.mean(cal_data['odds_weights']),
                'avg_combined_weight': statistics.mean(cal_data['weights']),
            })
        
        return rows
    
    def generate_csv(self, results: Dict, summary: List[Dict], output_dir: Path):
        """Generate CSV reports."""
        # Summary CSV
        summary_path = output_dir / f'engine_summary_{self.timestamp}.csv'
        with open(summary_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=summary[0].keys())
            writer.writeheader()
            for row in summary:
                # Round floats
                rounded = {k: round(v, 4) if isinstance(v, float) else v for k, v in row.items()}
                writer.writerow(rounded)
        print(f"Summary CSV: {summary_path}")
        
        # Detailed CSV
        if results['detailed']:
            detailed_path = output_dir / f'engine_detailed_{self.timestamp}.csv'
            with open(detailed_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=results['detailed'][0].keys())
                writer.writeheader()
                for row in results['detailed']:
                    rounded = {k: round(v, 4) if isinstance(v, float) else v for k, v in row.items()}
                    writer.writerow(rounded)
            print(f"Detailed CSV: {detailed_path}")
        
        return summary_path
    
    def generate_html(self, results: Dict, summary: List[Dict], output_dir: Path):
        """Generate HTML report."""
        html_path = output_dir / f'engine_report_{self.timestamp}.html'
        
        # Find best engine
        best_overall = min(summary, key=lambda x: (x['weighted_mae_home'] + x['weighted_mae_away']) / 2)
        best_underdog = min(summary, key=lambda x: x['weighted_mae_underdog'])
        best_favorite = min(summary, key=lambda x: x['weighted_mae_favorite'])
        
        # Improvement calculations (Poisson-Calibrated vs Poisson)
        poisson = next((s for s in summary if s['engine'] == 'Poisson'), None)
        calibrated = next((s for s in summary if s['engine'] == 'Poisson-Calibrated'), None)
        
        improvements = {}
        if poisson and calibrated:
            improvements = {
                'home': (1 - calibrated['weighted_mae_home'] / poisson['weighted_mae_home']) * 100,
                'away': (1 - calibrated['weighted_mae_away'] / poisson['weighted_mae_away']) * 100,
                'underdog': (1 - calibrated['weighted_mae_underdog'] / poisson['weighted_mae_underdog']) * 100,
                'favorite': (1 - calibrated['weighted_mae_favorite'] / poisson['weighted_mae_favorite']) * 100,
            }
        
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>1UP Engine Comparison Report - {self.timestamp}</title>
    <style>
        :root {{
            --primary: #2563eb;
            --success: #16a34a;
            --warning: #d97706;
            --danger: #dc2626;
            --bg: #f8fafc;
            --card-bg: #ffffff;
            --text: #1e293b;
            --text-muted: #64748b;
            --border: #e2e8f0;
        }}
        
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg);
            color: var(--text);
            line-height: 1.6;
            padding: 2rem;
        }}
        
        .container {{
            max-width: 1400px;
            margin: 0 auto;
        }}
        
        header {{
            text-align: center;
            margin-bottom: 2rem;
            padding-bottom: 1rem;
            border-bottom: 2px solid var(--border);
        }}
        
        h1 {{
            font-size: 2rem;
            color: var(--primary);
            margin-bottom: 0.5rem;
        }}
        
        .subtitle {{
            color: var(--text-muted);
            font-size: 1rem;
        }}
        
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }}
        
        .stat-card {{
            background: var(--card-bg);
            border-radius: 12px;
            padding: 1.5rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            text-align: center;
        }}
        
        .stat-value {{
            font-size: 2rem;
            font-weight: 700;
            color: var(--primary);
        }}
        
        .stat-value.success {{
            color: var(--success);
        }}
        
        .stat-label {{
            color: var(--text-muted);
            font-size: 0.875rem;
            margin-top: 0.25rem;
        }}
        
        .section {{
            background: var(--card-bg);
            border-radius: 12px;
            padding: 1.5rem;
            margin-bottom: 2rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}
        
        .section h2 {{
            font-size: 1.25rem;
            margin-bottom: 1rem;
            padding-bottom: 0.5rem;
            border-bottom: 1px solid var(--border);
        }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
        }}
        
        th, td {{
            padding: 0.75rem 1rem;
            text-align: left;
            border-bottom: 1px solid var(--border);
        }}
        
        th {{
            background: var(--bg);
            font-weight: 600;
            font-size: 0.875rem;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}
        
        tr:hover {{
            background: var(--bg);
        }}
        
        .engine-name {{
            font-weight: 600;
        }}
        
        .best {{
            background: #dcfce7 !important;
        }}
        
        .best .engine-name {{
            color: var(--success);
        }}
        
        .metric {{
            font-family: monospace;
            font-size: 0.9rem;
        }}
        
        .positive {{
            color: var(--danger);
        }}
        
        .negative {{
            color: var(--success);
        }}
        
        .improvement {{
            display: inline-block;
            padding: 0.25rem 0.5rem;
            border-radius: 4px;
            font-size: 0.875rem;
            font-weight: 600;
        }}
        
        .improvement.up {{
            background: #dcfce7;
            color: var(--success);
        }}
        
        .bar-chart {{
            margin-top: 1rem;
        }}
        
        .bar-row {{
            display: flex;
            align-items: center;
            margin-bottom: 0.75rem;
        }}
        
        .bar-label {{
            width: 150px;
            font-size: 0.875rem;
            font-weight: 500;
        }}
        
        .bar-container {{
            flex: 1;
            height: 24px;
            background: var(--bg);
            border-radius: 4px;
            overflow: hidden;
            position: relative;
        }}
        
        .bar {{
            height: 100%;
            border-radius: 4px;
            transition: width 0.5s ease;
        }}
        
        .bar-value {{
            position: absolute;
            right: 8px;
            top: 50%;
            transform: translateY(-50%);
            font-size: 0.75rem;
            font-weight: 600;
            color: var(--text);
        }}
        
        .legend {{
            display: flex;
            gap: 1.5rem;
            margin-top: 1rem;
            font-size: 0.875rem;
        }}
        
        .legend-item {{
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }}
        
        .legend-color {{
            width: 16px;
            height: 16px;
            border-radius: 4px;
        }}
        
        .methodology {{
            font-size: 0.875rem;
            color: var(--text-muted);
        }}
        
        .methodology code {{
            background: var(--bg);
            padding: 0.125rem 0.375rem;
            border-radius: 4px;
            font-family: monospace;
        }}
        
        footer {{
            text-align: center;
            color: var(--text-muted);
            font-size: 0.875rem;
            margin-top: 2rem;
            padding-top: 1rem;
            border-top: 1px solid var(--border);
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🎯 1UP Engine Comparison Report</h1>
            <p class="subtitle">Generated: {datetime.now().strftime('%B %d, %Y at %H:%M')}</p>
        </header>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-value">{results['processed']:,}</div>
                <div class="stat-label">Calculations Analyzed</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{len(results['engines'])}</div>
                <div class="stat-label">Engines Compared</div>
            </div>
            <div class="stat-card">
                <div class="stat-value success">{best_overall['engine']}</div>
                <div class="stat-label">Best Overall Engine</div>
            </div>
            <div class="stat-card">
                <div class="stat-value success">+{improvements.get('underdog', 0):.0f}%</div>
                <div class="stat-label">Underdog Accuracy Improvement</div>
            </div>
        </div>
        
        <div class="section">
            <h2>📊 Weighted Mean Absolute Error (Lower = Better)</h2>
            <p class="methodology" style="margin-bottom: 1rem;">
                Weighted by: <code>Time to Match × Odds Similarity</code>. 
                Higher weight when closer to kickoff and when Pawa/Sporty odds align.
            </p>
            <table>
                <thead>
                    <tr>
                        <th>Engine</th>
                        <th>Count</th>
                        <th>W-MAE Home</th>
                        <th>W-MAE Away</th>
                        <th>W-MAE Underdog</th>
                        <th>W-MAE Favorite</th>
                        <th>Avg Weight</th>
                    </tr>
                </thead>
                <tbody>
"""
        
        for row in summary:
            is_best = row['engine'] == best_overall['engine']
            row_class = 'best' if is_best else ''
            
            html += f"""                    <tr class="{row_class}">
                        <td class="engine-name">{row['engine']}</td>
                        <td>{row['count']}</td>
                        <td class="metric">{row['weighted_mae_home']:.4f}</td>
                        <td class="metric">{row['weighted_mae_away']:.4f}</td>
                        <td class="metric">{row['weighted_mae_underdog']:.4f}</td>
                        <td class="metric">{row['weighted_mae_favorite']:.4f}</td>
                        <td class="metric">{row['avg_combined_weight']:.3f}</td>
                    </tr>
"""
        
        html += """                </tbody>
            </table>
        </div>
        
        <div class="section">
            <h2>📈 Raw Bias Analysis (Negative = Conservative)</h2>
            <p class="methodology" style="margin-bottom: 1rem;">
                Average difference between our fair odds and market fair odds. 
                Negative values mean we offer lower odds than market (conservative).
            </p>
            <table>
                <thead>
                    <tr>
                        <th>Engine</th>
                        <th>Avg Home Diff</th>
                        <th>Avg Away Diff</th>
                        <th>Avg Underdog Diff</th>
                        <th>Avg Favorite Diff</th>
                    </tr>
                </thead>
                <tbody>
"""
        
        for row in summary:
            is_best = row['engine'] == best_overall['engine']
            row_class = 'best' if is_best else ''
            
            home_class = 'negative' if row['avg_home_diff'] < 0 else 'positive'
            away_class = 'negative' if row['avg_away_diff'] < 0 else 'positive'
            udog_class = 'negative' if row['avg_underdog_diff'] < 0 else 'positive'
            fav_class = 'negative' if row['avg_favorite_diff'] < 0 else 'positive'
            
            html += f"""                    <tr class="{row_class}">
                        <td class="engine-name">{row['engine']}</td>
                        <td class="metric {home_class}">{row['avg_home_diff']:+.4f}</td>
                        <td class="metric {away_class}">{row['avg_away_diff']:+.4f}</td>
                        <td class="metric {udog_class}">{row['avg_underdog_diff']:+.4f}</td>
                        <td class="metric {fav_class}">{row['avg_favorite_diff']:+.4f}</td>
                    </tr>
"""
        
        html += """                </tbody>
            </table>
        </div>
        
        <div class="section">
            <h2>🚀 Poisson-Calibrated Improvements</h2>
            <div class="bar-chart">
"""
        
        # Add bar charts for improvements
        metrics = [
            ('Home 1UP', improvements.get('home', 0), '#3b82f6'),
            ('Away 1UP', improvements.get('away', 0), '#8b5cf6'),
            ('Underdog', improvements.get('underdog', 0), '#10b981'),
            ('Favorite', improvements.get('favorite', 0), '#f59e0b'),
        ]
        
        max_improvement = max(m[1] for m in metrics) if metrics else 1
        
        for label, value, color in metrics:
            bar_width = (value / max_improvement * 100) if max_improvement > 0 else 0
            html += f"""                <div class="bar-row">
                    <div class="bar-label">{label}</div>
                    <div class="bar-container">
                        <div class="bar" style="width: {bar_width}%; background: {color};"></div>
                        <span class="bar-value">+{value:.1f}%</span>
                    </div>
                </div>
"""
        
        html += f"""            </div>
            <p class="methodology" style="margin-top: 1rem;">
                Improvement compared to standard Poisson engine using weighted MAE metric.
            </p>
        </div>
        
        <div class="section">
            <h2>🏆 Best Engine by Category</h2>
            <table>
                <thead>
                    <tr>
                        <th>Category</th>
                        <th>Best Engine</th>
                        <th>W-MAE Score</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td>Overall</td>
                        <td class="engine-name" style="color: var(--success);">{best_overall['engine']}</td>
                        <td class="metric">{(best_overall['weighted_mae_home'] + best_overall['weighted_mae_away'])/2:.4f}</td>
                    </tr>
                    <tr>
                        <td>Home 1UP</td>
                        <td class="engine-name">{min(summary, key=lambda x: x['weighted_mae_home'])['engine']}</td>
                        <td class="metric">{min(summary, key=lambda x: x['weighted_mae_home'])['weighted_mae_home']:.4f}</td>
                    </tr>
                    <tr>
                        <td>Away 1UP</td>
                        <td class="engine-name">{min(summary, key=lambda x: x['weighted_mae_away'])['engine']}</td>
                        <td class="metric">{min(summary, key=lambda x: x['weighted_mae_away'])['weighted_mae_away']:.4f}</td>
                    </tr>
                    <tr>
                        <td>Underdog Accuracy</td>
                        <td class="engine-name" style="color: var(--success);">{best_underdog['engine']}</td>
                        <td class="metric">{best_underdog['weighted_mae_underdog']:.4f}</td>
                    </tr>
                    <tr>
                        <td>Favorite Accuracy</td>
                        <td class="engine-name">{best_favorite['engine']}</td>
                        <td class="metric">{best_favorite['weighted_mae_favorite']:.4f}</td>
                    </tr>
                </tbody>
            </table>
        </div>
        
        <div class="section">
            <h2>📝 Methodology</h2>
            <div class="methodology">
                <p><strong>Weighting System:</strong></p>
                <ul style="margin: 0.5rem 0 1rem 1.5rem;">
                    <li><strong>Time Weight:</strong> <code>1 / (1 + hours_to_start / 24)</code> — Higher weight when closer to match start</li>
                    <li><strong>Odds Similarity Weight:</strong> <code>1 / (1 + avg_relative_diff × 5)</code> — Higher when Pawa and Sporty odds match</li>
                    <li><strong>Combined Weight:</strong> <code>Time Weight × Odds Similarity Weight</code></li>
                </ul>
                
                <p><strong>Metrics:</strong></p>
                <ul style="margin: 0.5rem 0 1rem 1.5rem;">
                    <li><strong>W-MAE:</strong> Weighted Mean Absolute Error — measures accuracy with business-relevant weighting</li>
                    <li><strong>Avg Diff:</strong> Raw signed difference — shows systematic bias direction</li>
                    <li><strong>Underdog/Favorite:</strong> Separated by which team has higher fair odds</li>
                </ul>
                
                <p><strong>Data:</strong></p>
                <ul style="margin: 0.5rem 0 0 1.5rem;">
                    <li>Input odds: Betpawa (Pawa) markets</li>
                    <li>Target: Sportybet actual 1UP odds (de-vigged to fair)</li>
                    <li>Total calculations analyzed: {results['processed']:,}</li>
                </ul>
            </div>
        </div>
        
        <footer>
            <p>1UP Engine Analysis Report • Generated by analyze_engines_comprehensive.py</p>
        </footer>
    </div>
</body>
</html>
"""
        
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html)
        
        print(f"HTML Report: {html_path}")
        return html_path
    
    def generate_reports(self, output_dir: Path) -> Dict:
        """Generate all reports."""
        output_dir.mkdir(parents=True, exist_ok=True)
        
        results = self.analyze()
        summary = self.compute_summary_metrics(results)
        
        csv_path = self.generate_csv(results, summary, output_dir)
        html_path = self.generate_html(results, summary, output_dir)
        
        return {
            'csv': csv_path,
            'html': html_path,
            'summary': summary,
            'results': results,
        }


def main():
    parser = argparse.ArgumentParser(description='Generate 1UP Engine Comparison Reports')
    parser.add_argument('--output-dir', '-o', type=str, default='reports',
                        help='Output directory for reports (default: reports)')
    args = parser.parse_args()
    
    print("="*80)
    print("1UP ENGINE COMPARISON REPORT GENERATOR")
    print("="*80)
    print()
    
    config = ConfigLoader()
    db = DatabaseManager(config.get_db_path())
    db.connect()
    
    try:
        output_dir = PROJECT_ROOT / args.output_dir
        generator = EngineReportGenerator(db, config)
        results = generator.generate_reports(output_dir)
        
        print()
        print("="*80)
        print("REPORTS GENERATED SUCCESSFULLY")
        print("="*80)
        print(f"  CSV Summary: {results['csv']}")
        print(f"  HTML Report: {results['html']}")
        
    finally:
        db.close()


if __name__ == '__main__':
    main()
