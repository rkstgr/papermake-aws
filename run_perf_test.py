#!/usr/bin/env python3
"""
Entry point script for PDF performance testing.
This script provides backward compatibility with the original command structure.
"""

import sys
import asyncio
import argparse
import logging
import os
from pathlib import Path
from pdf_perf_test.config import config
from pdf_perf_test.utils.logging import setup_logging, get_logger
from pdf_perf_test.core.runner import TestRunner


def parse_args():
    """Parse command line arguments without subcommands"""
    parser = argparse.ArgumentParser(
        description="Performance test for PDF rendering service"
    )

    # Required arguments
    parser.add_argument("--endpoint", required=True, help="API endpoint URL")
    parser.add_argument(
        "--template", required=True, help="Template ID to use for rendering"
    )
    parser.add_argument(
        "--bucket", required=True, help="S3 bucket name where results are stored"
    )

    # Optional arguments
    parser.add_argument(
        "--requests",
        type=int,
        default=1000,
        help="Number of requests to send (default: 1000)",
    )

    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Number of requests to send in a batch (default: 100)",
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
        help="Output directory for logs and results (default: logs/pdf_perf_test)",
    )

    return parser.parse_args()


async def main():
    """Main function that runs the performance test"""
    args = parse_args()

    # Update config with parsed arguments
    config.endpoint = args.endpoint
    config.template_id = args.template
    config.bucket = args.bucket
    config.requests = args.requests
    config.batch_size = args.batch_size
    config.concurrency = args.concurrency
    config.region = args.region
    config.interval = args.interval
    config.timeout = args.timeout
    config.log_level = getattr(logging, args.log_level)
    config.quiet = args.quiet

    # Create test directory if not specified or ensure it exists
    if args.output_dir:
        config.test_dir = Path(args.output_dir)

    os.makedirs(config.test_dir, exist_ok=True)

    # Set up logging
    setup_logging(
        log_dir=config.test_dir,
        log_level=config.log_level,
        console_output=not config.quiet,
    )

    # Get logger
    logger = get_logger("main")
    logger.info("Starting PDF performance test")

    # Run the test
    runner = TestRunner(config)
    results = await runner.run()

    # Return appropriate exit code
    if results.get("status") == "error":
        logger.error(f"Test failed: {results.get('error')}")
        return 1

    if "performance" in results and not results["performance"]["goal_achieved"]:
        logger.info("Test completed but performance goal was not met")
        return 2

    logger.info("Test completed successfully")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
