"""
Test runner module for PDF rendering performance tests.
Orchestrates the entire performance test process.
"""

import asyncio
import json
import os
import time
import random
import boto3
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
        # Initialize SQS client
        self.sqs = boto3.client("sqs", region_name=config.region)

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

            # Phase 1: Run load test
            self.logger.info("\nPhase 1: Sending requests...")
            load_test_results = await self.load_tester.run()

            # Phase 1.5: Check SQS queue until it's empty
            self.logger.info("\nPhase 1.5: Waiting for SQS queue to empty...")
            queue_empty_time = await self._wait_for_empty_queue()

            # Calculate processing time
            processing_time = queue_empty_time - self.start_time
            self.logger.info(f"Total processing time: {processing_time:.2f} seconds")

            # Phase 2: Verify PDF generation (sample max 100 job IDs)
            self.logger.info("\nPhase 2: Verifying PDF generation (sampling)...")
            job_ids = self._sample_job_ids(load_test_results.get("job_ids", []), 100)
            self.verifier = Verifier(self.config, job_ids)
            verify_results = self.verifier.verify()

            # Combine results
            combined_results = self._compile_results(
                load_test_results, verify_results, processing_time
            )

            # Save combined results
            self._save_combined_results(combined_results)

            # Log summary
            self._log_summary(combined_results)

            return combined_results

        except Exception as e:
            self.logger.exception(f"Error during performance test: {str(e)}")
            if not self.config.quiet:
                print(f"Error during performance test: {str(e)}")
            return {"status": "error", "error": str(e)}
        finally:
            self.end_time = time.time()
            total_duration = self.end_time - self.start_time
            self.logger.info(f"Total test duration: {total_duration:.2f} seconds")

    async def _wait_for_empty_queue(self):
        """
        Wait until the SQS queue is empty (has 0 messages).

        Returns:
            float: Timestamp when queue became empty
        """
        # Get queue URL
        try:
            queue_name = os.getenv("TEST_QUEUE_NAME", "pdf-render-queue-dev")
            response = self.sqs.get_queue_url(QueueName=queue_name)
            queue_url = response["QueueUrl"]
            self.logger.info(f"Found SQS queue URL: {queue_url}")
        except Exception as e:
            self.logger.error(f"Error getting queue URL: {str(e)}")
            raise

        # Poll queue until empty
        while True:
            try:
                response = self.sqs.get_queue_attributes(
                    QueueUrl=queue_url, AttributeNames=["ApproximateNumberOfMessages"]
                )
                msg_count = int(response["Attributes"]["ApproximateNumberOfMessages"])
                self.logger.info(f"Current queue size: {msg_count} messages")

                if not self.config.quiet:
                    print(f"Current queue size: {msg_count} messages")

                if msg_count == 0:
                    self.logger.info("Queue is empty! All PDFs have been rendered.")
                    if not self.config.quiet:
                        print("Queue is empty! All PDFs have been rendered.")
                    return time.time()

                # Wait before checking again
                await asyncio.sleep(0.2)

            except Exception as e:
                self.logger.error(f"Error checking queue: {str(e)}")
                if not self.config.quiet:
                    print(f"Error checking queue: {str(e)}")
                raise

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

    def _compile_results(self, load_results, verify_results, processing_time):
        """
        Compile load test and verification results into a single result.

        Args:
            load_results: Results from load test
            verify_results: Results from verification
            processing_time: Total processing time including SQS emptying

        Returns:
            dict: Combined results
        """
        combined = {
            "timestamp": verify_results.get("timestamp", str(time.time())),
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
            "verification": {
                "total_jobs": verify_results["total_jobs"],
                "completed_jobs": verify_results["completed_jobs"],
                "duration_seconds": verify_results["elapsed_seconds"],
                "throughput_per_second": verify_results["throughput_per_second"],
                "sample_size": verify_results["total_jobs"],
            },
        }

        # Add extrapolation data based on processing time
        if processing_time > 0:
            combined["performance"] = {
                "total_processing_time": processing_time,
                "throughput_per_second": load_results["successful_requests"]
                / processing_time,
                "extrapolated_million_seconds": 1000000
                / (load_results["successful_requests"] / processing_time)
                if processing_time > 0
                else 0,
                "extrapolated_million_minutes": (
                    1000000 / (load_results["successful_requests"] / processing_time)
                )
                / 60
                if processing_time > 0
                else 0,
            }
            combined["performance"]["goal_achieved"] = (
                combined["performance"]["extrapolated_million_minutes"] <= 10
            )

        # Add latency data if available
        if "avg_latency" in load_results:
            combined["load_test"]["latency"] = {
                "min": load_results["min_latency"],
                "max": load_results["max_latency"],
                "avg": load_results["avg_latency"],
            }
            if "latency_stddev" in load_results:
                combined["load_test"]["latency"]["stddev"] = load_results[
                    "latency_stddev"
                ]

        return combined

    def _save_combined_results(self, results):
        """
        Save combined results to file.

        Args:
            results: Combined results dictionary
        """
        results_file = self.config.test_dir / "performance_test_results.json"
        with open(results_file, "w") as f:
            json.dump(results, f, indent=2)
        self.logger.info(f"Saved combined performance test results to {results_file}")

    def _log_summary(self, results):
        """
        Log a summary of the performance test results.

        Args:
            results: Combined results dictionary
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

            # Phase 1: Request sending stats
            load_test = results["load_test"]
            print(
                f"Phase 1 - Requests: {load_test['successful_requests']}/{load_test['total_requests']} successful in {load_test['duration_seconds']:.2f}s"
            )

            # Include latency data if available
            if "latency" in load_test:
                # Calculate p90 if not provided (approximating from max since we don't have percentiles)
                p90 = load_test["latency"].get("p90", load_test["latency"]["max"] * 0.9)
                print(
                    f"  Latency: min={load_test['latency']['min']:.4f}s max={load_test['latency']['max']:.4f}s p90={p90:.4f}s avg={load_test['latency']['avg']:.4f}s"
                )

            print(
                f"  Throughput: {load_test['throughput_per_second']:.2f} requests/second"
            )
            print()

            # Phase 2: SQS empty time
            queue_empty_time = (
                results["processing"]["total_processing_time"]
                - load_test["duration_seconds"]
            )
            print(
                f"Phase 2 - Queue Processing: {queue_empty_time:.2f}s until SQS empty"
            )
            print(
                f"  Total processing time: {results['processing']['total_processing_time']:.2f}s"
            )
            print(
                f"  Throughput: {results['processing']['throughput_per_second']:.2f} PDFs/second"
            )
            print()

            # Phase 3: Verification results
            verification = results["verification"]
            print(
                f"Phase 3 - Verification: {verification['completed_jobs']}/{verification['total_jobs']} PDFs verified in S3"
            )
            print(f"  Sample size: {verification['sample_size']} job_ids")
            print(f"  Verification time: {verification['duration_seconds']:.2f}s")
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
