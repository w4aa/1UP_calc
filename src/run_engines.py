"""
Run 1UP Engines

Runs all pricing engines on existing database events without scraping.
Useful for re-calculating after config changes.

Usage:
    python src/run_engines.py
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.engine.runner import run_engines_on_all_events


def main():
    print("=" * 60)
    print("  1UP ENGINE RUNNER")
    print("=" * 60)
    print("\nLoading database and engines...")
    print("Running calculations (this may take a minute)...\n")
    
    result = run_engines_on_all_events()
    
    print(f"\nDone!")
    print(f"Events processed: {result['events']}")
    print(f"Calculations stored: {result['calculations']}")


if __name__ == "__main__":
    main()
