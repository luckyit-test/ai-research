#!/usr/bin/env python3
"""
Company Valuation Platform - CLI Interface

Usage:
    python -m company_valuation --domain example.com --iterations 3

This tool performs iterative analysis of a company based on its domain,
collecting data from multiple public sources and generating valuation reports.
"""

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime

from .core.orchestrator import ValuationOrchestrator
from .reporters.docx_report import DocxReportGenerator
from .reporters.dashboard import DashboardGenerator
from .analyzers.valuation import ValuationAnalyzer


def setup_logging(verbose: bool = False) -> None:
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%H:%M:%S"
    )


def print_banner() -> None:
    """Print application banner."""
    banner = """
    ╔══════════════════════════════════════════════════════════╗
    ║         COMPANY VALUATION PLATFORM                       ║
    ║         Iterative Multi-Source Analysis                  ║
    ╚══════════════════════════════════════════════════════════╝
    """
    print(banner)


def print_progress(message: str, current: int, total: int) -> None:
    """Print progress message."""
    if total > 0:
        percentage = (current / total) * 100
        bar_length = 30
        filled = int(bar_length * current / total)
        bar = "█" * filled + "░" * (bar_length - filled)
        print(f"\r[{bar}] {percentage:5.1f}% | {message}", end="", flush=True)
        if current == total:
            print()  # New line at completion
    else:
        print(f"  → {message}")


def print_summary(profile, analyzer: ValuationAnalyzer) -> None:
    """Print valuation summary to console."""
    print("\n" + "=" * 60)
    print("                    VALUATION SUMMARY")
    print("=" * 60)

    print(f"\n  Company:     {profile.name or profile.domain}")
    print(f"  Domain:      {profile.domain}")

    if profile.industry:
        print(f"  Industry:    {profile.industry}")

    if profile.employee_count:
        print(f"  Employees:   {profile.employee_count}")

    if profile.headquarters:
        print(f"  HQ:          {profile.headquarters}")

    print(f"\n  Data Points: {len(profile.data_points)}")
    print(f"  Metrics:     {len(profile.metrics)}")
    print(f"  Iterations:  {profile.current_iteration}/{profile.total_iterations}")

    print("\n" + "-" * 60)

    if profile.estimated_valuation:
        valuation = analyzer.format_valuation(profile.estimated_valuation)
        low = analyzer.format_valuation(profile.valuation_range[0])
        high = analyzer.format_valuation(profile.valuation_range[1])
        confidence = profile.confidence_score * 100

        print(f"\n  ESTIMATED VALUATION: {valuation}")
        print(f"  Valuation Range:     {low} - {high}")
        print(f"  Confidence Score:    {confidence:.0f}%")
    else:
        print("\n  ESTIMATED VALUATION: Insufficient data")

    print("\n" + "=" * 60)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Company Valuation Platform - Analyze company value from public sources",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m company_valuation --domain stripe.com
  python -m company_valuation --domain example.com --iterations 5
  python -m company_valuation --domain company.io --output ./reports --no-dashboard

Report Outputs:
  - DOCX report with detailed analysis
  - Interactive HTML dashboard
  - Console summary
        """
    )

    parser.add_argument(
        "--domain", "-d",
        required=True,
        help="Company domain to analyze (e.g., stripe.com)"
    )

    parser.add_argument(
        "--iterations", "-i",
        type=int,
        default=3,
        help="Number of data collection iterations (default: 3)"
    )

    parser.add_argument(
        "--output", "-o",
        default="./output",
        help="Output directory for reports (default: ./output)"
    )

    parser.add_argument(
        "--no-docx",
        action="store_true",
        help="Skip DOCX report generation"
    )

    parser.add_argument(
        "--no-dashboard",
        action="store_true",
        help="Skip HTML dashboard generation"
    )

    parser.add_argument(
        "--include-raw-data",
        action="store_true",
        help="Include raw data points in DOCX report"
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )

    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress progress output"
    )

    args = parser.parse_args()

    # Setup
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)

    if not args.quiet:
        print_banner()

    # Prepare output directory
    output_dir = os.path.abspath(args.output)
    os.makedirs(output_dir, exist_ok=True)

    # Clean domain name for filenames
    clean_domain = args.domain.replace(".", "_").replace("/", "")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Progress callback
    progress_callback = None if args.quiet else print_progress

    # Initialize orchestrator
    orchestrator = ValuationOrchestrator(progress_callback=progress_callback)
    analyzer = ValuationAnalyzer()

    try:
        # Run valuation
        if not args.quiet:
            print(f"\nAnalyzing: {args.domain}")
            print(f"Iterations: {args.iterations}")
            print(f"Output: {output_dir}\n")

        # Run async valuation
        report = asyncio.run(
            orchestrator.run(
                domain=args.domain,
                iterations=args.iterations,
                output_dir=output_dir
            )
        )

        profile = report.company

        # Print summary
        if not args.quiet:
            print_summary(profile, analyzer)

        # Generate reports
        generated_files = []

        if not args.no_docx:
            docx_path = os.path.join(output_dir, f"valuation_{clean_domain}_{timestamp}.docx")
            if not args.quiet:
                print(f"\nGenerating DOCX report...")

            docx_gen = DocxReportGenerator()
            docx_gen.generate(report, docx_path, include_raw_data=args.include_raw_data)
            generated_files.append(("DOCX Report", docx_path))
            logger.info(f"DOCX report saved: {docx_path}")

        if not args.no_dashboard:
            html_path = os.path.join(output_dir, f"dashboard_{clean_domain}_{timestamp}.html")
            if not args.quiet:
                print(f"Generating HTML dashboard...")

            dashboard_gen = DashboardGenerator()
            dashboard_gen.generate(report, html_path)
            generated_files.append(("Dashboard", html_path))
            logger.info(f"Dashboard saved: {html_path}")

        # Print generated files
        if not args.quiet and generated_files:
            print("\nGenerated files:")
            for name, path in generated_files:
                print(f"  • {name}: {path}")

        print("\nDone!")
        return 0

    except KeyboardInterrupt:
        print("\n\nOperation cancelled by user.")
        return 130

    except Exception as e:
        logger.error(f"Error during valuation: {e}", exc_info=args.verbose)
        if not args.quiet:
            print(f"\nError: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
