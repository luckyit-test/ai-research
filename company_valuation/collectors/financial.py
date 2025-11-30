"""
Financial data collector - gathers financial information for public companies.
"""

import re
from urllib.parse import quote_plus

from .base import BaseCollector
from ..core.models import CompanyProfile, DataPoint, DataSourceType, ConfidenceLevel


class FinancialCollector(BaseCollector):
    """Collects financial data for companies."""

    source_type = DataSourceType.FINANCIAL
    name = "Financial Data Collector"
    description = "Gathers financial metrics and valuations"
    priority = 3

    async def collect(self, profile: CompanyProfile, iteration: int) -> list[DataPoint]:
        """Collect financial data."""
        data_points = []

        company_name = profile.name or profile.domain.split(".")[0]

        # Try to find stock ticker
        ticker = await self._find_ticker(company_name, profile.domain)

        if ticker:
            data_points.append(self.create_data_point(
                key="stock_ticker",
                value=ticker,
                source_url="market_search",
                confidence=ConfidenceLevel.MEDIUM,
                iteration=iteration
            ))

            # Fetch stock data
            stock_data = await self._fetch_stock_data(ticker)
            for key, value in stock_data.items():
                data_points.append(self.create_data_point(
                    key=key,
                    value=str(value),
                    source_url=f"https://finance.yahoo.com/quote/{ticker}",
                    confidence=ConfidenceLevel.HIGH,
                    iteration=iteration
                ))

        # Check Crunchbase for funding data
        crunchbase_data = await self._fetch_crunchbase_data(company_name, profile.domain)
        for key, value in crunchbase_data.items():
            data_points.append(self.create_data_point(
                key=key,
                value=str(value),
                source_url="https://www.crunchbase.com",
                confidence=ConfidenceLevel.MEDIUM,
                iteration=iteration
            ))

        # Check for funding information in news
        funding_info = self._extract_funding_from_news(profile)
        for key, value in funding_info.items():
            data_points.append(self.create_data_point(
                key=key,
                value=str(value),
                source_url="news_aggregated",
                confidence=ConfidenceLevel.LOW,
                iteration=iteration
            ))

        # Estimate revenue based on available signals
        revenue_estimate = self._estimate_revenue(profile)
        if revenue_estimate:
            data_points.append(self.create_data_point(
                key="estimated_revenue_range",
                value=revenue_estimate,
                source_url="calculated",
                confidence=ConfidenceLevel.LOW,
                iteration=iteration,
                metadata={"method": "signal_based_estimation"}
            ))

        return data_points

    async def _find_ticker(self, company_name: str, domain: str) -> str:
        """Try to find stock ticker for the company."""
        # Yahoo Finance symbol search
        query = quote_plus(company_name)
        url = f"https://query1.finance.yahoo.com/v1/finance/search?q={query}&quotesCount=5"

        data = await self.fetch_json(url)
        if data and "quotes" in data:
            for quote in data["quotes"]:
                # Match by name similarity
                quote_name = quote.get("shortname", "").lower()
                if company_name.lower() in quote_name or quote_name in company_name.lower():
                    return quote.get("symbol", "")

                # Match by domain in longname
                long_name = quote.get("longname", "").lower()
                if domain.split(".")[0] in long_name:
                    return quote.get("symbol", "")

        return ""

    async def _fetch_stock_data(self, ticker: str) -> dict:
        """Fetch stock market data."""
        result = {}

        # Yahoo Finance API
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=1d"
        data = await self.fetch_json(url)

        if data and "chart" in data:
            chart = data["chart"]
            if "result" in chart and chart["result"]:
                meta = chart["result"][0].get("meta", {})

                result["market_cap"] = self._format_large_number(
                    meta.get("marketCap", 0)
                )
                result["current_price"] = meta.get("regularMarketPrice", 0)
                result["currency"] = meta.get("currency", "USD")
                result["exchange"] = meta.get("exchangeName", "")
                result["52_week_high"] = meta.get("fiftyTwoWeekHigh", 0)
                result["52_week_low"] = meta.get("fiftyTwoWeekLow", 0)

        # Get additional quote data
        quote_url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={ticker}"
        quote_data = await self.fetch_json(quote_url)

        if quote_data and "quoteResponse" in quote_data:
            results = quote_data["quoteResponse"].get("result", [])
            if results:
                q = results[0]
                result["pe_ratio"] = q.get("trailingPE", "N/A")
                result["eps"] = q.get("epsTrailingTwelveMonths", "N/A")
                result["dividend_yield"] = q.get("dividendYield", 0)
                result["revenue_ttm"] = self._format_large_number(
                    q.get("totalRevenue", 0)
                )
                result["profit_margin"] = f"{q.get('profitMargins', 0) * 100:.1f}%"

        return result

    async def _fetch_crunchbase_data(self, company_name: str, domain: str) -> dict:
        """Fetch data from Crunchbase (limited without API key)."""
        result = {}

        # Try to access Crunchbase page
        # Note: Crunchbase heavily restricts scraping, so this is limited
        slug = domain.split(".")[0].lower()
        url = f"https://www.crunchbase.com/organization/{slug}"

        html = await self.fetch_url(url)
        if not html:
            return result

        # Try to extract funding information
        funding_patterns = [
            r'"funding_total"\s*:\s*\{[^}]*"value"\s*:\s*(\d+)',
            r'"total_funding_amount"\s*:\s*(\d+)',
            r'Total Funding[^$]*\$([0-9.]+[MB])',
        ]

        for pattern in funding_patterns:
            match = re.search(pattern, html, re.I)
            if match:
                result["total_funding"] = match.group(1)
                break

        # Funding rounds
        rounds_match = re.search(r'"num_funding_rounds"\s*:\s*(\d+)', html)
        if rounds_match:
            result["funding_rounds"] = rounds_match.group(1)

        # Last funding date
        last_round_match = re.search(
            r'"last_funding_type"\s*:\s*"([^"]+)"', html
        )
        if last_round_match:
            result["last_funding_type"] = last_round_match.group(1)

        # Employee count range
        emp_match = re.search(r'"num_employees_enum"\s*:\s*"([^"]+)"', html)
        if emp_match:
            result["employee_range"] = emp_match.group(1)

        # Founded year
        founded_match = re.search(r'"founded_on"\s*:\s*"(\d{4})', html)
        if founded_match:
            result["founded_year"] = founded_match.group(1)

        return result

    def _extract_funding_from_news(self, profile: CompanyProfile) -> dict:
        """Extract funding information from collected news."""
        result = {}

        for dp in profile.data_points:
            if dp.key == "funding_amount" and dp.value:
                result["news_reported_funding"] = dp.value
                break

        return result

    def _estimate_revenue(self, profile: CompanyProfile) -> str:
        """Estimate revenue range based on available signals."""
        # Gather signals
        employee_count = 0
        for dp in profile.data_points:
            if dp.key == "linkedin_employees":
                try:
                    # Handle ranges like "201-500"
                    value = dp.value.replace(",", "")
                    if "-" in value:
                        parts = value.split("-")
                        employee_count = (int(parts[0]) + int(parts[1])) // 2
                    else:
                        employee_count = int(value)
                except ValueError:
                    pass

        if employee_count == 0:
            return ""

        # Industry average revenue per employee
        # Tech: $200-400k, Services: $100-200k, Retail: $150-300k
        # Using average of $200k per employee as baseline
        revenue_per_employee = 200000

        # Adjust based on tech sophistication
        for dp in profile.data_points:
            if dp.key == "tech_sophistication_score":
                try:
                    score = int(dp.value)
                    if score > 70:
                        revenue_per_employee = 350000
                    elif score > 50:
                        revenue_per_employee = 250000
                except ValueError:
                    pass

        estimated_revenue = employee_count * revenue_per_employee
        low = estimated_revenue * 0.6
        high = estimated_revenue * 1.5

        return f"${self._format_large_number(low)} - ${self._format_large_number(high)}"

    def _format_large_number(self, num: float) -> str:
        """Format large numbers with M/B suffixes."""
        if not num or num == 0:
            return "N/A"

        if num >= 1_000_000_000:
            return f"{num / 1_000_000_000:.1f}B"
        elif num >= 1_000_000:
            return f"{num / 1_000_000:.1f}M"
        elif num >= 1_000:
            return f"{num / 1_000:.1f}K"
        else:
            return str(int(num))

    def discover_sources(self, profile: CompanyProfile) -> list[str]:
        """Discover financial data sources."""
        sources = []

        # If we found a ticker, add investor relations page
        for dp in profile.data_points:
            if dp.key == "stock_ticker":
                sources.append(f"https://finance.yahoo.com/quote/{dp.value}")

            if dp.key == "page_investors":
                sources.append(dp.value)

        return sources
