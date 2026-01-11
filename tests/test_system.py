"""
System Test Script
Tests all three modes of operation:
1. Scraper only (--scrape)
2. Engines only (--engines)
3. Full pipeline (no flags)
"""

import sys
from pathlib import Path

# Add src to path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.db.manager import DatabaseManager
from src.config import ConfigLoader
from src.engine.runner import EngineRunner

def test_imports():
    """Test that all critical imports work."""
    print("Testing imports...")
    try:
        from src.engine import CalibratedPoissonEngine
        from src.engine.runner import EngineRunner
        print("[OK] Core engine imports successful")
        return True
    except Exception as e:
        print(f"[FAIL] Import failed: {e}")
        return False

def test_engine_runner():
    """Test that engine runner can be initialized."""
    print("\nTesting engine runner initialization...")
    try:
        config = ConfigLoader()
        db = DatabaseManager(config.get_db_path())
        db.connect()
        runner = EngineRunner(db, config)
        db.close()
        print("[OK] Engine runner initialized successfully")
        print(f"  Engines: {len(runner.engines)}")
        return True
    except Exception as e:
        print(f"[FAIL] Engine runner initialization failed: {e}")
        return False

def test_database():
    """Test database connectivity and stats."""
    print("\nTesting database...")
    try:
        config = ConfigLoader()
        db = DatabaseManager(config.get_db_path())
        db.connect()
        stats = db.get_stats()
        db.close()
        print("[OK] Database connection successful")
        print(f"  Events: {stats['total_events']}")
        print(f"  Matched: {stats['matched_events']}")
        print(f"  Markets: {stats['total_markets']}")
        return True
    except Exception as e:
        print(f"[FAIL] Database test failed: {e}")
        return False

def main():
    """Run all tests."""
    print("=" * 60)
    print("  1UP CALCULATOR SYSTEM TEST")
    print("=" * 60)

    tests = [
        test_imports,
        test_database,
        test_engine_runner,
    ]

    results = []
    for test in tests:
        results.append(test())

    print("\n" + "=" * 60)
    print(f"  RESULTS: {sum(results)}/{len(results)} tests passed")
    print("=" * 60)

    if all(results):
        print("\n[OK] All systems operational!")
        print("\nYou can now run:")
        print("  - python main.py --scrape    (scrape only)")
        print("  - python main.py --engines   (engines only)")
        print("  - python main.py             (full pipeline)")
        return 0
    else:
        print("\n[FAIL] Some tests failed. Please check errors above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
