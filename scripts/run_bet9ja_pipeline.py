import sys
from pathlib import Path
import asyncio

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.unified_scraper import UnifiedScraper

async def main():
    scraper = UnifiedScraper()
    # Run only Bet9ja scraping in the unified pipeline
    await scraper.run(scrape_sporty=False, scrape_pawa=False, run_engines=False)

if __name__ == '__main__':
    asyncio.run(main())
