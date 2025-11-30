"""
HTML Dashboard Generator - creates interactive web dashboard.
"""

import json
import os
from datetime import datetime
from typing import Optional

from ..core.models import CompanyProfile, ValuationReport, DataSourceType
from ..analyzers.valuation import ValuationAnalyzer


class DashboardGenerator:
    """Generates interactive HTML dashboards."""

    def __init__(self):
        self.analyzer = ValuationAnalyzer()

    def generate(
        self,
        report: ValuationReport,
        output_path: str,
        title: str = "Company Valuation Dashboard"
    ) -> str:
        """
        Generate an HTML dashboard.

        Args:
            report: The valuation report data
            output_path: Path for the output file
            title: Dashboard title

        Returns:
            Path to the generated file
        """
        profile = report.company

        html = self._generate_html(profile, report, title)

        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)

        return output_path

    def _generate_html(
        self,
        profile: CompanyProfile,
        report: ValuationReport,
        title: str
    ) -> str:
        """Generate the complete HTML document."""
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - {profile.name or profile.domain}</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        .gradient-bg {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        }}
        .card {{
            background: white;
            border-radius: 12px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        }}
        .metric-card {{
            transition: transform 0.2s;
        }}
        .metric-card:hover {{
            transform: translateY(-2px);
        }}
        .data-table {{
            font-size: 0.875rem;
        }}
        .confidence-high {{ color: #10b981; }}
        .confidence-medium {{ color: #f59e0b; }}
        .confidence-low {{ color: #ef4444; }}
    </style>
</head>
<body class="bg-gray-100 min-h-screen">
    <!-- Header -->
    <header class="gradient-bg text-white py-8 px-4">
        <div class="max-w-7xl mx-auto">
            <h1 class="text-3xl font-bold mb-2">{profile.name or profile.domain}</h1>
            <p class="text-lg opacity-90">{profile.domain}</p>
            <p class="text-sm opacity-75 mt-2">
                Generated: {datetime.now().strftime('%B %d, %Y at %H:%M')} |
                Iterations: {profile.current_iteration}/{profile.total_iterations}
            </p>
        </div>
    </header>

    <!-- Main Content -->
    <main class="max-w-7xl mx-auto px-4 py-8">
        <!-- Valuation Summary -->
        {self._generate_valuation_summary(profile)}

        <!-- Key Metrics Grid -->
        {self._generate_metrics_grid(profile)}

        <!-- Charts Row -->
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
            {self._generate_factors_chart(profile)}
            {self._generate_sources_chart(profile)}
        </div>

        <!-- Detailed Data Tables -->
        {self._generate_data_tables(profile)}

        <!-- Iteration History -->
        {self._generate_iteration_history(report)}

        <!-- Data Points -->
        {self._generate_data_points_section(profile)}
    </main>

    <!-- Footer -->
    <footer class="bg-gray-800 text-white py-6 px-4 mt-8">
        <div class="max-w-7xl mx-auto text-center text-sm opacity-75">
            <p>Company Valuation Platform | Data collected from public sources</p>
            <p class="mt-2">This report is for informational purposes only.</p>
        </div>
    </footer>

    <!-- Charts JavaScript -->
    <script>
        {self._generate_charts_js(profile)}
    </script>
</body>
</html>"""

    def _generate_valuation_summary(self, profile: CompanyProfile) -> str:
        """Generate valuation summary section."""
        if not profile.estimated_valuation:
            valuation_display = "Insufficient Data"
            range_display = "N/A"
            confidence_display = "0%"
            confidence_color = "text-gray-500"
        else:
            valuation_display = self.analyzer.format_valuation(profile.estimated_valuation)
            range_display = f"{self.analyzer.format_valuation(profile.valuation_range[0])} - {self.analyzer.format_valuation(profile.valuation_range[1])}"
            confidence_display = f"{profile.confidence_score * 100:.0f}%"

            if profile.confidence_score >= 0.7:
                confidence_color = "text-green-600"
            elif profile.confidence_score >= 0.4:
                confidence_color = "text-yellow-600"
            else:
                confidence_color = "text-red-600"

        return f"""
        <div class="card p-6 mb-8">
            <h2 class="text-xl font-semibold mb-4 text-gray-800">Valuation Summary</h2>
            <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
                <div class="text-center p-4 bg-gradient-to-br from-green-50 to-green-100 rounded-lg">
                    <p class="text-sm text-gray-600 mb-1">Estimated Valuation</p>
                    <p class="text-3xl font-bold text-green-600">{valuation_display}</p>
                </div>
                <div class="text-center p-4 bg-gray-50 rounded-lg">
                    <p class="text-sm text-gray-600 mb-1">Valuation Range</p>
                    <p class="text-xl font-semibold text-gray-700">{range_display}</p>
                </div>
                <div class="text-center p-4 bg-gray-50 rounded-lg">
                    <p class="text-sm text-gray-600 mb-1">Confidence Score</p>
                    <p class="text-2xl font-bold {confidence_color}">{confidence_display}</p>
                </div>
            </div>
        </div>
        """

    def _generate_metrics_grid(self, profile: CompanyProfile) -> str:
        """Generate key metrics grid."""
        metrics_html = ""

        key_metrics = [
            ("Industry", profile.industry or "Not determined", "bg-blue-50", "text-blue-600"),
            ("Employees", profile.employee_count or "Unknown", "bg-purple-50", "text-purple-600"),
            ("Headquarters", profile.headquarters or "Unknown", "bg-indigo-50", "text-indigo-600"),
            ("Founded", str(profile.founded_year) if profile.founded_year else "Unknown", "bg-pink-50", "text-pink-600"),
            ("Data Points", str(len(profile.data_points)), "bg-green-50", "text-green-600"),
            ("Metrics", str(len(profile.metrics)), "bg-yellow-50", "text-yellow-600"),
        ]

        for label, value, bg_color, text_color in key_metrics:
            metrics_html += f"""
            <div class="metric-card card p-4">
                <p class="text-sm text-gray-500 mb-1">{label}</p>
                <p class="text-lg font-semibold {text_color}">{value}</p>
            </div>
            """

        return f"""
        <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4 mb-8">
            {metrics_html}
        </div>
        """

    def _generate_factors_chart(self, profile: CompanyProfile) -> str:
        """Generate valuation factors chart card."""
        return """
        <div class="card p-6">
            <h3 class="text-lg font-semibold mb-4 text-gray-800">Valuation Factors</h3>
            <canvas id="factorsChart" height="200"></canvas>
        </div>
        """

    def _generate_sources_chart(self, profile: CompanyProfile) -> str:
        """Generate data sources chart card."""
        return """
        <div class="card p-6">
            <h3 class="text-lg font-semibold mb-4 text-gray-800">Data Sources</h3>
            <canvas id="sourcesChart" height="200"></canvas>
        </div>
        """

    def _generate_data_tables(self, profile: CompanyProfile) -> str:
        """Generate detailed data tables."""
        # Group metrics by category
        categories = {}
        for metric in profile.metrics:
            if metric.category not in categories:
                categories[metric.category] = []
            categories[metric.category].append(metric)

        tables_html = ""
        for category, metrics in categories.items():
            rows_html = ""
            for m in metrics:
                value_display = f"{m.value:.1f}" if isinstance(m.value, float) else str(m.value)
                rows_html += f"""
                <tr class="border-b hover:bg-gray-50">
                    <td class="py-2 px-4 font-medium">{m.name}</td>
                    <td class="py-2 px-4">{value_display}</td>
                    <td class="py-2 px-4 text-gray-500">{m.unit}</td>
                    <td class="py-2 px-4 text-gray-500 text-sm">{m.description}</td>
                </tr>
                """

            tables_html += f"""
            <div class="card p-6 mb-6">
                <h3 class="text-lg font-semibold mb-4 text-gray-800 capitalize">{category.replace('_', ' ')}</h3>
                <div class="overflow-x-auto">
                    <table class="w-full data-table">
                        <thead class="bg-gray-50">
                            <tr>
                                <th class="py-2 px-4 text-left font-medium text-gray-600">Metric</th>
                                <th class="py-2 px-4 text-left font-medium text-gray-600">Value</th>
                                <th class="py-2 px-4 text-left font-medium text-gray-600">Unit</th>
                                <th class="py-2 px-4 text-left font-medium text-gray-600">Description</th>
                            </tr>
                        </thead>
                        <tbody>
                            {rows_html}
                        </tbody>
                    </table>
                </div>
            </div>
            """

        return f"""
        <div class="mb-8">
            <h2 class="text-xl font-semibold mb-4 text-gray-800">Detailed Metrics</h2>
            {tables_html}
        </div>
        """

    def _generate_iteration_history(self, report: ValuationReport) -> str:
        """Generate iteration history section."""
        if not report.iterations:
            return ""

        rows_html = ""
        for it in report.iterations:
            sources = ", ".join(it.sources_used[:3])
            if len(it.sources_used) > 3:
                sources += f" +{len(it.sources_used) - 3} more"

            rows_html += f"""
            <tr class="border-b hover:bg-gray-50">
                <td class="py-2 px-4 font-medium">Iteration {it.iteration_number}</td>
                <td class="py-2 px-4">{it.data_points_collected}</td>
                <td class="py-2 px-4 text-sm">{sources}</td>
                <td class="py-2 px-4">{it.duration_seconds:.1f}s</td>
            </tr>
            """

        return f"""
        <div class="card p-6 mb-8">
            <h2 class="text-xl font-semibold mb-4 text-gray-800">Collection History</h2>
            <div class="overflow-x-auto">
                <table class="w-full data-table">
                    <thead class="bg-gray-50">
                        <tr>
                            <th class="py-2 px-4 text-left font-medium text-gray-600">Iteration</th>
                            <th class="py-2 px-4 text-left font-medium text-gray-600">Data Points</th>
                            <th class="py-2 px-4 text-left font-medium text-gray-600">Sources Used</th>
                            <th class="py-2 px-4 text-left font-medium text-gray-600">Duration</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows_html}
                    </tbody>
                </table>
            </div>
        </div>
        """

    def _generate_data_points_section(self, profile: CompanyProfile) -> str:
        """Generate collapsible data points section."""
        # Group by source
        by_source = {}
        for dp in profile.data_points:
            source = dp.source_type.value
            if source not in by_source:
                by_source[source] = []
            by_source[source].append(dp)

        sections_html = ""
        for source, dps in by_source.items():
            rows_html = ""
            for dp in dps[:20]:  # Limit display
                confidence_class = f"confidence-{dp.confidence.value}"
                value_display = str(dp.value)[:100]
                if len(str(dp.value)) > 100:
                    value_display += "..."

                rows_html += f"""
                <tr class="border-b hover:bg-gray-50">
                    <td class="py-2 px-4 font-mono text-sm">{dp.key}</td>
                    <td class="py-2 px-4 text-sm">{value_display}</td>
                    <td class="py-2 px-4 {confidence_class} text-sm capitalize">{dp.confidence.value}</td>
                    <td class="py-2 px-4 text-gray-500 text-sm">{dp.iteration}</td>
                </tr>
                """

            sections_html += f"""
            <details class="mb-4">
                <summary class="cursor-pointer bg-gray-100 p-3 rounded-lg font-medium hover:bg-gray-200">
                    {source.replace('_', ' ').title()} ({len(dps)} points)
                </summary>
                <div class="mt-2 overflow-x-auto">
                    <table class="w-full data-table">
                        <thead class="bg-gray-50">
                            <tr>
                                <th class="py-2 px-4 text-left font-medium text-gray-600">Key</th>
                                <th class="py-2 px-4 text-left font-medium text-gray-600">Value</th>
                                <th class="py-2 px-4 text-left font-medium text-gray-600">Confidence</th>
                                <th class="py-2 px-4 text-left font-medium text-gray-600">Iteration</th>
                            </tr>
                        </thead>
                        <tbody>
                            {rows_html}
                        </tbody>
                    </table>
                </div>
            </details>
            """

        return f"""
        <div class="card p-6">
            <h2 class="text-xl font-semibold mb-4 text-gray-800">Raw Data Points</h2>
            {sections_html}
        </div>
        """

    def _generate_charts_js(self, profile: CompanyProfile) -> str:
        """Generate JavaScript for charts."""
        # Prepare factors data
        factor_labels = []
        factor_scores = []
        factor_colors = [
            'rgba(99, 102, 241, 0.8)',
            'rgba(139, 92, 246, 0.8)',
            'rgba(236, 72, 153, 0.8)',
            'rgba(34, 197, 94, 0.8)',
            'rgba(251, 146, 60, 0.8)',
        ]

        for i, factor in enumerate(profile.valuation_factors[:5]):
            factor_labels.append(factor.name)
            factor_scores.append(round(factor.score, 1))

        # Prepare sources data
        source_counts = {}
        for dp in profile.data_points:
            source = dp.source_type.value.replace("_", " ").title()
            source_counts[source] = source_counts.get(source, 0) + 1

        source_labels = list(source_counts.keys())
        source_values = list(source_counts.values())

        return f"""
        // Factors Chart
        const factorsCtx = document.getElementById('factorsChart').getContext('2d');
        new Chart(factorsCtx, {{
            type: 'bar',
            data: {{
                labels: {json.dumps(factor_labels)},
                datasets: [{{
                    label: 'Score',
                    data: {json.dumps(factor_scores)},
                    backgroundColor: {json.dumps(factor_colors[:len(factor_scores)])},
                    borderWidth: 0,
                    borderRadius: 6,
                }}]
            }},
            options: {{
                responsive: true,
                plugins: {{
                    legend: {{ display: false }}
                }},
                scales: {{
                    y: {{
                        beginAtZero: true,
                        max: 100,
                        grid: {{ color: 'rgba(0,0,0,0.05)' }}
                    }},
                    x: {{
                        grid: {{ display: false }}
                    }}
                }}
            }}
        }});

        // Sources Chart
        const sourcesCtx = document.getElementById('sourcesChart').getContext('2d');
        new Chart(sourcesCtx, {{
            type: 'doughnut',
            data: {{
                labels: {json.dumps(source_labels)},
                datasets: [{{
                    data: {json.dumps(source_values)},
                    backgroundColor: [
                        'rgba(99, 102, 241, 0.8)',
                        'rgba(139, 92, 246, 0.8)',
                        'rgba(236, 72, 153, 0.8)',
                        'rgba(34, 197, 94, 0.8)',
                        'rgba(251, 146, 60, 0.8)',
                        'rgba(59, 130, 246, 0.8)',
                        'rgba(168, 85, 247, 0.8)',
                    ],
                    borderWidth: 2,
                    borderColor: 'white'
                }}]
            }},
            options: {{
                responsive: true,
                plugins: {{
                    legend: {{
                        position: 'right',
                        labels: {{ padding: 15 }}
                    }}
                }}
            }}
        }});
        """
