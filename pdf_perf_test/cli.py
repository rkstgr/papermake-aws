"""
Command-line interface for PDF performance testing.
"""

import asyncio
import sys
import argparse
from . import __version__
from .main import main as run_main


def parse_command():
    """Parse the command from command-line arguments"""
    parser = argparse.ArgumentParser(
        description="PDF Performance Testing Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )

    # Add subparsers for commands
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # 'test' command - run full test
    test_parser = subparsers.add_parser("test", help="Run a full performance test")
    _add_common_args(test_parser)

    # 'load' command - run just the load test
    load_parser = subparsers.add_parser("load", help="Run just the load test phase")
    _add_common_args(load_parser)

    # 'verify' command - run just the verification phase
    verify_parser = subparsers.add_parser(
        "verify", help="Run just the verification phase"
    )
    verify_parser.add_argument(
        "--job-ids-file", required=True, help="File containing job IDs to verify"
    )
    verify_parser.add_argument(
        "--bucket", required=True, help="S3 bucket containing rendered PDFs"
    )
    verify_parser.add_argument(
        "--region", default="eu-central-1", help="AWS region (default: eu-central-1)"
    )
    verify_parser.add_argument(
        "--interval",
        type=int,
        default=5,
        help="Check interval in seconds (default: 5)",
    )
    verify_parser.add_argument(
        "--timeout",
        type=int,
        default=600,
        help="Total timeout in seconds (default: 600)",
    )
    verify_parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set the logging level (default: INFO)",
    )
    verify_parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress log messages in terminal output",
    )
    verify_parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory for logs and results (default: logs/pdf_perf_test_TIMESTAMP)",
    )

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    return args


def _add_common_args(parser):
    """Add common arguments to a parser"""
    parser.add_argument("--endpoint", required=True, help="API endpoint URL")
    parser.add_argument(
        "--template", required=True, help="Template ID to use for rendering"
    )
    parser.add_argument(
        "--bucket", required=True, help="S3 bucket name where results are stored"
    )
    parser.add_argument(
        "--requests",
        type=int,
        default=1000,
        help="Number of requests to send (default: 1000)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=100,
        help="Number of concurrent requests (default: 100)",
    )
    parser.add_argument(
        "--region", default="eu-central-1", help="AWS region (default: eu-central-1)"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=5,
        help="Check interval in seconds for verification (default: 5)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=600,
        help="Total timeout in seconds for verification (default: 600)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set the logging level (default: INFO)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress log messages in terminal output",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory for logs and results (default: logs/pdf_perf_test_TIMESTAMP)",
    )


def main():
    """
    Entry point for the CLI.
    """
    args = parse_command()
    # Arguments are forwarded to the main function and handled there
    sys.exit(asyncio.run(run_main()))


if __name__ == "__main__":
    main()
