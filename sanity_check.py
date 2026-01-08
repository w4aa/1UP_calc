"""
Sanity Check Script

Validates the database integrity and system functionality.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.db.manager import DatabaseManager
from src.config import ConfigLoader

def main():
    print("=" * 70)
    print("  SANITY CHECK - 1UP CALCULATOR")
    print("=" * 70)
    
    config = ConfigLoader()
    db = DatabaseManager(config.get_db_path())
    db.connect()
    
    try:
        # 1. Database Stats
        print("\n[1] DATABASE STATISTICS")
        print("-" * 70)
        stats = db.get_stats()
        print(f"  Total Events:          {stats['total_events']}")
        print(f"  Matched Events:        {stats['matched_events']}")
        print(f"  Total Markets:         {stats['total_markets']}")
        print(f"  Matched Markets:       {stats['matched_markets']}")
        print(f"  Scraping Sessions:     {stats['total_sessions']}")
        print(f"  Market Snapshots:      {stats['total_snapshots']}")
        print(f"  Tournaments:           {stats['total_tournaments']}")
        
        # 2. Engine Calculations
        print("\n[2] ENGINE CALCULATIONS")
        print("-" * 70)
        cursor = db.conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM engine_calculations")
        total_calcs = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM engine_calculations WHERE scraping_history_id IS NOT NULL")
        calcs_with_session = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM engine_calculations WHERE scraping_history_id IS NULL")
        calcs_without_session = cursor.fetchone()[0]
        
        print(f"  Total Calculations:    {total_calcs}")
        print(f"  With Session ID:       {calcs_with_session} ({calcs_with_session/total_calcs*100:.1f}%)")
        print(f"  Without Session ID:    {calcs_without_session} ({calcs_without_session/total_calcs*100 if total_calcs > 0 else 0:.1f}%)")
        
        # 3. Unprocessed Sessions
        print("\n[3] PENDING WORK")
        print("-" * 70)
        unprocessed = db.get_unprocessed_sessions()
        print(f"  Unprocessed Sessions:  {len(unprocessed)}")
        
        if unprocessed:
            print(f"\n  Details:")
            for s in unprocessed[:10]:  # Show first 10
                markets = db.get_markets_for_event(s["sportradar_id"])
                print(f"    - Session {s['id']}: {s.get('home_team', 'Unknown')} vs {s.get('away_team', 'Unknown')}")
                print(f"      Markets: {len(markets)}, Sportradar ID: {s['sportradar_id']}")
            if len(unprocessed) > 10:
                print(f"    ... and {len(unprocessed) - 10} more")
        
        # 4. Data Consistency Checks
        print("\n[4] DATA CONSISTENCY CHECKS")
        print("-" * 70)
        
        # Check for orphaned calculations (no matching event)
        cursor.execute("""
            SELECT COUNT(*) FROM engine_calculations ec
            WHERE NOT EXISTS (
                SELECT 1 FROM events e WHERE e.sportradar_id = ec.sportradar_id
            )
        """)
        orphaned_calcs = cursor.fetchone()[0]
        print(f"  Orphaned Calculations: {orphaned_calcs} {'✓' if orphaned_calcs == 0 else '⚠'}")
        
        # Check for snapshots without valid session
        cursor.execute("""
            SELECT COUNT(*) FROM market_snapshots ms
            WHERE NOT EXISTS (
                SELECT 1 FROM scraping_history sh WHERE sh.id = ms.scraping_history_id
            )
        """)
        orphaned_snapshots = cursor.fetchone()[0]
        print(f"  Orphaned Snapshots:    {orphaned_snapshots} {'✓' if orphaned_snapshots == 0 else '⚠'}")
        
        # Check for calculations with invalid session ID
        cursor.execute("""
            SELECT COUNT(*) FROM engine_calculations ec
            WHERE ec.scraping_history_id IS NOT NULL
            AND NOT EXISTS (
                SELECT 1 FROM scraping_history sh WHERE sh.id = ec.scraping_history_id
            )
        """)
        invalid_session_refs = cursor.fetchone()[0]
        print(f"  Invalid Session Refs:  {invalid_session_refs} {'✓' if invalid_session_refs == 0 else '⚠'}")
        
        # 5. Engine Performance Summary
        print("\n[5] ENGINE PERFORMANCE (at 6% margin)")
        print("-" * 70)
        accuracy_stats = db.get_engine_accuracy_stats(0.06)
        
        if accuracy_stats:
            print(f"  {'Engine':<20} {'Source':<8} {'Events':>8} {'MAE':>10}")
            print(f"  {'-'*50}")
            for stat in sorted(accuracy_stats, key=lambda x: x['mae_total'])[:8]:
                print(f"  {stat['engine_name']:<20} {stat['bookmaker'].upper():<8} "
                      f"{stat['n_events']:>8} {stat['mae_total']:>10.4f}")
        else:
            print("  No accuracy statistics available")
        
        # 6. Overall Health
        print("\n[6] OVERALL HEALTH")
        print("-" * 70)
        
        issues = []
        
        if orphaned_calcs > 0:
            issues.append(f"{orphaned_calcs} orphaned calculations")
        if orphaned_snapshots > 0:
            issues.append(f"{orphaned_snapshots} orphaned snapshots")
        if invalid_session_refs > 0:
            issues.append(f"{invalid_session_refs} invalid session references")
        if calcs_without_session > 0:
            issues.append(f"{calcs_without_session} calculations without session ID")
        
        if not issues:
            print("  ✓ All checks passed!")
            print("  ✓ Database is healthy and consistent")
            print("  ✓ scraping_history_id properly populated")
            return_code = 0
        else:
            print("  ⚠ Issues found:")
            for issue in issues:
                print(f"    - {issue}")
            return_code = 1
        
        print("\n" + "=" * 70)
        print("  SANITY CHECK COMPLETE")
        print("=" * 70)
        
        return return_code
        
    finally:
        db.close()


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
