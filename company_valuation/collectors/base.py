"""
Base collector class for all data collectors.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Optional

import aiohttp

from ..core.models import CompanyProfile, DataPoint, DataSourceType, ConfidenceLevel


class BaseCollector(ABC):
    """Abstract base class for all data collectors."""

    source_type: DataSourceType
    name: str = "Base Collector"
    description: str = ""
    priority: int = 1  # Lower = higher priority for first iteration

    def __init__(self, timeout: int = 30, max_retries: int = 3):
        self.timeout = timeout
        self.max_retries = max_retries
        self.logger = logging.getLogger(self.__class__.__name__)
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                }
            )
        return self._session

    async def close(self) -> None:
        """Close the session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def fetch_url(self, url: str) -> Optional[str]:
        """Fetch content from URL with retries."""
        session = await self._get_session()

        for attempt in range(self.max_retries):
            try:
                async with session.get(url) as response:
                    if response.status == 200:
                        return await response.text()
                    self.logger.warning(f"HTTP {response.status} for {url}")
            except asyncio.TimeoutError:
                self.logger.warning(f"Timeout fetching {url}, attempt {attempt + 1}")
            except aiohttp.ClientError as e:
                self.logger.warning(f"Error fetching {url}: {e}")

            if attempt < self.max_retries - 1:
                await asyncio.sleep(2 ** attempt)  # Exponential backoff

        return None

    async def fetch_json(self, url: str) -> Optional[dict]:
        """Fetch JSON from URL with retries."""
        session = await self._get_session()

        for attempt in range(self.max_retries):
            try:
                async with session.get(url) as response:
                    if response.status == 200:
                        return await response.json()
                    self.logger.warning(f"HTTP {response.status} for {url}")
            except asyncio.TimeoutError:
                self.logger.warning(f"Timeout fetching {url}, attempt {attempt + 1}")
            except aiohttp.ClientError as e:
                self.logger.warning(f"Error fetching {url}: {e}")

            if attempt < self.max_retries - 1:
                await asyncio.sleep(2 ** attempt)

        return None

    def create_data_point(
        self,
        key: str,
        value: str,
        source_url: str,
        confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM,
        iteration: int = 1,
        metadata: dict = None
    ) -> DataPoint:
        """Create a data point with this collector's source type."""
        return DataPoint(
            source_type=self.source_type,
            source_url=source_url,
            key=key,
            value=value,
            confidence=confidence,
            iteration=iteration,
            metadata=metadata or {}
        )

    @abstractmethod
    async def collect(self, profile: CompanyProfile, iteration: int) -> list[DataPoint]:
        """
        Collect data for the company.

        Args:
            profile: Current company profile with existing data
            iteration: Current iteration number

        Returns:
            List of collected data points
        """
        pass

    @abstractmethod
    def discover_sources(self, profile: CompanyProfile) -> list[str]:
        """
        Discover new data sources based on collected data.

        Args:
            profile: Current company profile

        Returns:
            List of discovered source URLs or identifiers
        """
        pass

    def should_run_on_iteration(self, iteration: int) -> bool:
        """
        Determine if this collector should run on the given iteration.

        By default, collectors with priority <= iteration run.
        """
        return self.priority <= iteration

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(source_type={self.source_type})"
