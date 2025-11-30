"""
Valuation analyzer - calculates company valuation based on collected data.
"""

import re
from typing import Optional

from ..core.models import (
    CompanyProfile,
    CompanyMetric,
    ValuationFactor,
    DataSourceType,
    ConfidenceLevel,
)


class ValuationAnalyzer:
    """Analyzes collected data and estimates company valuation."""

    # Industry multipliers for revenue-based valuation
    INDUSTRY_MULTIPLIERS = {
        "technology": {"revenue": 8.0, "ebitda": 20.0},
        "software": {"revenue": 10.0, "ebitda": 25.0},
        "saas": {"revenue": 12.0, "ebitda": 30.0},
        "e-commerce": {"revenue": 3.0, "ebitda": 15.0},
        "fintech": {"revenue": 8.0, "ebitda": 20.0},
        "healthcare": {"revenue": 4.0, "ebitda": 12.0},
        "manufacturing": {"revenue": 1.5, "ebitda": 8.0},
        "retail": {"revenue": 1.0, "ebitda": 6.0},
        "services": {"revenue": 2.0, "ebitda": 10.0},
        "default": {"revenue": 3.0, "ebitda": 10.0},
    }

    # Employee-based valuation ranges
    EMPLOYEE_VALUATION = {
        (1, 10): (500_000, 5_000_000),
        (11, 50): (2_000_000, 20_000_000),
        (51, 200): (10_000_000, 100_000_000),
        (201, 500): (50_000_000, 500_000_000),
        (501, 1000): (200_000_000, 2_000_000_000),
        (1001, 5000): (500_000_000, 10_000_000_000),
        (5001, float("inf")): (2_000_000_000, 100_000_000_000),
    }

    def analyze(self, profile: CompanyProfile) -> CompanyProfile:
        """Perform full analysis and update profile with metrics and valuation."""
        # Calculate metrics
        profile.metrics = self._calculate_metrics(profile)

        # Calculate valuation factors
        profile.valuation_factors = self._calculate_valuation_factors(profile)

        # Estimate valuation
        valuation, valuation_range, confidence = self._estimate_valuation(profile)
        profile.estimated_valuation = valuation
        profile.valuation_range = valuation_range
        profile.confidence_score = confidence

        # Extract key company info
        self._update_company_info(profile)

        return profile

    def _calculate_metrics(self, profile: CompanyProfile) -> list[CompanyMetric]:
        """Calculate all metrics from collected data."""
        metrics = []

        # Web presence metrics
        metrics.extend(self._calculate_web_metrics(profile))

        # Social media metrics
        metrics.extend(self._calculate_social_metrics(profile))

        # Growth metrics
        metrics.extend(self._calculate_growth_metrics(profile))

        # Technology metrics
        metrics.extend(self._calculate_tech_metrics(profile))

        # Financial metrics
        metrics.extend(self._calculate_financial_metrics(profile))

        return metrics

    def _calculate_web_metrics(self, profile: CompanyProfile) -> list[CompanyMetric]:
        """Calculate web presence metrics."""
        metrics = []

        # Domain age score
        domain_age = self._get_data_value(profile, "domain_age_years")
        if domain_age:
            try:
                age = float(domain_age)
                score = min(age * 10, 100)  # 10 points per year, max 100
                metrics.append(CompanyMetric(
                    name="Domain Age Score",
                    value=score,
                    unit="points",
                    category="web_presence",
                    description="Score based on domain registration age",
                    weight=0.5
                ))
            except ValueError:
                pass

        # Has important pages score
        important_pages = ["about", "contact", "careers", "blog", "investors"]
        page_count = sum(
            1 for page in important_pages
            if self._get_data_value(profile, f"page_{page}")
        )
        metrics.append(CompanyMetric(
            name="Website Completeness",
            value=page_count / len(important_pages) * 100,
            unit="percent",
            category="web_presence",
            description="Percentage of important pages present",
            weight=0.3
        ))

        return metrics

    def _calculate_social_metrics(self, profile: CompanyProfile) -> list[CompanyMetric]:
        """Calculate social media metrics."""
        metrics = []

        # Total social followers
        social_platforms = ["linkedin", "twitter", "facebook", "instagram", "github"]
        total_followers = 0

        for platform in social_platforms:
            followers = self._get_data_value(profile, f"{platform}_followers")
            if followers:
                try:
                    total_followers += int(followers.replace(",", ""))
                except ValueError:
                    pass

        if total_followers > 0:
            # Log scale scoring: 1000 = 30 points, 10000 = 50 points, 100000 = 70 points
            import math
            score = min(math.log10(total_followers) * 20, 100)
            metrics.append(CompanyMetric(
                name="Social Media Reach",
                value=score,
                unit="points",
                category="social_presence",
                description=f"Total followers: {total_followers:,}",
                weight=0.6
            ))

        # GitHub activity (for tech companies)
        github_stars = self._get_data_value(profile, "github_total_stars")
        github_repos = self._get_data_value(profile, "github_repos")

        if github_stars or github_repos:
            stars = int(github_stars or 0)
            repos = int(github_repos or 0)

            # Score based on stars and repos
            import math
            tech_score = min((math.log10(max(stars, 1)) * 15) + (repos * 2), 100)
            metrics.append(CompanyMetric(
                name="Open Source Presence",
                value=tech_score,
                unit="points",
                category="social_presence",
                description=f"Stars: {stars:,}, Repos: {repos}",
                weight=0.4
            ))

        return metrics

    def _calculate_growth_metrics(self, profile: CompanyProfile) -> list[CompanyMetric]:
        """Calculate growth-related metrics."""
        metrics = []

        # Job postings as growth indicator
        job_count = self._get_data_value(profile, "total_job_postings")
        if job_count:
            try:
                jobs = int(job_count)
                # More jobs = higher growth signal
                score = min(jobs * 5, 100)
                metrics.append(CompanyMetric(
                    name="Hiring Activity",
                    value=score,
                    unit="points",
                    category="growth",
                    description=f"Active job postings: {jobs}",
                    weight=0.7
                ))
            except ValueError:
                pass

        # Engineering hiring
        eng_jobs = self._get_data_value(profile, "jobs_engineering")
        if eng_jobs:
            try:
                eng = int(eng_jobs)
                metrics.append(CompanyMetric(
                    name="Engineering Growth",
                    value=min(eng * 10, 100),
                    unit="points",
                    category="growth",
                    description=f"Engineering positions: {eng}",
                    weight=0.5
                ))
            except ValueError:
                pass

        # News activity as growth indicator
        recent_news = self._get_data_value(profile, "recent_news_count")
        if recent_news:
            try:
                news = int(recent_news)
                metrics.append(CompanyMetric(
                    name="Media Presence",
                    value=min(news * 10, 100),
                    unit="points",
                    category="growth",
                    description=f"Recent news mentions: {news}",
                    weight=0.4
                ))
            except ValueError:
                pass

        # Funding as growth indicator
        funding = self._get_data_value(profile, "funding_amount")
        if funding:
            metrics.append(CompanyMetric(
                name="Funding Raised",
                value=100,  # Having funding is a strong signal
                unit="points",
                category="growth",
                description=f"Reported funding: {funding}",
                weight=0.8
            ))

        return metrics

    def _calculate_tech_metrics(self, profile: CompanyProfile) -> list[CompanyMetric]:
        """Calculate technology-related metrics."""
        metrics = []

        tech_score = self._get_data_value(profile, "tech_sophistication_score")
        if tech_score:
            try:
                score = int(tech_score)
                metrics.append(CompanyMetric(
                    name="Technology Sophistication",
                    value=score,
                    unit="points",
                    category="technology",
                    description="Score based on technologies used",
                    weight=0.6
                ))
            except ValueError:
                pass

        # SSL and security
        ssl = self._get_data_value(profile, "ssl_enabled")
        if ssl == "true":
            metrics.append(CompanyMetric(
                name="Security Basics",
                value=100,
                unit="points",
                category="technology",
                description="SSL/HTTPS enabled",
                weight=0.3
            ))

        return metrics

    def _calculate_financial_metrics(self, profile: CompanyProfile) -> list[CompanyMetric]:
        """Calculate financial metrics."""
        metrics = []

        # Market cap for public companies
        market_cap = self._get_data_value(profile, "market_cap")
        if market_cap and market_cap != "N/A":
            metrics.append(CompanyMetric(
                name="Market Capitalization",
                value=self._parse_money(market_cap),
                unit="USD",
                category="financial",
                description=f"Market cap: {market_cap}",
                weight=1.0
            ))

        # Revenue
        revenue = self._get_data_value(profile, "revenue_ttm")
        if revenue and revenue != "N/A":
            metrics.append(CompanyMetric(
                name="Annual Revenue",
                value=self._parse_money(revenue),
                unit="USD",
                category="financial",
                description=f"TTM Revenue: {revenue}",
                weight=0.9
            ))

        return metrics

    def _calculate_valuation_factors(self, profile: CompanyProfile) -> list[ValuationFactor]:
        """Calculate valuation factors from metrics."""
        factors = []

        # Group metrics by category
        categories = {}
        for metric in profile.metrics:
            if metric.category not in categories:
                categories[metric.category] = []
            categories[metric.category].append(metric)

        # Calculate factor for each category
        category_weights = {
            "web_presence": 0.10,
            "social_presence": 0.15,
            "growth": 0.25,
            "technology": 0.15,
            "financial": 0.35,
        }

        for category, cat_metrics in categories.items():
            if not cat_metrics:
                continue

            # Weighted average of metrics in category
            total_weight = sum(m.weight for m in cat_metrics)
            if total_weight > 0:
                score = sum(m.value * m.weight for m in cat_metrics) / total_weight
            else:
                score = sum(m.value for m in cat_metrics) / len(cat_metrics)

            factors.append(ValuationFactor(
                name=category.replace("_", " ").title(),
                score=min(score, 100),
                weight=category_weights.get(category, 0.1),
                category=category,
                description=f"Based on {len(cat_metrics)} metrics",
                metrics=cat_metrics
            ))

        return factors

    def _estimate_valuation(
        self, profile: CompanyProfile
    ) -> tuple[float, tuple[float, float], float]:
        """Estimate company valuation."""
        valuations = []
        confidences = []

        # Method 1: Market cap (if public company)
        market_cap = self._get_data_value(profile, "market_cap")
        if market_cap and market_cap != "N/A":
            value = self._parse_money(market_cap)
            if value > 0:
                valuations.append(("market_cap", value, 1.0))
                confidences.append(1.0)

        # Method 2: Revenue multiple
        revenue = self._get_data_value(profile, "revenue_ttm")
        if revenue and revenue != "N/A":
            rev_value = self._parse_money(revenue)
            if rev_value > 0:
                industry = self._detect_industry(profile)
                multiplier = self.INDUSTRY_MULTIPLIERS.get(
                    industry, self.INDUSTRY_MULTIPLIERS["default"]
                )["revenue"]
                valuations.append(("revenue_multiple", rev_value * multiplier, 0.8))
                confidences.append(0.8)

        # Method 3: Employee-based estimation
        employees = self._estimate_employee_count(profile)
        if employees > 0:
            for (low, high), (val_low, val_high) in self.EMPLOYEE_VALUATION.items():
                if low <= employees <= high:
                    mid_val = (val_low + val_high) / 2
                    valuations.append(("employee_based", mid_val, 0.4))
                    confidences.append(0.4)
                    break

        # Method 4: Funding-based (if startup)
        funding = self._get_data_value(profile, "total_funding")
        if not funding:
            funding = self._get_data_value(profile, "news_reported_funding")

        if funding:
            funding_value = self._parse_money(funding)
            if funding_value > 0:
                # Typical post-money valuation is 3-5x last round
                estimated = funding_value * 4
                valuations.append(("funding_based", estimated, 0.5))
                confidences.append(0.5)

        # Calculate weighted average
        if not valuations:
            return 0, (0, 0), 0

        total_weight = sum(v[2] for v in valuations)
        weighted_avg = sum(v[1] * v[2] for v in valuations) / total_weight

        # Calculate range (±30% for uncertainty)
        low_range = weighted_avg * 0.7
        high_range = weighted_avg * 1.3

        # Overall confidence
        confidence = sum(confidences) / len(confidences) if confidences else 0

        return weighted_avg, (low_range, high_range), confidence

    def _detect_industry(self, profile: CompanyProfile) -> str:
        """Detect company industry from collected data."""
        industry = self._get_data_value(profile, "linkedin_industry")
        if industry:
            industry_lower = industry.lower()
            if "software" in industry_lower or "saas" in industry_lower:
                return "saas"
            elif "technology" in industry_lower:
                return "technology"
            elif "fintech" in industry_lower or "financial" in industry_lower:
                return "fintech"
            elif "health" in industry_lower:
                return "healthcare"
            elif "retail" in industry_lower or "e-commerce" in industry_lower:
                return "e-commerce"

        # Detect from tech stack
        for dp in profile.data_points:
            if dp.key.startswith("tech_category_"):
                if "frontend" in dp.value or "backend" in dp.value:
                    return "technology"

        return "default"

    def _estimate_employee_count(self, profile: CompanyProfile) -> int:
        """Estimate employee count from various sources."""
        # LinkedIn employees
        linkedin_emp = self._get_data_value(profile, "linkedin_employees")
        if linkedin_emp:
            try:
                value = linkedin_emp.replace(",", "")
                if "-" in value:
                    parts = value.split("-")
                    return (int(parts[0]) + int(parts[1])) // 2
                return int(value)
            except ValueError:
                pass

        # Employee range from Crunchbase
        emp_range = self._get_data_value(profile, "employee_range")
        if emp_range:
            # Parse ranges like "c_00051_00100"
            match = re.search(r"(\d+).*?(\d+)", emp_range)
            if match:
                return (int(match.group(1)) + int(match.group(2))) // 2

        return 0

    def _update_company_info(self, profile: CompanyProfile) -> None:
        """Update profile with extracted company information."""
        # Company name
        if not profile.name:
            profile.name = self._get_data_value(profile, "company_name")

        # Industry
        if not profile.industry:
            profile.industry = self._get_data_value(profile, "linkedin_industry")

        # Headquarters
        if not profile.headquarters:
            profile.headquarters = self._get_data_value(profile, "linkedin_headquarters")

        # Employee count
        if not profile.employee_count:
            emp = self._estimate_employee_count(profile)
            if emp > 0:
                profile.employee_count = str(emp)

        # Founded year
        if not profile.founded_year:
            founded = self._get_data_value(profile, "founded_year")
            if founded:
                try:
                    profile.founded_year = int(founded)
                except ValueError:
                    pass

    def _get_data_value(self, profile: CompanyProfile, key: str) -> Optional[str]:
        """Get the most recent value for a data point key."""
        for dp in reversed(profile.data_points):
            if dp.key == key:
                return dp.value
        return None

    def _parse_money(self, value: str) -> float:
        """Parse money string to float."""
        if not value or value == "N/A":
            return 0

        value = value.replace("$", "").replace(",", "").strip()

        multipliers = {
            "T": 1_000_000_000_000,
            "B": 1_000_000_000,
            "M": 1_000_000,
            "K": 1_000,
        }

        for suffix, mult in multipliers.items():
            if value.upper().endswith(suffix):
                try:
                    return float(value[:-1]) * mult
                except ValueError:
                    return 0

        try:
            return float(value)
        except ValueError:
            return 0

    def format_valuation(self, value: float) -> str:
        """Format valuation for display."""
        if value >= 1_000_000_000:
            return f"${value / 1_000_000_000:.1f}B"
        elif value >= 1_000_000:
            return f"${value / 1_000_000:.1f}M"
        elif value >= 1_000:
            return f"${value / 1_000:.1f}K"
        else:
            return f"${value:.0f}"
