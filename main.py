"""
1UP Calculator - Main Entry Point

Runs the complete pipeline:
1. Scrape odds from Sportybet and Betpawa
2. Run all 1UP pricing engines
3. Store results in database

Usage:
    python main.py              # Full run (scrape + engines)
    python main.py --scrape     # Scrape only
    python main.py --engines    # Engines only (no scraping)
    python main.py --analyze    # Run analysis after
"""

import asyncio
import argparse
import sys
from pathlib import Path

# Add src to path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))


async def run_scraper(force: bool = False, sporty_only: bool = False, pawa_only: bool = False):
    """Run the betting odds scraper."""
    from src.unified_scraper import UnifiedScraper
    
    scraper = UnifiedScraper()
    await scraper.run(
        scrape_sporty=not pawa_only,
        scrape_pawa=not sporty_only,
        force=force,
        run_engines=False  # We handle engines separately
    )


def run_engines():
    """Run all 1UP pricing engines on new snapshots."""
    from src.db.manager import DatabaseManager
    from src.config import ConfigLoader
    from src.engine.runner import EngineRunner
    
    print("\n" + "=" * 60)
    print("  1UP PRICING ENGINES")
    print("=" * 60)
    
    config = ConfigLoader()
    db = DatabaseManager(config.get_db_path())
    db.connect()
    
    try:
        runner = EngineRunner(db, config)
        
        # Check for unprocessed sessions
        unprocessed = db.get_unprocessed_sessions()
        
        if unprocessed:
            print(f"\nProcessing {len(unprocessed)} new match snapshots...")
            result = runner.run_new_snapshots()
            print(f"\nEngines complete!")
            print(f"  Sessions processed: {result.get('sessions', 0)}")
            print(f"  Calculations stored: {result['calculations']}")
        else:
            print("\nNo new snapshots to process.")
            print("All scraping sessions have been processed.")
    
    finally:
        db.close()


def run_analysis():
    """Run engine accuracy analysis."""
    from src.db.manager import DatabaseManager
    from src.config import ConfigLoader
    
    print("\n" + "=" * 60)
    print("  ENGINE ANALYSIS SUMMARY")
    print("=" * 60)
    
    config = ConfigLoader()
    db = DatabaseManager(config.get_db_path())
    db.connect()
    
    try:
        # Get best engine stats at 6% margin (optimal)
        stats = db.get_engine_accuracy_stats(0.06)
        
        if not stats:
            print("\n  No calculations found. Run scraper first.")
            return
        
        print(f"\n  Best performing engines (at 6% margin):\n")
        print(f"  {'Engine':<20} {'Source':<8} {'MAE':>10}")
        print(f"  {'-'*40}")
        
        for s in sorted(stats, key=lambda x: x['mae_total'])[:5]:
            print(f"  {s['engine_name']:<20} {s['bookmaker'].upper():<8} {s['mae_total']:>10.4f}")
        
        print(f"\n  For full analysis run: python analyze_engines.py")
        
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(
        description="1UP Calculator - Unified betting scraper and pricing engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                    # Full pipeline (scrape + engines)
  python main.py --scrape           # Scrape only
  python main.py --engines          # Run engines only
  python main.py -f                 # Force full scrape
  python main.py --sporty-only      # Scrape Sportybet only
  python main.py --analyze          # Show analysis after run
        """
    )
    
    # Mode selection
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--scrape", action="store_true",
                           help="Run scraper only (no engines)")
    mode_group.add_argument("--engines", action="store_true",
                           help="Run engines only (no scraping)")
    
    # Scraper options
    parser.add_argument("--force", "-f", action="store_true",
                        help="Force full scrape even if 1X2 odds unchanged")
    parser.add_argument("--sporty-only", action="store_true",
                        help="Only scrape Sportybet")
    parser.add_argument("--pawa-only", action="store_true",
                        help="Only scrape Betpawa")
    
    # Analysis
    parser.add_argument("--analyze", "-a", action="store_true",
                        help="Show engine analysis summary after run")
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("  1UP CALCULATOR")
    print("=" * 60)
    
    try:
        # Determine what to run
        if args.engines:
            # Engines only
            run_engines()
        elif args.scrape:
            # Scrape only
            asyncio.run(run_scraper(
                force=args.force,
                sporty_only=args.sporty_only,
                pawa_only=args.pawa_only
            ))
        else:
            # Full pipeline: scrape + engines
            asyncio.run(run_scraper(
                force=args.force,
                sporty_only=args.sporty_only,
                pawa_only=args.pawa_only
            ))
            run_engines()
        
        # Optional analysis
        if args.analyze:
            run_analysis()
        
        print("\n" + "=" * 60)
        print("  COMPLETE")
        print("=" * 60 + "\n")
        
    except KeyboardInterrupt:
        print("\n\nInterrupted by user.")
        sys.exit(1)


if __name__ == "__main__":
    main()
