"""
Data models for company valuation platform.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class DataSourceType(Enum):
    """Types of data sources."""
    WEBSITE = "website"
    WHOIS = "whois"
    SOCIAL_MEDIA = "social_media"
    NEWS = "news"
    JOBS = "jobs"
    TECH_STACK = "tech_stack"
    FINANCIAL = "financial"
    REVIEWS = "reviews"
    PATENTS = "patents"
    LEGAL = "legal"


class ConfidenceLevel(Enum):
    """Confidence level for collected data."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERIFIED = "verified"


@dataclass
class DataPoint:
    """A single piece of collected data."""
    source_type: DataSourceType
    source_url: str
    key: str
    value: str
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM
    collected_at: datetime = field(default_factory=datetime.now)
    iteration: int = 1
    metadata: dict = field(default_factory=dict)


@dataclass
class CompanyMetric:
    """A calculated metric for the company."""
    name: str
    value: float
    unit: str
    category: str
    description: str
    data_points: list[DataPoint] = field(default_factory=list)
    weight: float = 1.0


@dataclass
class ValuationFactor:
    """A factor contributing to company valuation."""
    name: str
    score: float  # 0-100
    weight: float  # 0-1
    category: str
    description: str
    metrics: list[CompanyMetric] = field(default_factory=list)


@dataclass
class CompanyProfile:
    """Complete company profile with all collected data."""
    domain: str
    name: Optional[str] = None
    description: Optional[str] = None
    industry: Optional[str] = None
    founded_year: Optional[int] = None
    headquarters: Optional[str] = None
    employee_count: Optional[str] = None
    data_points: list[DataPoint] = field(default_factory=list)
    metrics: list[CompanyMetric] = field(default_factory=list)
    valuation_factors: list[ValuationFactor] = field(default_factory=list)
    estimated_valuation: Optional[float] = None
    valuation_range: tuple[float, float] = (0, 0)
    confidence_score: float = 0.0
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    current_iteration: int = 0
    total_iterations: int = 1

    def add_data_point(self, data_point: DataPoint) -> None:
        """Add a new data point to the profile."""
        self.data_points.append(data_point)
        self.updated_at = datetime.now()

    def get_data_by_source(self, source_type: DataSourceType) -> list[DataPoint]:
        """Get all data points from a specific source."""
        return [dp for dp in self.data_points if dp.source_type == source_type]

    def get_data_by_iteration(self, iteration: int) -> list[DataPoint]:
        """Get all data points from a specific iteration."""
        return [dp for dp in self.data_points if dp.iteration == iteration]


@dataclass
class IterationResult:
    """Result of a single iteration."""
    iteration_number: int
    sources_used: list[str]
    data_points_collected: int
    new_sources_discovered: list[str]
    metrics_updated: list[str]
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    duration_seconds: float = 0.0

    def complete(self) -> None:
        """Mark iteration as complete."""
        self.completed_at = datetime.now()
        self.duration_seconds = (self.completed_at - self.started_at).total_seconds()


@dataclass
class ValuationReport:
    """Complete valuation report."""
    company: CompanyProfile
    iterations: list[IterationResult] = field(default_factory=list)
    generated_at: datetime = field(default_factory=datetime.now)
    report_version: str = "1.0"
