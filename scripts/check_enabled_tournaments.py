import sys
from pathlib import Path
# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from src.config import ConfigLoader

c = ConfigLoader()
ets = c.get_enabled_tournaments()
print('enabled tournaments:', len(ets))
for t in ets:
    print(t.get('id'), 'pawa=', t.get('pawa_competition_id'), 'bet9ja=', t.get('bet9ja_group_id'))
