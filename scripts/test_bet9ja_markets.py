#!/usr/bin/env python
"""
Test script: scrape Bet9ja events + markets for a configured tournament and
verify markets were upserted into the database.

Usage:
  .venv\Scripts\python.exe scripts/test_bet9ja_markets.py
"""
import asyncio
import logging
import sys
from pathlib import Path

# Ensure project root is on sys.path so `src` package can be imported
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.unified_scraper import UnifiedScraper


async def main():
    logging.basicConfig(level=logging.INFO)

    scraper = UnifiedScraper()
    # Connect DB
    scraper.db.connect()

    # Find a tournament with bet9ja_group_id
    tournaments = scraper.config.get_enabled_tournaments()
    tour = None
    for t in tournaments:
        if t.get("bet9ja_group_id"):
            tour = t
            break

    if not tour:
        print("No configured tournament with bet9ja_group_id found in config/tournaments.yaml")
        return

    print(f"Testing Bet9ja scraping for tournament: {tour['name']} (group {tour.get('bet9ja_group_id')})")

    # Run the Bet9ja scraper flow for this tournament (force=True to ensure markets are fetched)
    await scraper._scrape_bet9ja(tour, force=True)

    # Query DB for events from this group
    conn = scraper.db.conn
    cur = conn.cursor()
    group_id = str(tour.get('bet9ja_group_id'))
    cur.execute("SELECT sportradar_id, bet9ja_event_id FROM events WHERE bet9ja_group_id = ?", (group_id,))
    rows = cur.fetchall()

    print(f"Events recorded in DB for Bet9ja group {group_id}: {len(rows)}")

    for r in rows:
        sportradar_id = r[0]
        bet9ja_event_id = r[1]

        cur.execute(
            "SELECT market_name, specifier, bet9ja_outcome_1_name, bet9ja_outcome_1_odds, bet9ja_outcome_2_name, bet9ja_outcome_2_odds, bet9ja_outcome_3_name, bet9ja_outcome_3_odds FROM markets WHERE sportradar_id = ?",
            (sportradar_id,)
        )
        mrows = cur.fetchall()
        print(f"\nEvent {sportradar_id} (bet9ja_event {bet9ja_event_id}): {len(mrows)} market rows with Bet9ja data")

        # Print a sample of markets
        for m in mrows[:40]:
            print("  ", m[0], "| spec:", m[1], "|", m[2], m[3], "|", m[4], m[5], "|", m[6], m[7])

    print("\nTest complete.")


if __name__ == '__main__':
    asyncio.run(main())
