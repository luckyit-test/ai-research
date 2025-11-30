"""
Jobs collector - analyzes job postings to understand company growth.
"""

import re
from urllib.parse import quote_plus

from .base import BaseCollector
from ..core.models import CompanyProfile, DataPoint, DataSourceType, ConfidenceLevel


class JobsCollector(BaseCollector):
    """Collects job posting data to assess company growth."""

    source_type = DataSourceType.JOBS
    name = "Job Postings Analyzer"
    description = "Analyzes job postings for growth indicators"
    priority = 2

    async def collect(self, profile: CompanyProfile, iteration: int) -> list[DataPoint]:
        """Collect job posting data."""
        data_points = []

        company_name = profile.name or profile.domain.split(".")[0]

        # Collect from multiple sources
        jobs = []

        # GitHub Jobs API alternative - check careers page
        careers_page = self._get_careers_url(profile)
        if careers_page:
            page_jobs = await self._analyze_careers_page(careers_page)
            jobs.extend(page_jobs)

        # Try LinkedIn jobs (limited without API)
        linkedin_jobs = await self._search_linkedin_jobs(company_name)
        jobs.extend(linkedin_jobs)

        # Analyze collected jobs
        if jobs:
            data_points.append(self.create_data_point(
                key="total_job_postings",
                value=str(len(jobs)),
                source_url="aggregated",
                confidence=ConfidenceLevel.MEDIUM,
                iteration=iteration
            ))

            # Categorize jobs by department
            departments = self._categorize_jobs(jobs)
            for dept, count in departments.items():
                if count > 0:
                    data_points.append(self.create_data_point(
                        key=f"jobs_{dept}",
                        value=str(count),
                        source_url="aggregated",
                        confidence=ConfidenceLevel.MEDIUM,
                        iteration=iteration
                    ))

            # Analyze job locations
            locations = self._extract_locations(jobs)
            if locations:
                data_points.append(self.create_data_point(
                    key="job_locations",
                    value=", ".join(locations[:10]),
                    source_url="aggregated",
                    confidence=ConfidenceLevel.MEDIUM,
                    iteration=iteration
                ))

            # Check for remote positions
            remote_count = sum(1 for j in jobs if self._is_remote(j))
            data_points.append(self.create_data_point(
                key="remote_positions",
                value=str(remote_count),
                source_url="aggregated",
                confidence=ConfidenceLevel.MEDIUM,
                iteration=iteration
            ))

            # Check for senior positions (indicates growth/maturity)
            senior_count = sum(1 for j in jobs if self._is_senior(j))
            data_points.append(self.create_data_point(
                key="senior_positions",
                value=str(senior_count),
                source_url="aggregated",
                confidence=ConfidenceLevel.MEDIUM,
                iteration=iteration
            ))

            # Extract required skills
            skills = self._extract_skills(jobs)
            if skills:
                data_points.append(self.create_data_point(
                    key="required_skills",
                    value=", ".join(skills[:15]),
                    source_url="aggregated",
                    confidence=ConfidenceLevel.MEDIUM,
                    iteration=iteration
                ))

        # Check if company has a careers page
        if careers_page:
            data_points.append(self.create_data_point(
                key="careers_page_url",
                value=careers_page,
                source_url=careers_page,
                confidence=ConfidenceLevel.HIGH,
                iteration=iteration
            ))

        return data_points

    def _get_careers_url(self, profile: CompanyProfile) -> str:
        """Get careers page URL from profile data."""
        for dp in profile.data_points:
            if dp.key == "page_careers":
                return dp.value
        return ""

    async def _analyze_careers_page(self, url: str) -> list[dict]:
        """Analyze company's careers page."""
        jobs = []
        html = await self.fetch_url(url)

        if not html:
            return jobs

        # Common patterns for job listings
        # Look for job title patterns
        title_patterns = [
            r'<h[1-4][^>]*class="[^"]*job[^"]*"[^>]*>([^<]+)</h[1-4]>',
            r'<a[^>]*href="[^"]*(?:job|career|position)[^"]*"[^>]*>([^<]+)</a>',
            r'"title"\s*:\s*"([^"]+)"',
            r'"jobTitle"\s*:\s*"([^"]+)"',
        ]

        for pattern in title_patterns:
            matches = re.findall(pattern, html, re.I)
            for title in matches:
                if len(title) > 5 and len(title) < 200:
                    jobs.append({
                        "title": self._clean_text(title),
                        "source": url
                    })

        # Remove duplicates
        seen = set()
        unique_jobs = []
        for job in jobs:
            if job["title"] not in seen:
                seen.add(job["title"])
                unique_jobs.append(job)

        return unique_jobs

    async def _search_linkedin_jobs(self, company_name: str) -> list[dict]:
        """Search for jobs on LinkedIn."""
        jobs = []

        # LinkedIn jobs search page
        query = quote_plus(company_name)
        url = f"https://www.linkedin.com/jobs/search/?keywords={query}"

        html = await self.fetch_url(url)
        if not html:
            return jobs

        # Extract job titles from the page
        title_matches = re.findall(
            r'<span[^>]*class="[^"]*job-title[^"]*"[^>]*>([^<]+)</span>',
            html, re.I
        )

        for title in title_matches[:20]:
            jobs.append({
                "title": self._clean_text(title),
                "source": "linkedin"
            })

        return jobs

    def _clean_text(self, text: str) -> str:
        """Clean text from HTML entities and extra whitespace."""
        text = re.sub(r"&[a-z]+;", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _categorize_jobs(self, jobs: list[dict]) -> dict[str, int]:
        """Categorize jobs by department."""
        categories = {
            "engineering": ["engineer", "developer", "software", "devops", "sre", "backend", "frontend", "fullstack", "разработчик", "инженер"],
            "product": ["product", "продукт"],
            "design": ["design", "ux", "ui", "дизайн"],
            "data": ["data", "analyst", "scientist", "ml", "ai", "данных", "аналитик"],
            "sales": ["sales", "account", "business development", "продаж"],
            "marketing": ["marketing", "content", "seo", "growth", "маркетинг"],
            "hr": ["hr", "recruiter", "talent", "people", "hr", "рекрутер"],
            "finance": ["finance", "accounting", "финанс", "бухгалтер"],
            "operations": ["operations", "ops", "operations"],
            "customer": ["customer", "support", "success", "поддержк", "клиент"],
            "legal": ["legal", "counsel", "юрист", "правов"],
            "executive": ["ceo", "cto", "cfo", "vp", "director", "head of", "директор", "руководитель"],
        }

        counts = {cat: 0 for cat in categories}

        for job in jobs:
            title = job.get("title", "").lower()
            for category, keywords in categories.items():
                if any(kw in title for kw in keywords):
                    counts[category] += 1
                    break

        return counts

    def _extract_locations(self, jobs: list[dict]) -> list[str]:
        """Extract job locations."""
        locations = []

        for job in jobs:
            location = job.get("location", "")
            if location and location not in locations:
                locations.append(location)

        return locations

    def _is_remote(self, job: dict) -> bool:
        """Check if job is remote."""
        text = f"{job.get('title', '')} {job.get('location', '')}".lower()
        return any(kw in text for kw in ["remote", "удален", "wfh", "work from home"])

    def _is_senior(self, job: dict) -> bool:
        """Check if job is a senior position."""
        title = job.get("title", "").lower()
        return any(kw in title for kw in [
            "senior", "lead", "principal", "staff", "director",
            "head", "vp", "chief", "старший", "ведущий", "руководитель"
        ])

    def _extract_skills(self, jobs: list[dict]) -> list[str]:
        """Extract commonly required skills from job titles."""
        skill_keywords = [
            "python", "java", "javascript", "typescript", "react", "node",
            "aws", "gcp", "azure", "kubernetes", "docker", "sql", "nosql",
            "mongodb", "postgresql", "redis", "kafka", "elasticsearch",
            "machine learning", "deep learning", "nlp", "computer vision",
            "golang", "rust", "c++", "scala", "kotlin", "swift",
            "tensorflow", "pytorch", "spark", "hadoop",
        ]

        skill_counts = {}
        for job in jobs:
            title = job.get("title", "").lower()
            for skill in skill_keywords:
                if skill in title:
                    skill_counts[skill] = skill_counts.get(skill, 0) + 1

        # Sort by frequency
        sorted_skills = sorted(skill_counts.items(), key=lambda x: x[1], reverse=True)
        return [skill for skill, _ in sorted_skills]

    def discover_sources(self, profile: CompanyProfile) -> list[str]:
        """Discover additional sources from job data."""
        sources = []

        for dp in profile.get_data_by_source(self.source_type):
            if dp.key == "careers_page_url":
                sources.append(dp.value)

        return sources
