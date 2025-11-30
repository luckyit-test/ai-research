"""
Social media collector - gathers data from social platforms.
"""

import re
from urllib.parse import urlparse

from .base import BaseCollector
from ..core.models import CompanyProfile, DataPoint, DataSourceType, ConfidenceLevel


class SocialMediaCollector(BaseCollector):
    """Collects data from social media platforms."""

    source_type = DataSourceType.SOCIAL_MEDIA
    name = "Social Media Analyzer"
    description = "Analyzes company presence on social media platforms"
    priority = 2

    async def collect(self, profile: CompanyProfile, iteration: int) -> list[DataPoint]:
        """Collect social media data."""
        data_points = []

        # Get social URLs from website data
        social_urls = {}
        for dp in profile.data_points:
            if dp.key.startswith("social_"):
                platform = dp.key.replace("social_", "")
                social_urls[platform] = dp.value

        # If no social links found, try to discover them
        if not social_urls:
            social_urls = await self._discover_social_profiles(profile.domain)

        for platform, url in social_urls.items():
            platform_data = await self._analyze_platform(platform, url, iteration)
            data_points.extend(platform_data)

        return data_points

    async def _discover_social_profiles(self, domain: str) -> dict[str, str]:
        """Try to discover social profiles based on domain name."""
        company_name = domain.split(".")[0]
        discovered = {}

        # Common social URL patterns
        platforms = {
            "linkedin": f"https://www.linkedin.com/company/{company_name}",
            "twitter": f"https://twitter.com/{company_name}",
            "facebook": f"https://www.facebook.com/{company_name}",
            "instagram": f"https://www.instagram.com/{company_name}",
            "github": f"https://github.com/{company_name}",
        }

        for platform, url in platforms.items():
            # Quick check if profile exists
            html = await self.fetch_url(url)
            if html and not self._is_404_page(html):
                discovered[platform] = url

        return discovered

    def _is_404_page(self, html: str) -> bool:
        """Check if page is a 404 error page."""
        indicators = [
            "page not found",
            "404",
            "doesn't exist",
            "не найдена",
            "this page isn't available",
            "sorry, this page",
        ]
        html_lower = html.lower()
        return any(ind in html_lower for ind in indicators)

    async def _analyze_platform(
        self, platform: str, url: str, iteration: int
    ) -> list[DataPoint]:
        """Analyze a specific social media platform."""
        data_points = []

        if platform == "linkedin":
            data_points.extend(await self._analyze_linkedin(url, iteration))
        elif platform == "twitter":
            data_points.extend(await self._analyze_twitter(url, iteration))
        elif platform == "facebook":
            data_points.extend(await self._analyze_facebook(url, iteration))
        elif platform == "github":
            data_points.extend(await self._analyze_github(url, iteration))
        elif platform == "instagram":
            data_points.extend(await self._analyze_instagram(url, iteration))

        return data_points

    async def _analyze_linkedin(self, url: str, iteration: int) -> list[DataPoint]:
        """Analyze LinkedIn company page."""
        data_points = []
        html = await self.fetch_url(url)

        if not html:
            return data_points

        # Try to extract follower count
        follower_patterns = [
            r'"followerCount"\s*:\s*(\d+)',
            r'(\d[\d,]+)\s*followers',
            r'(\d+)\s*follower',
        ]

        for pattern in follower_patterns:
            match = re.search(pattern, html, re.I)
            if match:
                followers = match.group(1).replace(",", "")
                data_points.append(self.create_data_point(
                    key="linkedin_followers",
                    value=followers,
                    source_url=url,
                    confidence=ConfidenceLevel.MEDIUM,
                    iteration=iteration
                ))
                break

        # Try to extract employee count
        employee_patterns = [
            r'"staffCount"\s*:\s*(\d+)',
            r'(\d[\d,]+(?:-\d[\d,]+)?)\s*employees',
            r'(\d[\d,]+)\s*associated members',
        ]

        for pattern in employee_patterns:
            match = re.search(pattern, html, re.I)
            if match:
                employees = match.group(1)
                data_points.append(self.create_data_point(
                    key="linkedin_employees",
                    value=employees,
                    source_url=url,
                    confidence=ConfidenceLevel.MEDIUM,
                    iteration=iteration
                ))
                break

        # Industry
        industry_match = re.search(r'"industry"\s*:\s*"([^"]+)"', html)
        if industry_match:
            data_points.append(self.create_data_point(
                key="linkedin_industry",
                value=industry_match.group(1),
                source_url=url,
                confidence=ConfidenceLevel.MEDIUM,
                iteration=iteration
            ))

        # Headquarters
        hq_match = re.search(r'"headquarter"\s*:\s*\{[^}]*"city"\s*:\s*"([^"]+)"', html)
        if hq_match:
            data_points.append(self.create_data_point(
                key="linkedin_headquarters",
                value=hq_match.group(1),
                source_url=url,
                confidence=ConfidenceLevel.MEDIUM,
                iteration=iteration
            ))

        return data_points

    async def _analyze_twitter(self, url: str, iteration: int) -> list[DataPoint]:
        """Analyze Twitter profile."""
        data_points = []

        # Handle x.com redirect
        if "x.com" not in url:
            url = url.replace("twitter.com", "x.com")

        html = await self.fetch_url(url)
        if not html:
            return data_points

        # Follower count
        follower_match = re.search(r'"followers_count"\s*:\s*(\d+)', html)
        if follower_match:
            data_points.append(self.create_data_point(
                key="twitter_followers",
                value=follower_match.group(1),
                source_url=url,
                confidence=ConfidenceLevel.MEDIUM,
                iteration=iteration
            ))

        # Tweet count
        tweet_match = re.search(r'"statuses_count"\s*:\s*(\d+)', html)
        if tweet_match:
            data_points.append(self.create_data_point(
                key="twitter_tweets",
                value=tweet_match.group(1),
                source_url=url,
                confidence=ConfidenceLevel.MEDIUM,
                iteration=iteration
            ))

        # Verified status
        verified = '"verified":true' in html.lower() or '"is_blue_verified":true' in html.lower()
        data_points.append(self.create_data_point(
            key="twitter_verified",
            value=str(verified),
            source_url=url,
            confidence=ConfidenceLevel.HIGH,
            iteration=iteration
        ))

        return data_points

    async def _analyze_facebook(self, url: str, iteration: int) -> list[DataPoint]:
        """Analyze Facebook page."""
        data_points = []
        html = await self.fetch_url(url)

        if not html:
            return data_points

        # Page likes
        likes_match = re.search(r'(\d[\d,]+)\s*people\s*like\s*this', html, re.I)
        if likes_match:
            data_points.append(self.create_data_point(
                key="facebook_likes",
                value=likes_match.group(1).replace(",", ""),
                source_url=url,
                confidence=ConfidenceLevel.MEDIUM,
                iteration=iteration
            ))

        # Followers
        followers_match = re.search(r'(\d[\d,]+)\s*people\s*follow', html, re.I)
        if followers_match:
            data_points.append(self.create_data_point(
                key="facebook_followers",
                value=followers_match.group(1).replace(",", ""),
                source_url=url,
                confidence=ConfidenceLevel.MEDIUM,
                iteration=iteration
            ))

        return data_points

    async def _analyze_github(self, url: str, iteration: int) -> list[DataPoint]:
        """Analyze GitHub organization."""
        data_points = []

        # Parse org name
        parsed = urlparse(url)
        org_name = parsed.path.strip("/").split("/")[0]

        # Use GitHub API
        api_url = f"https://api.github.com/orgs/{org_name}"
        data = await self.fetch_json(api_url)

        if data:
            if "public_repos" in data:
                data_points.append(self.create_data_point(
                    key="github_repos",
                    value=str(data["public_repos"]),
                    source_url=url,
                    confidence=ConfidenceLevel.HIGH,
                    iteration=iteration
                ))

            if "followers" in data:
                data_points.append(self.create_data_point(
                    key="github_followers",
                    value=str(data["followers"]),
                    source_url=url,
                    confidence=ConfidenceLevel.HIGH,
                    iteration=iteration
                ))

            if "blog" in data and data["blog"]:
                data_points.append(self.create_data_point(
                    key="github_blog",
                    value=data["blog"],
                    source_url=url,
                    confidence=ConfidenceLevel.HIGH,
                    iteration=iteration
                ))

            if "description" in data and data["description"]:
                data_points.append(self.create_data_point(
                    key="github_description",
                    value=data["description"],
                    source_url=url,
                    confidence=ConfidenceLevel.HIGH,
                    iteration=iteration
                ))

        # Get popular repos
        repos_url = f"https://api.github.com/orgs/{org_name}/repos?sort=stars&per_page=5"
        repos = await self.fetch_json(repos_url)

        if repos and isinstance(repos, list):
            total_stars = sum(r.get("stargazers_count", 0) for r in repos)
            data_points.append(self.create_data_point(
                key="github_total_stars",
                value=str(total_stars),
                source_url=url,
                confidence=ConfidenceLevel.HIGH,
                iteration=iteration
            ))

            languages = set()
            for repo in repos:
                if repo.get("language"):
                    languages.add(repo["language"])

            if languages:
                data_points.append(self.create_data_point(
                    key="github_languages",
                    value=", ".join(languages),
                    source_url=url,
                    confidence=ConfidenceLevel.HIGH,
                    iteration=iteration
                ))

        return data_points

    async def _analyze_instagram(self, url: str, iteration: int) -> list[DataPoint]:
        """Analyze Instagram profile."""
        data_points = []
        html = await self.fetch_url(url)

        if not html:
            return data_points

        # Followers
        followers_match = re.search(r'"edge_followed_by"\s*:\s*\{\s*"count"\s*:\s*(\d+)', html)
        if followers_match:
            data_points.append(self.create_data_point(
                key="instagram_followers",
                value=followers_match.group(1),
                source_url=url,
                confidence=ConfidenceLevel.MEDIUM,
                iteration=iteration
            ))

        # Posts
        posts_match = re.search(r'"edge_owner_to_timeline_media"\s*:\s*\{\s*"count"\s*:\s*(\d+)', html)
        if posts_match:
            data_points.append(self.create_data_point(
                key="instagram_posts",
                value=posts_match.group(1),
                source_url=url,
                confidence=ConfidenceLevel.MEDIUM,
                iteration=iteration
            ))

        return data_points

    def discover_sources(self, profile: CompanyProfile) -> list[str]:
        """Discover additional sources from social data."""
        sources = []

        for dp in profile.get_data_by_source(self.source_type):
            # GitHub blog can be a source
            if dp.key == "github_blog" and dp.value:
                sources.append(dp.value)

        return sources
