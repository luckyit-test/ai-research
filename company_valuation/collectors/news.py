"""
News collector - gathers news and press releases about the company.
"""

import re
from datetime import datetime, timedelta
from urllib.parse import quote_plus

from .base import BaseCollector
from ..core.models import CompanyProfile, DataPoint, DataSourceType, ConfidenceLevel


class NewsCollector(BaseCollector):
    """Collects news and press mentions about the company."""

    source_type = DataSourceType.NEWS
    name = "News & Press Collector"
    description = "Gathers news articles and press releases"
    priority = 2

    async def collect(self, profile: CompanyProfile, iteration: int) -> list[DataPoint]:
        """Collect news data."""
        data_points = []

        company_name = profile.name or profile.domain.split(".")[0]

        # Search multiple news sources
        news_items = []

        # Google News (via RSS)
        google_news = await self._fetch_google_news(company_name)
        news_items.extend(google_news)

        # Hacker News (for tech companies)
        hn_items = await self._fetch_hacker_news(company_name, profile.domain)
        news_items.extend(hn_items)

        # Analyze news sentiment and topics
        if news_items:
            data_points.append(self.create_data_point(
                key="news_count",
                value=str(len(news_items)),
                source_url="aggregated",
                confidence=ConfidenceLevel.HIGH,
                iteration=iteration
            ))

            # Recent news (last 30 days)
            recent_cutoff = datetime.now() - timedelta(days=30)
            recent_news = [n for n in news_items if n.get("date") and n["date"] > recent_cutoff]
            data_points.append(self.create_data_point(
                key="recent_news_count",
                value=str(len(recent_news)),
                source_url="aggregated",
                confidence=ConfidenceLevel.MEDIUM,
                iteration=iteration
            ))

            # Extract topics/keywords
            topics = self._extract_topics(news_items)
            if topics:
                data_points.append(self.create_data_point(
                    key="news_topics",
                    value=", ".join(topics[:10]),
                    source_url="aggregated",
                    confidence=ConfidenceLevel.MEDIUM,
                    iteration=iteration
                ))

            # Check for funding news
            funding_news = [
                n for n in news_items
                if any(kw in n.get("title", "").lower()
                       for kw in ["funding", "raised", "investment", "series", "инвестици", "раунд"])
            ]
            if funding_news:
                data_points.append(self.create_data_point(
                    key="funding_mentions",
                    value=str(len(funding_news)),
                    source_url="aggregated",
                    confidence=ConfidenceLevel.MEDIUM,
                    iteration=iteration
                ))

                # Extract funding amounts
                for news in funding_news[:3]:
                    amount = self._extract_funding_amount(news.get("title", ""))
                    if amount:
                        data_points.append(self.create_data_point(
                            key="funding_amount",
                            value=amount,
                            source_url=news.get("url", ""),
                            confidence=ConfidenceLevel.LOW,
                            iteration=iteration,
                            metadata={"title": news.get("title")}
                        ))
                        break

            # Check for acquisition/merger news
            ma_news = [
                n for n in news_items
                if any(kw in n.get("title", "").lower()
                       for kw in ["acquire", "acquisition", "merger", "acquires", "bought", "поглощ", "слияни"])
            ]
            if ma_news:
                data_points.append(self.create_data_point(
                    key="ma_mentions",
                    value=str(len(ma_news)),
                    source_url="aggregated",
                    confidence=ConfidenceLevel.MEDIUM,
                    iteration=iteration
                ))

            # Store top news headlines
            for i, news in enumerate(news_items[:5]):
                data_points.append(self.create_data_point(
                    key=f"news_headline_{i+1}",
                    value=news.get("title", "")[:200],
                    source_url=news.get("url", ""),
                    confidence=ConfidenceLevel.HIGH,
                    iteration=iteration,
                    metadata={"date": news.get("date", "").isoformat() if news.get("date") else None}
                ))

        return data_points

    async def _fetch_google_news(self, company_name: str) -> list[dict]:
        """Fetch news from Google News RSS."""
        query = quote_plus(f'"{company_name}"')
        url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"

        xml = await self.fetch_url(url)
        if not xml:
            return []

        news_items = []

        # Parse RSS items
        items = re.findall(r"<item>(.*?)</item>", xml, re.DOTALL)
        for item in items[:20]:  # Limit to 20 items
            title_match = re.search(r"<title>(.*?)</title>", item)
            link_match = re.search(r"<link>(.*?)</link>", item)
            date_match = re.search(r"<pubDate>(.*?)</pubDate>", item)

            if title_match:
                news = {
                    "title": self._clean_html(title_match.group(1)),
                    "url": link_match.group(1) if link_match else "",
                    "source": "google_news"
                }

                if date_match:
                    try:
                        # Parse RFC 2822 date
                        date_str = date_match.group(1)
                        news["date"] = datetime.strptime(
                            date_str, "%a, %d %b %Y %H:%M:%S %Z"
                        )
                    except ValueError:
                        news["date"] = None

                news_items.append(news)

        return news_items

    async def _fetch_hacker_news(self, company_name: str, domain: str) -> list[dict]:
        """Fetch from Hacker News search API."""
        news_items = []

        # Search by company name
        query = quote_plus(company_name)
        url = f"https://hn.algolia.com/api/v1/search?query={query}&tags=story&hitsPerPage=10"

        data = await self.fetch_json(url)
        if data and "hits" in data:
            for hit in data["hits"]:
                news_items.append({
                    "title": hit.get("title", ""),
                    "url": hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}",
                    "date": datetime.fromtimestamp(hit["created_at_i"]) if hit.get("created_at_i") else None,
                    "source": "hacker_news",
                    "points": hit.get("points", 0),
                    "comments": hit.get("num_comments", 0)
                })

        # Also search by domain
        url = f"https://hn.algolia.com/api/v1/search?query={domain}&tags=story&hitsPerPage=10"
        data = await self.fetch_json(url)
        if data and "hits" in data:
            for hit in data["hits"]:
                if not any(n["url"] == hit.get("url") for n in news_items):
                    news_items.append({
                        "title": hit.get("title", ""),
                        "url": hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}",
                        "date": datetime.fromtimestamp(hit["created_at_i"]) if hit.get("created_at_i") else None,
                        "source": "hacker_news",
                        "points": hit.get("points", 0)
                    })

        return news_items

    def _clean_html(self, text: str) -> str:
        """Remove HTML tags and entities."""
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"&[a-z]+;", " ", text)
        return text.strip()

    def _extract_topics(self, news_items: list[dict]) -> list[str]:
        """Extract common topics from news headlines."""
        # Common business/tech keywords to look for
        topic_keywords = {
            "funding": ["funding", "raised", "investment", "series", "инвестици"],
            "product": ["launch", "release", "announces", "new product", "запуск", "релиз"],
            "expansion": ["expand", "growth", "new market", "открыт", "расширен"],
            "partnership": ["partner", "collaboration", "deal", "партнер", "сотрудничеств"],
            "acquisition": ["acquire", "merger", "bought", "поглощ", "слияни"],
            "ipo": ["ipo", "public", "listing", "размещение"],
            "layoffs": ["layoff", "cut", "сокращен"],
            "leadership": ["ceo", "cto", "appoints", "назначен"],
            "technology": ["ai", "ml", "cloud", "blockchain", "технологи"],
            "revenue": ["revenue", "profit", "earnings", "выручк", "прибыль"],
        }

        topic_counts = {topic: 0 for topic in topic_keywords}

        for news in news_items:
            title = news.get("title", "").lower()
            for topic, keywords in topic_keywords.items():
                if any(kw in title for kw in keywords):
                    topic_counts[topic] += 1

        # Return topics sorted by frequency
        sorted_topics = sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)
        return [topic for topic, count in sorted_topics if count > 0]

    def _extract_funding_amount(self, text: str) -> str:
        """Extract funding amount from text."""
        patterns = [
            r"\$(\d+(?:\.\d+)?)\s*(million|billion|M|B)",
            r"(\d+(?:\.\d+)?)\s*(million|billion|M|B)\s*dollars",
            r"(\d+)\s*млн",
            r"(\d+)\s*млрд",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.I)
            if match:
                amount = match.group(1)
                unit = match.group(2).lower() if len(match.groups()) > 1 else ""

                if unit in ["million", "m", "млн"]:
                    return f"${amount}M"
                elif unit in ["billion", "b", "млрд"]:
                    return f"${amount}B"
                else:
                    return f"${amount}"

        return ""

    def discover_sources(self, profile: CompanyProfile) -> list[str]:
        """Discover additional sources from news."""
        sources = []

        for dp in profile.get_data_by_source(self.source_type):
            # News URLs can be sources for deeper analysis
            if dp.key.startswith("news_headline_") and dp.source_url:
                sources.append(dp.source_url)

        return sources
