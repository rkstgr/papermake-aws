"""
Configuration module for PDF performance testing.
Handles command-line arguments and provides a centralized configuration object.
"""

import argparse
import logging
from pathlib import Path
import datetime


class Config:
    """
    Central configuration class for PDF performance testing.
    Handles command-line arguments and environment variables.
    """

    def __init__(self):
        """Initialize config with default values"""
        # Test parameters
        self.endpoint = None
        self.template_id = None
        self.bucket = None
        self.region = "eu-central-1"

        # Performance parameters
        self.requests = 1000
        self.concurrency = 100

        # Verification parameters
        self.interval = 5
        self.timeout = 600

        # Logging parameters
        self.log_level = logging.INFO
        self.quiet = False

        # Runtime parameters
        self.timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        # Use a central logs directory without creating a new folder for each test
        self.test_dir = Path("logs/pdf_perf_test")

    def parse_args(self):
        """Parse command-line arguments and update configuration"""
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
            "--concurrency",
            type=int,
            default=100,
            help="Number of concurrent requests (default: 100)",
        )
        parser.add_argument(
            "--region",
            default="eu-central-1",
            help="AWS region (default: eu-central-1)",
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

        args = parser.parse_args()

        # Update configuration from args
        self.endpoint = args.endpoint
        self.template_id = args.template
        self.bucket = args.bucket
        self.requests = args.requests
        self.concurrency = args.concurrency
        self.region = args.region
        self.interval = args.interval
        self.timeout = args.timeout
        self.log_level = getattr(logging, args.log_level)
        self.quiet = args.quiet

        # Override test directory if specified
        if args.output_dir:
            self.test_dir = Path(args.output_dir)

        # Create the test directory
        self.test_dir.mkdir(parents=True, exist_ok=True)

        return self


# Singleton instance
config = Config()
