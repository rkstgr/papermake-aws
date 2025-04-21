"""
Main entry point for PDF performance testing.
"""

import asyncio
import sys
from pathlib import Path
import logging
from .config import config
from .utils.logging import setup_logging, get_logger
from .core.runner import TestRunner


async def main():
    """
    Main function for running PDF performance tests.

    Returns:
        int: Exit code
    """
    try:
        # Parse command-line arguments
        config.parse_args()

        # Create the test directory if it doesn't exist
        Path(config.test_dir).mkdir(parents=True, exist_ok=True)

        # Set up logging with the improved system
        setup_logging(
            log_dir=config.test_dir,
            log_level=config.log_level,
            console_output=False,  # Never output logs to console, use print statements instead
        )

        # Get logger
        logger = get_logger("main")
        logger.info(
            f"Starting PDF performance test v{__import__('pdf_perf_test').__version__}"
        )

        # Run the test
        runner = TestRunner(config)
        results = await runner.run()

        # Check if any errors occurred
        if results.get("status") == "error":
            logger.error(f"Test failed: {results.get('error')}")
            return 1

        # Check if goal was achieved
        if "performance" in results and not results["performance"]["goal_achieved"]:
            logger.info("Test completed but performance goal was not met")
            return 2

        logger.info("Test completed successfully")
        return 0

    except Exception as e:
        print(f"Unhandled error: {str(e)}")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
