#!/usr/bin/env python3
"""
Company Valuation Platform - Web Interface
Interactive GUI for analyzing company valuations.
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from flask import Flask, render_template_string, request, jsonify

# Add project to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from company_valuation.core.orchestrator import ValuationOrchestrator
from company_valuation.analyzers.valuation import ValuationAnalyzer

app = Flask(__name__)

# Store results in memory for demo
results_cache = {}

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Company Valuation Platform</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Inter', sans-serif; }
        .gradient-bg {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        }
        .card {
            background: white;
            border-radius: 16px;
            box-shadow: 0 10px 40px -10px rgba(0, 0, 0, 0.1);
        }
        .loader {
            border: 4px solid #f3f3f3;
            border-top: 4px solid #667eea;
            border-radius: 50%;
            width: 40px;
            height: 40px;
            animation: spin 1s linear infinite;
        }
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        .pulse {
            animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
        }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: .5; }
        }
        .fade-in {
            animation: fadeIn 0.5s ease-in;
        }
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }
    </style>
</head>
<body class="bg-gray-50 min-h-screen">
    <!-- Header -->
    <header class="gradient-bg text-white py-8 px-4 shadow-lg">
        <div class="max-w-6xl mx-auto">
            <h1 class="text-4xl font-bold mb-2">Company Valuation Platform</h1>
            <p class="text-lg opacity-90">AI-powered company analysis from public data sources</p>
        </div>
    </header>

    <!-- Main Content -->
    <main class="max-w-6xl mx-auto px-4 py-8">
        <!-- Search Form -->
        <div class="card p-8 mb-8">
            <h2 class="text-2xl font-semibold text-gray-800 mb-6">Analyze a Company</h2>
            <form id="analyzeForm" class="space-y-4">
                <div class="flex flex-col md:flex-row gap-4">
                    <div class="flex-1">
                        <label class="block text-sm font-medium text-gray-700 mb-2">Company Domain</label>
                        <input type="text" id="domain" name="domain"
                               placeholder="e.g., stripe.com, anthropic.com"
                               class="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent transition"
                               required>
                    </div>
                    <div class="w-full md:w-48">
                        <label class="block text-sm font-medium text-gray-700 mb-2">Iterations</label>
                        <select id="iterations" name="iterations"
                                class="w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent">
                            <option value="1">1 (Quick)</option>
                            <option value="2">2 (Standard)</option>
                            <option value="3" selected>3 (Thorough)</option>
                            <option value="5">5 (Deep)</option>
                        </select>
                    </div>
                </div>
                <button type="submit" id="submitBtn"
                        class="w-full md:w-auto px-8 py-3 bg-gradient-to-r from-purple-600 to-indigo-600 text-white font-semibold rounded-lg hover:from-purple-700 hover:to-indigo-700 transition transform hover:scale-105 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:ring-offset-2">
                    <span id="btnText">Analyze Company</span>
                    <span id="btnLoader" class="hidden">
                        <svg class="animate-spin inline h-5 w-5 text-white ml-2" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
                        </svg>
                        Analyzing...
                    </span>
                </button>
            </form>
        </div>

        <!-- Progress Section -->
        <div id="progressSection" class="hidden card p-8 mb-8 fade-in">
            <h3 class="text-xl font-semibold text-gray-800 mb-4">Analysis in Progress</h3>
            <div class="space-y-3">
                <div class="flex items-center">
                    <div class="loader mr-4"></div>
                    <div>
                        <p id="progressText" class="text-gray-700 font-medium">Starting analysis...</p>
                        <p id="progressDetail" class="text-sm text-gray-500">Collecting data from public sources</p>
                    </div>
                </div>
                <div class="w-full bg-gray-200 rounded-full h-2 mt-4">
                    <div id="progressBar" class="bg-gradient-to-r from-purple-600 to-indigo-600 h-2 rounded-full transition-all duration-500" style="width: 0%"></div>
                </div>
            </div>
        </div>

        <!-- Results Section -->
        <div id="resultsSection" class="hidden fade-in">
            <!-- Valuation Summary -->
            <div class="card p-8 mb-8">
                <div class="flex flex-col md:flex-row md:items-center md:justify-between mb-6">
                    <div>
                        <h2 id="companyName" class="text-3xl font-bold text-gray-800"></h2>
                        <p id="companyDomain" class="text-gray-500"></p>
                    </div>
                    <div class="mt-4 md:mt-0">
                        <span id="industryBadge" class="px-4 py-2 bg-purple-100 text-purple-700 rounded-full font-medium"></span>
                    </div>
                </div>

                <!-- Valuation Cards -->
                <div class="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
                    <div class="p-6 bg-gradient-to-br from-green-50 to-emerald-100 rounded-xl">
                        <p class="text-sm text-gray-600 mb-1">Estimated Valuation</p>
                        <p id="valuation" class="text-4xl font-bold text-green-600"></p>
                    </div>
                    <div class="p-6 bg-gray-50 rounded-xl">
                        <p class="text-sm text-gray-600 mb-1">Valuation Range</p>
                        <p id="valuationRange" class="text-xl font-semibold text-gray-700"></p>
                    </div>
                    <div class="p-6 bg-gray-50 rounded-xl">
                        <p class="text-sm text-gray-600 mb-1">Confidence Score</p>
                        <p id="confidence" class="text-3xl font-bold"></p>
                    </div>
                </div>

                <!-- Key Metrics -->
                <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div class="p-4 bg-blue-50 rounded-lg">
                        <p class="text-sm text-gray-500">Employees</p>
                        <p id="employees" class="text-lg font-semibold text-blue-600"></p>
                    </div>
                    <div class="p-4 bg-purple-50 rounded-lg">
                        <p class="text-sm text-gray-500">Headquarters</p>
                        <p id="headquarters" class="text-lg font-semibold text-purple-600"></p>
                    </div>
                    <div class="p-4 bg-indigo-50 rounded-lg">
                        <p class="text-sm text-gray-500">Founded</p>
                        <p id="founded" class="text-lg font-semibold text-indigo-600"></p>
                    </div>
                    <div class="p-4 bg-pink-50 rounded-lg">
                        <p class="text-sm text-gray-500">Data Points</p>
                        <p id="dataPoints" class="text-lg font-semibold text-pink-600"></p>
                    </div>
                </div>
            </div>

            <!-- Charts -->
            <div class="grid grid-cols-1 lg:grid-cols-2 gap-8 mb-8">
                <div class="card p-6">
                    <h3 class="text-lg font-semibold text-gray-800 mb-4">Valuation Factors</h3>
                    <canvas id="factorsChart"></canvas>
                </div>
                <div class="card p-6">
                    <h3 class="text-lg font-semibold text-gray-800 mb-4">Data Sources</h3>
                    <canvas id="sourcesChart"></canvas>
                </div>
            </div>

            <!-- Detailed Metrics -->
            <div id="metricsSection" class="card p-6 mb-8">
                <h3 class="text-xl font-semibold text-gray-800 mb-4">Detailed Metrics</h3>
                <div id="metricsContent"></div>
            </div>

            <!-- Data Points -->
            <div class="card p-6">
                <h3 class="text-xl font-semibold text-gray-800 mb-4">Raw Data Points</h3>
                <div id="dataPointsContent" class="space-y-4"></div>
            </div>
        </div>

        <!-- Demo Data Section -->
        <div id="demoSection" class="card p-8 mt-8">
            <h3 class="text-xl font-semibold text-gray-800 mb-4">Try Demo Data</h3>
            <p class="text-gray-600 mb-4">Click below to load sample analysis results:</p>
            <div class="flex flex-wrap gap-4">
                <button onclick="loadDemo('tech_startup')"
                        class="px-6 py-2 bg-blue-100 text-blue-700 rounded-lg hover:bg-blue-200 transition">
                    Tech Startup
                </button>
                <button onclick="loadDemo('enterprise')"
                        class="px-6 py-2 bg-green-100 text-green-700 rounded-lg hover:bg-green-200 transition">
                    Enterprise SaaS
                </button>
                <button onclick="loadDemo('ecommerce')"
                        class="px-6 py-2 bg-purple-100 text-purple-700 rounded-lg hover:bg-purple-200 transition">
                    E-commerce
                </button>
            </div>
        </div>
    </main>

    <!-- Footer -->
    <footer class="bg-gray-800 text-white py-6 px-4 mt-12">
        <div class="max-w-6xl mx-auto text-center text-sm opacity-75">
            <p>Company Valuation Platform | Data collected from public sources</p>
            <p class="mt-2">This report is for informational purposes only.</p>
        </div>
    </footer>

    <script>
        let factorsChart = null;
        let sourcesChart = null;

        // Demo data
        const demoData = {
            tech_startup: {
                company: {
                    name: "TechVenture AI",
                    domain: "techventure.ai",
                    industry: "Artificial Intelligence",
                    employee_count: "50-100",
                    headquarters: "San Francisco, CA",
                    founded_year: 2021,
                    estimated_valuation: 45000000,
                    valuation_range: [30000000, 75000000],
                    confidence_score: 0.68,
                    data_points: Array(47).fill({source_type: {value: 'website'}, key: 'metric', value: '123', confidence: {value: 'high'}, iteration: 1}),
                    metrics: [
                        {category: 'growth', name: 'Monthly Growth Rate', value: 15.2, unit: '%', description: 'Month-over-month growth'},
                        {category: 'growth', name: 'User Acquisition Cost', value: 45, unit: 'USD', description: 'Cost per new user'},
                        {category: 'market', name: 'Market Size', value: 5.2, unit: 'B USD', description: 'Total addressable market'},
                        {category: 'team', name: 'Team Size', value: 75, unit: 'people', description: 'Full-time employees'},
                    ],
                    valuation_factors: [
                        {name: 'Market Potential', score: 82},
                        {name: 'Technology', score: 78},
                        {name: 'Team', score: 71},
                        {name: 'Traction', score: 65},
                        {name: 'Financials', score: 55}
                    ]
                }
            },
            enterprise: {
                company: {
                    name: "CloudScale Enterprise",
                    domain: "cloudscale.io",
                    industry: "Enterprise SaaS",
                    employee_count: "200-500",
                    headquarters: "Seattle, WA",
                    founded_year: 2018,
                    estimated_valuation: 180000000,
                    valuation_range: [120000000, 250000000],
                    confidence_score: 0.75,
                    data_points: Array(89).fill({source_type: {value: 'financial'}, key: 'metric', value: '456', confidence: {value: 'high'}, iteration: 1}),
                    metrics: [
                        {category: 'revenue', name: 'ARR', value: 22.5, unit: 'M USD', description: 'Annual recurring revenue'},
                        {category: 'revenue', name: 'MRR Growth', value: 8.5, unit: '%', description: 'Monthly recurring revenue growth'},
                        {category: 'customers', name: 'Enterprise Clients', value: 156, unit: 'companies', description: 'Paying enterprise customers'},
                        {category: 'customers', name: 'Net Revenue Retention', value: 125, unit: '%', description: 'Net dollar retention rate'},
                    ],
                    valuation_factors: [
                        {name: 'Revenue', score: 88},
                        {name: 'Retention', score: 85},
                        {name: 'Market Position', score: 72},
                        {name: 'Team', score: 79},
                        {name: 'Technology', score: 68}
                    ]
                }
            },
            ecommerce: {
                company: {
                    name: "ShopGlobal",
                    domain: "shopglobal.com",
                    industry: "E-commerce",
                    employee_count: "100-200",
                    headquarters: "New York, NY",
                    founded_year: 2019,
                    estimated_valuation: 95000000,
                    valuation_range: [70000000, 140000000],
                    confidence_score: 0.72,
                    data_points: Array(63).fill({source_type: {value: 'social'}, key: 'metric', value: '789', confidence: {value: 'medium'}, iteration: 1}),
                    metrics: [
                        {category: 'sales', name: 'GMV', value: 45.8, unit: 'M USD', description: 'Gross merchandise value'},
                        {category: 'sales', name: 'Take Rate', value: 12.5, unit: '%', description: 'Platform commission rate'},
                        {category: 'users', name: 'Active Sellers', value: 12400, unit: 'merchants', description: 'Monthly active sellers'},
                        {category: 'users', name: 'Active Buyers', value: 890000, unit: 'users', description: 'Monthly active buyers'},
                    ],
                    valuation_factors: [
                        {name: 'GMV Growth', score: 76},
                        {name: 'User Acquisition', score: 81},
                        {name: 'Retention', score: 69},
                        {name: 'Market Size', score: 73},
                        {name: 'Unit Economics', score: 62}
                    ]
                }
            }
        };

        function formatValuation(value) {
            if (value >= 1000000000) {
                return '$' + (value / 1000000000).toFixed(1) + 'B';
            } else if (value >= 1000000) {
                return '$' + (value / 1000000).toFixed(1) + 'M';
            } else if (value >= 1000) {
                return '$' + (value / 1000).toFixed(0) + 'K';
            }
            return '$' + value.toFixed(0);
        }

        function displayResults(data) {
            const company = data.company;

            // Show results section
            document.getElementById('resultsSection').classList.remove('hidden');

            // Update basic info
            document.getElementById('companyName').textContent = company.name || company.domain;
            document.getElementById('companyDomain').textContent = company.domain;
            document.getElementById('industryBadge').textContent = company.industry || 'Technology';

            // Update valuation
            if (company.estimated_valuation) {
                document.getElementById('valuation').textContent = formatValuation(company.estimated_valuation);
                document.getElementById('valuationRange').textContent =
                    formatValuation(company.valuation_range[0]) + ' - ' + formatValuation(company.valuation_range[1]);

                const confidence = company.confidence_score * 100;
                const confidenceEl = document.getElementById('confidence');
                confidenceEl.textContent = confidence.toFixed(0) + '%';
                confidenceEl.className = 'text-3xl font-bold ' +
                    (confidence >= 70 ? 'text-green-600' : confidence >= 40 ? 'text-yellow-600' : 'text-red-600');
            } else {
                document.getElementById('valuation').textContent = 'N/A';
                document.getElementById('valuationRange').textContent = 'Insufficient data';
                document.getElementById('confidence').textContent = '0%';
            }

            // Update metrics
            document.getElementById('employees').textContent = company.employee_count || 'Unknown';
            document.getElementById('headquarters').textContent = company.headquarters || 'Unknown';
            document.getElementById('founded').textContent = company.founded_year || 'Unknown';
            document.getElementById('dataPoints').textContent = company.data_points ? company.data_points.length : 0;

            // Update charts
            updateCharts(company);

            // Update metrics table
            updateMetricsTable(company.metrics || []);

            // Update data points
            updateDataPoints(company.data_points || []);
        }

        function updateCharts(company) {
            // Destroy existing charts
            if (factorsChart) factorsChart.destroy();
            if (sourcesChart) sourcesChart.destroy();

            // Factors chart
            const factors = company.valuation_factors || [];
            const factorsCtx = document.getElementById('factorsChart').getContext('2d');
            factorsChart = new Chart(factorsCtx, {
                type: 'bar',
                data: {
                    labels: factors.map(f => f.name),
                    datasets: [{
                        label: 'Score',
                        data: factors.map(f => f.score),
                        backgroundColor: [
                            'rgba(99, 102, 241, 0.8)',
                            'rgba(139, 92, 246, 0.8)',
                            'rgba(236, 72, 153, 0.8)',
                            'rgba(34, 197, 94, 0.8)',
                            'rgba(251, 146, 60, 0.8)',
                        ],
                        borderWidth: 0,
                        borderRadius: 8,
                    }]
                },
                options: {
                    responsive: true,
                    plugins: { legend: { display: false } },
                    scales: {
                        y: { beginAtZero: true, max: 100 },
                        x: { grid: { display: false } }
                    }
                }
            });

            // Sources chart
            const sourceCounts = {};
            (company.data_points || []).forEach(dp => {
                const source = dp.source_type?.value || 'other';
                sourceCounts[source] = (sourceCounts[source] || 0) + 1;
            });

            const sourcesCtx = document.getElementById('sourcesChart').getContext('2d');
            sourcesChart = new Chart(sourcesCtx, {
                type: 'doughnut',
                data: {
                    labels: Object.keys(sourceCounts).map(s => s.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase())),
                    datasets: [{
                        data: Object.values(sourceCounts),
                        backgroundColor: [
                            'rgba(99, 102, 241, 0.8)',
                            'rgba(139, 92, 246, 0.8)',
                            'rgba(236, 72, 153, 0.8)',
                            'rgba(34, 197, 94, 0.8)',
                            'rgba(251, 146, 60, 0.8)',
                            'rgba(59, 130, 246, 0.8)',
                        ],
                        borderWidth: 2,
                        borderColor: 'white'
                    }]
                },
                options: {
                    responsive: true,
                    plugins: {
                        legend: { position: 'right' }
                    }
                }
            });
        }

        function updateMetricsTable(metrics) {
            const container = document.getElementById('metricsContent');
            if (metrics.length === 0) {
                container.innerHTML = '<p class="text-gray-500">No detailed metrics available</p>';
                return;
            }

            // Group by category
            const categories = {};
            metrics.forEach(m => {
                if (!categories[m.category]) categories[m.category] = [];
                categories[m.category].push(m);
            });

            let html = '';
            Object.keys(categories).forEach(cat => {
                html += `
                    <div class="mb-6">
                        <h4 class="text-md font-semibold text-gray-700 mb-2 capitalize">${cat.replace('_', ' ')}</h4>
                        <div class="overflow-x-auto">
                            <table class="w-full text-sm">
                                <thead class="bg-gray-50">
                                    <tr>
                                        <th class="py-2 px-4 text-left">Metric</th>
                                        <th class="py-2 px-4 text-left">Value</th>
                                        <th class="py-2 px-4 text-left">Unit</th>
                                        <th class="py-2 px-4 text-left">Description</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${categories[cat].map(m => `
                                        <tr class="border-b hover:bg-gray-50">
                                            <td class="py-2 px-4 font-medium">${m.name}</td>
                                            <td class="py-2 px-4">${typeof m.value === 'number' ? m.value.toFixed(1) : m.value}</td>
                                            <td class="py-2 px-4 text-gray-500">${m.unit}</td>
                                            <td class="py-2 px-4 text-gray-500">${m.description}</td>
                                        </tr>
                                    `).join('')}
                                </tbody>
                            </table>
                        </div>
                    </div>
                `;
            });

            container.innerHTML = html;
        }

        function updateDataPoints(dataPoints) {
            const container = document.getElementById('dataPointsContent');
            if (dataPoints.length === 0) {
                container.innerHTML = '<p class="text-gray-500">No data points collected</p>';
                return;
            }

            // Group by source
            const bySource = {};
            dataPoints.forEach(dp => {
                const source = dp.source_type?.value || 'other';
                if (!bySource[source]) bySource[source] = [];
                bySource[source].push(dp);
            });

            let html = '';
            Object.keys(bySource).forEach(source => {
                const points = bySource[source].slice(0, 10);
                html += `
                    <details class="border rounded-lg">
                        <summary class="cursor-pointer bg-gray-100 p-3 rounded-lg font-medium hover:bg-gray-200">
                            ${source.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase())} (${bySource[source].length} points)
                        </summary>
                        <div class="p-4 text-sm text-gray-600">
                            <p>Sample data points from this source...</p>
                        </div>
                    </details>
                `;
            });

            container.innerHTML = html;
        }

        function loadDemo(type) {
            const data = demoData[type];
            if (data) {
                document.getElementById('progressSection').classList.add('hidden');
                displayResults(data);

                // Scroll to results
                document.getElementById('resultsSection').scrollIntoView({ behavior: 'smooth' });
            }
        }

        // Form submission
        document.getElementById('analyzeForm').addEventListener('submit', async function(e) {
            e.preventDefault();

            const domain = document.getElementById('domain').value;
            const iterations = document.getElementById('iterations').value;

            // Show progress
            document.getElementById('progressSection').classList.remove('hidden');
            document.getElementById('resultsSection').classList.add('hidden');
            document.getElementById('btnText').classList.add('hidden');
            document.getElementById('btnLoader').classList.remove('hidden');
            document.getElementById('submitBtn').disabled = true;

            // Simulate progress
            let progress = 0;
            const progressInterval = setInterval(() => {
                progress += Math.random() * 15;
                if (progress > 90) progress = 90;
                document.getElementById('progressBar').style.width = progress + '%';

                const messages = [
                    'Analyzing website...',
                    'Collecting financial data...',
                    'Scanning social presence...',
                    'Gathering news articles...',
                    'Processing data points...',
                    'Calculating valuation...'
                ];
                document.getElementById('progressText').textContent = messages[Math.floor(progress / 20) % messages.length];
            }, 500);

            try {
                const response = await fetch('/analyze', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ domain, iterations: parseInt(iterations) })
                });

                const data = await response.json();

                clearInterval(progressInterval);
                document.getElementById('progressBar').style.width = '100%';

                setTimeout(() => {
                    document.getElementById('progressSection').classList.add('hidden');

                    if (data.error) {
                        alert('Error: ' + data.error);
                    } else {
                        displayResults(data);
                    }

                    // Reset button
                    document.getElementById('btnText').classList.remove('hidden');
                    document.getElementById('btnLoader').classList.add('hidden');
                    document.getElementById('submitBtn').disabled = false;
                }, 500);

            } catch (error) {
                clearInterval(progressInterval);
                document.getElementById('progressSection').classList.add('hidden');
                document.getElementById('btnText').classList.remove('hidden');
                document.getElementById('btnLoader').classList.add('hidden');
                document.getElementById('submitBtn').disabled = false;

                alert('Error: ' + error.message);
            }
        });
    </script>
</body>
</html>
"""


@app.route('/')
def index():
    """Serve the main page."""
    return render_template_string(HTML_TEMPLATE)


@app.route('/analyze', methods=['POST'])
def analyze():
    """Run company analysis."""
    try:
        data = request.get_json()
        domain = data.get('domain', '')
        iterations = data.get('iterations', 3)

        if not domain:
            return jsonify({'error': 'Domain is required'}), 400

        # Clean domain
        domain = domain.strip().lower()
        if domain.startswith('http://'):
            domain = domain[7:]
        if domain.startswith('https://'):
            domain = domain[8:]
        if domain.startswith('www.'):
            domain = domain[4:]
        domain = domain.split('/')[0]

        # Run analysis
        orchestrator = ValuationOrchestrator()
        analyzer = ValuationAnalyzer()

        # Run async analysis
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            report = loop.run_until_complete(
                orchestrator.run(domain=domain, iterations=iterations)
            )
        finally:
            loop.close()

        profile = report.company

        # Format response
        result = {
            'company': {
                'name': profile.name,
                'domain': profile.domain,
                'industry': profile.industry,
                'employee_count': profile.employee_count,
                'headquarters': profile.headquarters,
                'founded_year': profile.founded_year,
                'estimated_valuation': profile.estimated_valuation,
                'valuation_range': list(profile.valuation_range) if profile.valuation_range else [0, 0],
                'confidence_score': profile.confidence_score,
                'data_points': [
                    {
                        'source_type': {'value': dp.source_type.value},
                        'key': dp.key,
                        'value': str(dp.value)[:100],
                        'confidence': {'value': dp.confidence.value},
                        'iteration': dp.iteration
                    }
                    for dp in profile.data_points
                ],
                'metrics': [
                    {
                        'category': m.category,
                        'name': m.name,
                        'value': m.value,
                        'unit': m.unit,
                        'description': m.description
                    }
                    for m in profile.metrics
                ],
                'valuation_factors': [
                    {'name': f.name, 'score': f.score}
                    for f in profile.valuation_factors
                ]
            }
        }

        return jsonify(result)

    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("  COMPANY VALUATION PLATFORM - Web Interface")
    print("=" * 60)
    print("\n  Starting web server...")
    print("  Open http://localhost:5000 in your browser")
    print("\n  Press Ctrl+C to stop the server")
    print("=" * 60 + "\n")

    app.run(host='0.0.0.0', port=5000, debug=False)
