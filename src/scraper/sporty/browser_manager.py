"""
Shared Browser Manager for Sportybet scrapers.

This module provides a singleton browser instance that can be shared
across multiple scrapers to reduce startup overhead.
"""

import asyncio
import logging
from typing import Optional

from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright

logger = logging.getLogger(__name__)

# Default pool size for parallel page operations
DEFAULT_PAGE_POOL_SIZE = 4

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"


class SharedBrowserManager:
    """
    Manages a shared browser instance for all Sportybet scrapers.
    
    Usage:
        async with SharedBrowserManager() as browser_manager:
            # Create pages for different tasks
            events_page = await browser_manager.new_page()
            markets_page = await browser_manager.new_page()
    """

    def __init__(self, headless: bool = True, timeout: int = 30000):
        """
        Initialize the browser manager.
        
        Args:
            headless: Run browser in headless mode
            timeout: Default page timeout in milliseconds
        """
        self.headless = headless
        self.timeout = timeout
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._pages: list[Page] = []
        
        # Page pool for parallel operations
        self._page_pool: list[Page] = []
        self._pool_lock = asyncio.Lock()
        self._pool_available = asyncio.Condition()
        self._pool_size = DEFAULT_PAGE_POOL_SIZE

    async def __aenter__(self):
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    async def start(self):
        """Start the browser."""
        if self._browser:
            return  # Already started
            
        logger.info("Starting shared browser...")
        self._playwright = await async_playwright().start()
        
        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ],
        )
        
        self._context = await self._browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=USER_AGENT,
            locale="en-US",
            timezone_id="Africa/Lagos",
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "clientid": "web",
                "operid": "2",
                "platform": "web",
            },
        )
        
        logger.info("Shared browser started successfully")

    async def new_page(self) -> Page:
        """
        Create a new page in the shared browser context.
        
        Returns:
            A new Page instance
        """
        if not self._context:
            raise RuntimeError("Browser not started. Call start() first.")
        
        page = await self._context.new_page()
        page.set_default_timeout(self.timeout)
        self._pages.append(page)
        return page

    async def close_page(self, page: Page):
        """Close a specific page."""
        if page in self._pages:
            self._pages.remove(page)
            await page.close()

    async def create_page_pool(self, size: int = DEFAULT_PAGE_POOL_SIZE):
        """
        Create a pool of pages for parallel operations.
        
        Args:
            size: Number of pages in the pool
        """
        if not self._context:
            raise RuntimeError("Browser not started. Call start() first.")
        
        self._pool_size = size
        logger.info(f"Creating page pool with {size} pages...")
        
        for i in range(size):
            page = await self._context.new_page()
            page.set_default_timeout(self.timeout)
            self._page_pool.append(page)
            self._pages.append(page)
        
        logger.info(f"Page pool ready with {len(self._page_pool)} pages")

    async def acquire_page(self) -> Page:
        """
        Acquire a page from the pool. Blocks if no pages available.
        
        Returns:
            A Page instance from the pool
        """
        async with self._pool_available:
            while not self._page_pool:
                await self._pool_available.wait()
            
            page = self._page_pool.pop()
            return page

    async def release_page(self, page: Page):
        """
        Release a page back to the pool.
        
        Args:
            page: The page to return to the pool
        """
        async with self._pool_available:
            self._page_pool.append(page)
            self._pool_available.notify()

    @property
    def pool_size(self) -> int:
        """Get the page pool size."""
        return self._pool_size

    async def close(self):
        """Close the browser and cleanup all resources."""
        logger.info("Closing shared browser...")
        
        # Close all pages
        for page in self._pages:
            try:
                await page.close()
            except Exception:
                pass
        self._pages.clear()
        
        # Close context and browser
        if self._context:
            await self._context.close()
            self._context = None
            
        if self._browser:
            await self._browser.close()
            self._browser = None
            
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
            
        logger.info("Shared browser closed")

    @property
    def browser(self) -> Optional[Browser]:
        """Get the underlying browser instance."""
        return self._browser

    @property
    def context(self) -> Optional[BrowserContext]:
        """Get the browser context."""
        return self._context

    @property
    def is_running(self) -> bool:
        """Check if browser is running."""
        return self._browser is not None
