"""
Test runner module for PDF rendering performance tests.
Orchestrates the entire performance test process.
"""

import asyncio
import json
import os
import time
import random
from pathlib import Path
from ..utils.logging import get_logger
from .load_tester import LoadTester
from .verifier import Verifier


class TestRunner:
    """
    Orchestrates the entire PDF rendering performance test process.
    """

    def __init__(self, config):
        """
        Initialize the test runner with configuration.

        Args:
            config: Configuration object
        """
        self.config = config
        self.logger = get_logger("test_runner")
        self.load_tester = LoadTester(config)
        self.verifier = Verifier(config)
        self.start_time = None
        self.end_time = None

    async def run(self):
        """
        Run the complete performance test.

        Returns:
            dict: Combined test results
        """
        self.start_time = time.time()
        self.logger.info("Starting PDF rendering performance test")
        self.logger.info(f"Test directory: {self.config.test_dir}")

        try:
            # Print test parameters
            self.logger.info(
                "\nStarting performance test with the following parameters:"
            )
            self.logger.info(f"API Endpoint: {self.config.endpoint}")
            self.logger.info(f"Template ID: {self.config.template_id}")
            self.logger.info(f"Requests: {self.config.requests}")
            self.logger.info(f"Concurrency: {self.config.concurrency}")
            self.logger.info(f"Result Bucket: {self.config.bucket}")
            self.logger.info(f"Region: {self.config.region}")

            # Run load test (now includes processing since it's synchronous)
            self.logger.info("\nSending requests and processing...")
            load_test_results = await self.load_tester.run()

            # Processing time is now the same as load test time (synchronous)
            processing_time = load_test_results["total_time"]
            self.logger.info(f"Total processing time: {processing_time:.2f} seconds")

            # Create final results (no verification needed)
            final_results = self._create_final_results(load_test_results, processing_time)

            # Save results
            self._save_results(final_results)

            # Log summary
            self._log_summary(final_results)

            return final_results

        except Exception as e:
            self.logger.exception(f"Error during performance test: {str(e)}")
            if not self.config.quiet:
                print(f"Error during performance test: {str(e)}")
            return {"status": "error", "error": str(e)}
        finally:
            self.end_time = time.time()
            total_duration = self.end_time - self.start_time
            self.logger.info(f"Total test duration: {total_duration:.2f} seconds")


    def _sample_job_ids(self, job_ids, max_sample=100):
        """
        Sample a maximum of max_sample job IDs from the list.

        Args:
            job_ids: List of all job IDs
            max_sample: Maximum number of job IDs to sample

        Returns:
            list: Sampled job IDs
        """
        if not job_ids:
            return []

        if len(job_ids) <= max_sample:
            return job_ids

        self.logger.info(f"Sampling {max_sample} job IDs from {len(job_ids)} total")
        return random.sample(job_ids, max_sample)

    def _create_final_results(self, load_results, processing_time):
        """
        Create final results from load test data only.

        Args:
            load_results: Results from load test
            processing_time: Total processing time (same as load test time)

        Returns:
            dict: Final results
        """
        results = {
            "timestamp": str(time.time()),
            "load_test": {
                "total_requests": load_results["total_requests"],
                "successful_requests": load_results["successful_requests"],
                "duration_seconds": load_results["total_time"],
                "throughput_per_second": load_results["throughput"],
            },
            "processing": {
                "total_processing_time": processing_time,
                "throughput_per_second": load_results["successful_requests"]
                / processing_time
                if processing_time > 0
                else 0,
            },
        }

        # Add performance extrapolation
        if processing_time > 0 and load_results["successful_requests"] > 0:
            throughput = load_results["successful_requests"] / processing_time
            results["performance"] = {
                "throughput_per_second": throughput,
                "extrapolated_million_seconds": 1000000 / throughput,
                "extrapolated_million_minutes": (1000000 / throughput) / 60,
            }
            results["performance"]["goal_achieved"] = (
                results["performance"]["extrapolated_million_minutes"] <= 10
            )

        # Add latency data if available
        if "avg_latency" in load_results:
            results["load_test"]["latency"] = {
                "min": load_results["min_latency"],
                "max": load_results["max_latency"],
                "avg": load_results["avg_latency"],
            }
            if "latency_stddev" in load_results:
                results["load_test"]["latency"]["stddev"] = load_results[
                    "latency_stddev"
                ]

        return results

    def _save_results(self, results):
        """
        Save results to file.

        Args:
            results: Results dictionary
        """
        results_file = self.config.test_dir / "performance_test_results.json"
        with open(results_file, "w") as f:
            json.dump(results, f, indent=2)
        self.logger.info(f"Saved performance test results to {results_file}")

    def _log_summary(self, results):
        """
        Log a summary of the performance test results.

        Args:
            results: Results dictionary
        """
        summary_header = "=== PDF Performance Test ==="

        # Only print to console if not in quiet mode
        if not self.config.quiet:
            print(summary_header)

            # Test config summary
            print(f"Config: endpoint={self.config.endpoint}")
            print(
                f"        template={self.config.template_id} requests={self.config.requests} concurrency={self.config.concurrency} batchsize={self.config.batch_size}"
            )
            print(f"        bucket={self.config.bucket} region={self.config.region}")
            print()

            # Request stats
            load_test = results["load_test"]
            print(
                f"Results: {load_test['successful_requests']}/{load_test['total_requests']} successful in {load_test['duration_seconds']:.2f}s"
            )

            # Include latency data if available
            if "latency" in load_test:
                print(
                    f"  Latency: min={load_test['latency']['min']:.4f}s max={load_test['latency']['max']:.4f}s avg={load_test['latency']['avg']:.4f}s"
                )

            print(
                f"  Throughput: {load_test['throughput_per_second']:.2f} PDFs/second"
            )
            print()

            # Summary and goal achievement
            if "performance" in results:
                print(
                    f"Summary: 1M PDFs would take {results['performance']['extrapolated_million_minutes']:.2f} minutes (target: 10 minutes)"
                )

                # Show goal achievement status with required rate
                required_rate = 1000000 / (10 * 60)  # 10 minutes in seconds
                current_rate = results["processing"]["throughput_per_second"]

                if results["performance"]["goal_achieved"]:
                    print(f"✅ GOAL ACHIEVED (current {current_rate:.2f} PDFs/sec)")
                else:
                    print(
                        f"❌ GOAL NOT ACHIEVED (need {required_rate:.0f} PDFs/sec, current {current_rate:.2f} PDFs/sec)"
                    )

        # Log the main points to the log file
        self.logger.info(
            f"Test completed with {results['load_test']['successful_requests']}/{results['load_test']['total_requests']} successful requests"
        )
        self.logger.info(
            f"Processing throughput: {results['processing']['throughput_per_second']:.2f} PDFs/second"
        )
        if "performance" in results:
            self.logger.info(
                f"{'Goal achieved' if results['performance']['goal_achieved'] else 'Goal not achieved'}: "
                f"{results['performance']['extrapolated_million_minutes']:.2f} minutes for 1M PDFs (target: 10 minutes)"
            )
