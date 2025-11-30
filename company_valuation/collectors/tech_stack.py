"""
Tech stack collector - analyzes technologies used by the company.
"""

import re
from urllib.parse import urlparse

from .base import BaseCollector
from ..core.models import CompanyProfile, DataPoint, DataSourceType, ConfidenceLevel


class TechStackCollector(BaseCollector):
    """Collects technology stack information."""

    source_type = DataSourceType.TECH_STACK
    name = "Technology Stack Analyzer"
    description = "Analyzes technologies and infrastructure used"
    priority = 1

    # Known technology signatures
    TECH_SIGNATURES = {
        # Frontend frameworks
        "react": [r"react", r"_react", r"__REACT"],
        "vue": [r"vue\.js", r"__vue__", r"v-bind"],
        "angular": [r"angular", r"ng-", r"ng\."],
        "svelte": [r"svelte"],
        "next.js": [r"__NEXT_DATA__", r"_next"],
        "nuxt": [r"__NUXT__"],

        # Backend
        "node.js": [r"express", r"node"],
        "django": [r"csrfmiddlewaretoken", r"django"],
        "rails": [r"rails", r"csrf-token"],
        "laravel": [r"laravel"],
        "asp.net": [r"__VIEWSTATE", r"asp\.net"],

        # CMS/Platforms
        "wordpress": [r"wp-content", r"wp-includes"],
        "shopify": [r"shopify", r"cdn\.shopify"],
        "wix": [r"wix\.com", r"wixstatic"],
        "squarespace": [r"squarespace"],
        "webflow": [r"webflow"],

        # Analytics/Marketing
        "google analytics": [r"google-analytics", r"gtag", r"ga\.js"],
        "google tag manager": [r"googletagmanager"],
        "facebook pixel": [r"fbq", r"facebook.*pixel"],
        "hotjar": [r"hotjar"],
        "mixpanel": [r"mixpanel"],
        "amplitude": [r"amplitude"],
        "segment": [r"segment\.com", r"analytics\.js"],
        "hubspot": [r"hubspot", r"hs-scripts"],

        # Infrastructure
        "cloudflare": [r"cloudflare", r"cf-ray"],
        "aws": [r"amazonaws\.com", r"aws"],
        "google cloud": [r"googleapis\.com", r"gstatic"],
        "azure": [r"azure", r"microsoftonline"],
        "vercel": [r"vercel", r"\.now\.sh"],
        "netlify": [r"netlify"],
        "heroku": [r"heroku"],

        # Other services
        "stripe": [r"stripe\.com", r"stripe\.js"],
        "intercom": [r"intercom"],
        "zendesk": [r"zendesk"],
        "drift": [r"drift\.com"],
        "crisp": [r"crisp\.chat"],
        "sentry": [r"sentry\.io", r"sentry"],
        "datadog": [r"datadoghq"],

        # A/B Testing
        "optimizely": [r"optimizely"],
        "vwo": [r"visualwebsiteoptimizer"],

        # CDN
        "fastly": [r"fastly"],
        "akamai": [r"akamai"],
        "cloudfront": [r"cloudfront\.net"],
    }

    async def collect(self, profile: CompanyProfile, iteration: int) -> list[DataPoint]:
        """Collect technology stack data."""
        data_points = []
        base_url = f"https://{profile.domain}"

        html = await self.fetch_url(base_url)
        if not html:
            base_url = f"http://{profile.domain}"
            html = await self.fetch_url(base_url)

        if html:
            # Detect technologies from HTML
            detected_tech = self._detect_technologies(html)

            for tech, confidence in detected_tech.items():
                data_points.append(self.create_data_point(
                    key=f"tech_{tech.replace(' ', '_').replace('.', '_')}",
                    value="detected",
                    source_url=base_url,
                    confidence=confidence,
                    iteration=iteration
                ))

            # Categorize detected technologies
            categories = self._categorize_technologies(detected_tech)
            for category, techs in categories.items():
                if techs:
                    data_points.append(self.create_data_point(
                        key=f"tech_category_{category}",
                        value=", ".join(techs),
                        source_url=base_url,
                        confidence=ConfidenceLevel.MEDIUM,
                        iteration=iteration
                    ))

            # Calculate technology sophistication score
            score = self._calculate_tech_score(detected_tech)
            data_points.append(self.create_data_point(
                key="tech_sophistication_score",
                value=str(score),
                source_url=base_url,
                confidence=ConfidenceLevel.MEDIUM,
                iteration=iteration
            ))

            # Check SSL/Security
            ssl_info = await self._check_ssl(profile.domain)
            for key, value in ssl_info.items():
                data_points.append(self.create_data_point(
                    key=key,
                    value=value,
                    source_url=base_url,
                    confidence=ConfidenceLevel.HIGH,
                    iteration=iteration
                ))

            # Check DNS records
            dns_info = await self._analyze_dns(profile.domain)
            for key, value in dns_info.items():
                data_points.append(self.create_data_point(
                    key=key,
                    value=value,
                    source_url=f"dns://{profile.domain}",
                    confidence=ConfidenceLevel.HIGH,
                    iteration=iteration
                ))

        # Check BuiltWith or similar services
        builtwith_data = await self._fetch_builtwith(profile.domain)
        for key, value in builtwith_data.items():
            data_points.append(self.create_data_point(
                key=key,
                value=value,
                source_url=f"https://builtwith.com/{profile.domain}",
                confidence=ConfidenceLevel.MEDIUM,
                iteration=iteration
            ))

        return data_points

    def _detect_technologies(self, html: str) -> dict[str, ConfidenceLevel]:
        """Detect technologies from HTML content."""
        detected = {}

        for tech, patterns in self.TECH_SIGNATURES.items():
            for pattern in patterns:
                if re.search(pattern, html, re.I):
                    detected[tech] = ConfidenceLevel.HIGH
                    break

        return detected

    def _categorize_technologies(self, techs: dict) -> dict[str, list[str]]:
        """Categorize detected technologies."""
        categories = {
            "frontend": ["react", "vue", "angular", "svelte", "next.js", "nuxt"],
            "backend": ["node.js", "django", "rails", "laravel", "asp.net"],
            "cms": ["wordpress", "shopify", "wix", "squarespace", "webflow"],
            "analytics": ["google analytics", "google tag manager", "mixpanel", "amplitude", "segment", "hotjar"],
            "infrastructure": ["cloudflare", "aws", "google cloud", "azure", "vercel", "netlify", "heroku"],
            "payments": ["stripe"],
            "customer_support": ["intercom", "zendesk", "drift", "crisp"],
            "monitoring": ["sentry", "datadog"],
            "marketing": ["facebook pixel", "hubspot"],
        }

        result = {}
        for category, category_techs in categories.items():
            found = [t for t in techs.keys() if t in category_techs]
            if found:
                result[category] = found

        return result

    def _calculate_tech_score(self, techs: dict) -> int:
        """Calculate technology sophistication score (0-100)."""
        score = 0

        # Modern frontend framework
        if any(t in techs for t in ["react", "vue", "angular", "svelte", "next.js"]):
            score += 20

        # Cloud infrastructure
        if any(t in techs for t in ["aws", "google cloud", "azure", "vercel"]):
            score += 15

        # CDN usage
        if any(t in techs for t in ["cloudflare", "fastly", "akamai", "cloudfront"]):
            score += 10

        # Analytics
        if any(t in techs for t in ["google analytics", "mixpanel", "amplitude", "segment"]):
            score += 10

        # Professional payments
        if "stripe" in techs:
            score += 10

        # Customer support tools
        if any(t in techs for t in ["intercom", "zendesk", "drift"]):
            score += 10

        # Monitoring
        if any(t in techs for t in ["sentry", "datadog"]):
            score += 10

        # Marketing automation
        if any(t in techs for t in ["hubspot", "segment"]):
            score += 10

        # Not using basic CMS (WordPress without customization)
        if "wordpress" not in techs and "wix" not in techs:
            score += 5

        return min(score, 100)

    async def _check_ssl(self, domain: str) -> dict[str, str]:
        """Check SSL certificate information."""
        result = {}

        # Check if HTTPS works
        url = f"https://{domain}"
        html = await self.fetch_url(url)

        result["ssl_enabled"] = "true" if html else "false"

        return result

    async def _analyze_dns(self, domain: str) -> dict[str, str]:
        """Analyze DNS configuration."""
        result = {}

        # Check for common DNS patterns
        # This would typically use DNS queries, but we'll infer from headers/content

        # Check for email providers (MX records inference)
        common_email_providers = {
            "google": "Google Workspace",
            "outlook": "Microsoft 365",
            "zoho": "Zoho Mail",
        }

        return result

    async def _fetch_builtwith(self, domain: str) -> dict[str, str]:
        """Fetch data from BuiltWith or similar service."""
        result = {}

        # Try to get basic info from BuiltWith free tier
        url = f"https://api.builtwith.com/free1/api.json?KEY=&LOOKUP={domain}"
        data = await self.fetch_json(url)

        if data and isinstance(data, dict):
            groups = data.get("groups", [])
            for group in groups:
                categories = group.get("categories", [])
                for cat in categories:
                    cat_name = cat.get("name", "").lower().replace(" ", "_")
                    techs = [t.get("name", "") for t in cat.get("live", [])]
                    if techs:
                        result[f"builtwith_{cat_name}"] = ", ".join(techs[:5])

        return result

    def discover_sources(self, profile: CompanyProfile) -> list[str]:
        """Discover sources from tech stack analysis."""
        sources = []

        # If company uses GitHub, check their repos
        for dp in profile.data_points:
            if dp.key == "social_github" and dp.value:
                sources.append(dp.value)

        return sources
