"""
Website collector - analyzes company's main website.
"""

import re
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

from .base import BaseCollector
from ..core.models import CompanyProfile, DataPoint, DataSourceType, ConfidenceLevel


class WebsiteCollector(BaseCollector):
    """Collects data from company's main website."""

    source_type = DataSourceType.WEBSITE
    name = "Website Analyzer"
    description = "Analyzes company's main website for basic information"
    priority = 1

    async def collect(self, profile: CompanyProfile, iteration: int) -> list[DataPoint]:
        """Collect data from company website."""
        data_points = []
        base_url = f"https://{profile.domain}"

        html = await self.fetch_url(base_url)
        if not html:
            # Try without https
            base_url = f"http://{profile.domain}"
            html = await self.fetch_url(base_url)

        if not html:
            self.logger.warning(f"Could not fetch website for {profile.domain}")
            return data_points

        soup = BeautifulSoup(html, "html.parser")

        # Extract title
        title = soup.find("title")
        if title and title.text:
            data_points.append(self.create_data_point(
                key="website_title",
                value=title.text.strip(),
                source_url=base_url,
                confidence=ConfidenceLevel.HIGH,
                iteration=iteration
            ))

        # Extract meta description
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc and meta_desc.get("content"):
            data_points.append(self.create_data_point(
                key="meta_description",
                value=meta_desc["content"],
                source_url=base_url,
                confidence=ConfidenceLevel.HIGH,
                iteration=iteration
            ))

        # Extract company name from various sources
        company_name = self._extract_company_name(soup, profile.domain)
        if company_name:
            data_points.append(self.create_data_point(
                key="company_name",
                value=company_name,
                source_url=base_url,
                confidence=ConfidenceLevel.MEDIUM,
                iteration=iteration
            ))

        # Find social media links
        social_links = self._extract_social_links(soup, base_url)
        for platform, url in social_links.items():
            data_points.append(self.create_data_point(
                key=f"social_{platform}",
                value=url,
                source_url=base_url,
                confidence=ConfidenceLevel.HIGH,
                iteration=iteration
            ))

        # Find contact information
        emails = self._extract_emails(html)
        for email in emails:
            data_points.append(self.create_data_point(
                key="email",
                value=email,
                source_url=base_url,
                confidence=ConfidenceLevel.HIGH,
                iteration=iteration
            ))

        phones = self._extract_phones(html)
        for phone in phones:
            data_points.append(self.create_data_point(
                key="phone",
                value=phone,
                source_url=base_url,
                confidence=ConfidenceLevel.MEDIUM,
                iteration=iteration
            ))

        # Find addresses
        addresses = self._extract_addresses(soup)
        for addr in addresses:
            data_points.append(self.create_data_point(
                key="address",
                value=addr,
                source_url=base_url,
                confidence=ConfidenceLevel.MEDIUM,
                iteration=iteration
            ))

        # Analyze internal pages
        internal_pages = self._find_important_pages(soup, base_url)
        for page_type, url in internal_pages.items():
            data_points.append(self.create_data_point(
                key=f"page_{page_type}",
                value=url,
                source_url=base_url,
                confidence=ConfidenceLevel.HIGH,
                iteration=iteration
            ))

        return data_points

    def _extract_company_name(self, soup: BeautifulSoup, domain: str) -> str:
        """Extract company name from page."""
        # Try logo alt text
        logo = soup.find("img", class_=re.compile(r"logo", re.I))
        if logo and logo.get("alt"):
            return logo["alt"].strip()

        # Try header
        h1 = soup.find("h1")
        if h1 and h1.text:
            return h1.text.strip()

        # Use domain name
        name = domain.split(".")[0]
        return name.title()

    def _extract_social_links(self, soup: BeautifulSoup, base_url: str) -> dict[str, str]:
        """Extract social media links."""
        social_patterns = {
            "linkedin": r"linkedin\.com",
            "twitter": r"(twitter\.com|x\.com)",
            "facebook": r"facebook\.com",
            "instagram": r"instagram\.com",
            "youtube": r"youtube\.com",
            "github": r"github\.com",
            "tiktok": r"tiktok\.com",
            "telegram": r"(t\.me|telegram\.)",
        }

        found = {}
        for link in soup.find_all("a", href=True):
            href = link["href"]
            for platform, pattern in social_patterns.items():
                if platform not in found and re.search(pattern, href, re.I):
                    found[platform] = href
                    break

        return found

    def _extract_emails(self, html: str) -> list[str]:
        """Extract email addresses."""
        pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
        emails = re.findall(pattern, html)
        # Filter out common non-company emails
        filtered = [e for e in set(emails) if not any(
            x in e.lower() for x in ["example.com", "test.com", "email.com", "wixpress"]
        )]
        return filtered[:5]  # Limit to 5

    def _extract_phones(self, html: str) -> list[str]:
        """Extract phone numbers."""
        patterns = [
            r"\+?[1-9]\d{0,2}[-.\s]?\(?\d{1,4}\)?[-.\s]?\d{1,4}[-.\s]?\d{1,9}",
            r"\(\d{3}\)\s*\d{3}[-.\s]?\d{4}",
        ]
        phones = []
        for pattern in patterns:
            phones.extend(re.findall(pattern, html))

        # Filter and clean
        cleaned = []
        for p in phones:
            p = re.sub(r"[^\d+]", "", p)
            if 7 <= len(p) <= 15:
                cleaned.append(p)

        return list(set(cleaned))[:3]

    def _extract_addresses(self, soup: BeautifulSoup) -> list[str]:
        """Extract physical addresses."""
        addresses = []

        # Look for address tags
        for addr in soup.find_all("address"):
            text = addr.get_text(strip=True)
            if text and len(text) > 10:
                addresses.append(text[:200])

        # Look for schema.org address
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                import json
                data = json.loads(script.string)
                if isinstance(data, dict):
                    addr = data.get("address", {})
                    if isinstance(addr, dict):
                        parts = [
                            addr.get("streetAddress", ""),
                            addr.get("addressLocality", ""),
                            addr.get("addressRegion", ""),
                            addr.get("postalCode", ""),
                            addr.get("addressCountry", "")
                        ]
                        address = ", ".join(p for p in parts if p)
                        if address:
                            addresses.append(address)
            except (json.JSONDecodeError, AttributeError):
                pass

        return addresses[:2]

    def _find_important_pages(self, soup: BeautifulSoup, base_url: str) -> dict[str, str]:
        """Find important pages like About, Contact, Careers."""
        page_patterns = {
            "about": r"(about|о.?нас|о.?компании|who.?we.?are)",
            "contact": r"(contact|контакты|связь|reach.?us)",
            "careers": r"(career|job|вакансии|работа|hiring)",
            "team": r"(team|команда|our.?people|leadership)",
            "products": r"(product|услуги|service|solution|pricing)",
            "blog": r"(blog|новости|news|articles)",
            "investors": r"(investor|relations|акционерам)",
        }

        found = {}
        for link in soup.find_all("a", href=True):
            href = link["href"]
            text = link.get_text(strip=True).lower()

            for page_type, pattern in page_patterns.items():
                if page_type not in found:
                    if re.search(pattern, href, re.I) or re.search(pattern, text, re.I):
                        full_url = urljoin(base_url, href)
                        if urlparse(full_url).netloc == urlparse(base_url).netloc:
                            found[page_type] = full_url
                            break

        return found

    def discover_sources(self, profile: CompanyProfile) -> list[str]:
        """Discover new sources from website data."""
        sources = []

        for dp in profile.get_data_by_source(self.source_type):
            # Social media links become sources
            if dp.key.startswith("social_"):
                sources.append(dp.value)

            # Important pages become sources
            if dp.key.startswith("page_"):
                sources.append(dp.value)

        return sources
