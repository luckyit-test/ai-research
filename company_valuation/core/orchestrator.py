"""
Iteration orchestrator - manages the iterative data collection process.
"""

import asyncio
import logging
from datetime import datetime
from typing import Callable, Optional

from .models import CompanyProfile, IterationResult, ValuationReport

from ..collectors.base import BaseCollector
from ..collectors.website import WebsiteCollector
from ..collectors.whois import WhoisCollector
from ..collectors.social import SocialMediaCollector
from ..collectors.news import NewsCollector
from ..collectors.jobs import JobsCollector
from ..collectors.tech_stack import TechStackCollector
from ..collectors.financial import FinancialCollector

from ..analyzers.valuation import ValuationAnalyzer


class ValuationOrchestrator:
    """Orchestrates the iterative valuation process."""

    def __init__(
        self,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
        report_callback: Optional[Callable[[CompanyProfile, int], None]] = None,
    ):
        """
        Initialize the orchestrator.

        Args:
            progress_callback: Called with (message, current_iteration, total_iterations)
            report_callback: Called after each iteration with (profile, iteration)
        """
        self.logger = logging.getLogger(__name__)
        self.progress_callback = progress_callback
        self.report_callback = report_callback
        self.analyzer = ValuationAnalyzer()

        # Initialize collectors in priority order
        self.collectors: list[BaseCollector] = [
            WebsiteCollector(),
            WhoisCollector(),
            TechStackCollector(),
            SocialMediaCollector(),
            NewsCollector(),
            JobsCollector(),
            FinancialCollector(),
        ]

    async def run(
        self,
        domain: str,
        iterations: int = 3,
        output_dir: str = "./output"
    ) -> ValuationReport:
        """
        Run the full valuation process.

        Args:
            domain: Company domain to analyze
            iterations: Number of collection iterations
            output_dir: Directory for output files

        Returns:
            Complete valuation report
        """
        self._log_progress(f"Starting valuation for {domain}", 0, iterations)

        # Initialize company profile
        profile = CompanyProfile(
            domain=self._clean_domain(domain),
            total_iterations=iterations
        )

        # Initialize report
        report = ValuationReport(company=profile)

        # Run iterations
        for i in range(1, iterations + 1):
            profile.current_iteration = i
            self._log_progress(f"Starting iteration {i}/{iterations}", i, iterations)

            # Run iteration
            iteration_result = await self._run_iteration(profile, i)
            report.iterations.append(iteration_result)

            # Analyze and update valuation
            self._log_progress(f"Analyzing data from iteration {i}", i, iterations)
            profile = self.analyzer.analyze(profile)

            # Report progress
            if self.report_callback:
                self.report_callback(profile, i)

            self._log_progress(
                f"Iteration {i} complete: {iteration_result.data_points_collected} data points",
                i, iterations
            )

        # Final analysis
        self._log_progress("Finalizing valuation", iterations, iterations)
        profile = self.analyzer.analyze(profile)

        # Close all collectors
        await self._close_collectors()

        return report

    async def _run_iteration(
        self, profile: CompanyProfile, iteration: int
    ) -> IterationResult:
        """Run a single collection iteration."""
        result = IterationResult(
            iteration_number=iteration,
            sources_used=[],
            data_points_collected=0,
            new_sources_discovered=[]
        )

        # Determine which collectors to run
        collectors_to_run = [
            c for c in self.collectors
            if c.should_run_on_iteration(iteration)
        ]

        self.logger.info(
            f"Iteration {iteration}: Running {len(collectors_to_run)} collectors"
        )

        # Run collectors concurrently
        tasks = [
            self._run_collector(collector, profile, iteration)
            for collector in collectors_to_run
        ]

        collector_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        for collector, collector_result in zip(collectors_to_run, collector_results):
            if isinstance(collector_result, Exception):
                self.logger.error(
                    f"Collector {collector.name} failed: {collector_result}"
                )
                continue

            data_points, discovered = collector_result

            # Add data points to profile
            for dp in data_points:
                profile.add_data_point(dp)

            result.sources_used.append(collector.name)
            result.data_points_collected += len(data_points)
            result.new_sources_discovered.extend(discovered)

        result.complete()
        return result

    async def _run_collector(
        self, collector: BaseCollector, profile: CompanyProfile, iteration: int
    ) -> tuple[list, list]:
        """Run a single collector and return its results."""
        try:
            self.logger.debug(f"Running collector: {collector.name}")

            # Collect data
            data_points = await collector.collect(profile, iteration)

            # Discover new sources
            discovered = collector.discover_sources(profile)

            self.logger.debug(
                f"{collector.name}: collected {len(data_points)} points, "
                f"discovered {len(discovered)} sources"
            )

            return data_points, discovered

        except Exception as e:
            self.logger.error(f"Error in {collector.name}: {e}")
            raise

    async def _close_collectors(self) -> None:
        """Close all collector sessions."""
        for collector in self.collectors:
            try:
                await collector.close()
            except Exception as e:
                self.logger.warning(f"Error closing {collector.name}: {e}")

    def _clean_domain(self, domain: str) -> str:
        """Clean and normalize domain."""
        domain = domain.lower().strip()

        # Remove protocol
        if domain.startswith("http://"):
            domain = domain[7:]
        elif domain.startswith("https://"):
            domain = domain[8:]

        # Remove www
        if domain.startswith("www."):
            domain = domain[4:]

        # Remove trailing slash and path
        domain = domain.split("/")[0]

        return domain

    def _log_progress(self, message: str, current: int, total: int) -> None:
        """Log progress and call callback if set."""
        self.logger.info(message)
        if self.progress_callback:
            self.progress_callback(message, current, total)


class AsyncValuationRunner:
    """Convenient wrapper for running valuation asynchronously."""

    def __init__(self):
        self.orchestrator = None
        self.report = None

    def run(
        self,
        domain: str,
        iterations: int = 3,
        output_dir: str = "./output",
        progress_callback: Optional[Callable] = None,
        report_callback: Optional[Callable] = None,
    ) -> ValuationReport:
        """Run valuation synchronously."""
        self.orchestrator = ValuationOrchestrator(
            progress_callback=progress_callback,
            report_callback=report_callback
        )

        # Run in event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            self.report = loop.run_until_complete(
                self.orchestrator.run(domain, iterations, output_dir)
            )
            return self.report
        finally:
            loop.close()
