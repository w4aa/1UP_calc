import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import ConfigLoader
import sqlite3

cfg = ConfigLoader()
dbpath = cfg.get_db_path()
print(f"Using DB: {dbpath}")

conn = sqlite3.connect(dbpath)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

q = """
SELECT id, sportradar_id, market_name, specifier, sporty_market_id, pawa_market_id, bet9ja_market_id,
       sporty_outcome_1_name, sporty_outcome_1_odds, sporty_outcome_2_name, sporty_outcome_2_odds, sporty_outcome_3_name, sporty_outcome_3_odds,
       pawa_outcome_1_name, pawa_outcome_1_odds, pawa_outcome_2_name, pawa_outcome_2_odds, pawa_outcome_3_name, pawa_outcome_3_odds,
       bet9ja_outcome_1_name, bet9ja_outcome_1_odds, bet9ja_outcome_2_name, bet9ja_outcome_2_odds, bet9ja_outcome_3_name, bet9ja_outcome_3_odds
FROM markets
WHERE market_name = 'First Team to Score'
ORDER BY id
"""

rows = cur.execute(q).fetchall()
print(f"Found {len(rows)} 'First Team to Score' rows")
for r in rows:
    d = dict(r)
    # Compact display
    print({
        'id': d['id'],
        'sportradar_id': d['sportradar_id'],
        'specifier': d['specifier'],
        'sporty_market_id': d.get('sporty_market_id'),
        'pawa_market_id': d.get('pawa_market_id'),
        'bet9ja_market_id': d.get('bet9ja_market_id'),
        'sporty_outcomes': [
            (d.get('sporty_outcome_1_name'), d.get('sporty_outcome_1_odds')),
            (d.get('sporty_outcome_2_name'), d.get('sporty_outcome_2_odds')),
            (d.get('sporty_outcome_3_name'), d.get('sporty_outcome_3_odds')),
        ],
        'pawa_outcomes': [
            (d.get('pawa_outcome_1_name'), d.get('pawa_outcome_1_odds')),
            (d.get('pawa_outcome_2_name'), d.get('pawa_outcome_2_odds')),
            (d.get('pawa_outcome_3_name'), d.get('pawa_outcome_3_odds')),
        ],
        'bet9ja_outcomes': [
            (d.get('bet9ja_outcome_1_name'), d.get('bet9ja_outcome_1_odds')),
            (d.get('bet9ja_outcome_2_name'), d.get('bet9ja_outcome_2_odds')),
            (d.get('bet9ja_outcome_3_name'), d.get('bet9ja_outcome_3_odds')),
        ],
    })

conn.close()
