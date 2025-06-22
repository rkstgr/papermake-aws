"""
Load tester module for PDF rendering performance tests.
Handles sending requests to the API endpoint and collecting metrics.
"""

import asyncio
import aiohttp
import json
import time
import statistics
from pathlib import Path
from ..utils.logging import get_logger
from ..utils.data_generator import generate_trade_confirmation


class LoadTester:
    """
    Handles sending concurrent API requests and collecting performance metrics.
    """

    def __init__(self, config):
        """
        Initialize the load tester with configuration.

        Args:
            config: Configuration object with endpoint, template_id, batch_size, etc.
        """
        self.config = config
        self.logger = get_logger("load_tester")

        # Results and metrics
        self.job_ids = []
        self.latencies = []
        self.start_time = None
        self.end_time = None
        self.successful_requests = 0

    async def send_batch_request(self, session, batch_start):
        """
        Send a batch of render requests to the API.

        Args:
            session: aiohttp ClientSession
            batch_start: Starting index for this batch

        Returns:
            list: List of booleans indicating success/failure for each request in the batch
        """
        start_time = time.time()

        batch_payloads = []
        for i in range(self.config.batch_size):
            request_id = batch_start + i
            data = generate_trade_confirmation(request_id)
            batch_payloads.append(
                {"template_id": self.config.template_id, "data": data}
            )

        payload = {"jobs": batch_payloads}

        try:
            async with session.post(self.config.endpoint, json=payload) as response:
                response_data = json.loads(await response.text())
                end_time = time.time()
                batch_latency = end_time - start_time

                if response.status == 200:
                    batch_results = []
                    # New API returns results array with job_id and s3_key
                    for result in response_data.get("results", []):
                        if result.get("status") == "success":
                            self.job_ids.append(result["job_id"])
                            self.latencies.append(batch_latency / self.config.batch_size)
                            self.successful_requests += 1
                            batch_results.append(True)
                        else:
                            batch_results.append(False)

                    if len(self.job_ids) % 100 == 0:
                        progress_msg = (
                            f"Sent {len(self.job_ids)} requests. "
                            f"Current rate: {len(self.job_ids) / (time.time() - self.start_time):.2f} req/sec"
                        )
                        if not self.config.quiet:
                            print(progress_msg)
                        self.logger.info(progress_msg)

                    success_count = sum(1 for result in response_data.get("results", []) if result.get("status") == "success")
                    self.logger.debug(
                        f"Batch request starting at {batch_start} succeeded with {success_count} successful results, "
                        f"latency: {batch_latency:.4f}s"
                    )
                    return batch_results
                else:
                    error_msg = f"Error response {response.status}: {response_data}"
                    if not self.config.quiet:
                        print(error_msg)
                    self.logger.error(error_msg)
                    return [False] * self.config.batch_size
        except Exception as e:
            error_msg = f"Batch request error: {e}"
            if not self.config.quiet:
                print(error_msg)
            self.logger.error(error_msg)
            return [False] * self.config.batch_size

    async def run(self):
        """
        Run the load test with specified concurrency and batch size.

        Returns:
            dict: Test results
        """
        self.start_time = time.time()
        self.job_ids = []
        self.latencies = []
        self.successful_requests = 0

        start_msg = (
            f"Starting load test: {self.config.requests} requests with "
            f"concurrency {self.config.concurrency} and batch size {self.config.batch_size}"
        )
        if not self.config.quiet:
            print(start_msg)
        self.logger.info(start_msg)

        endpoint_msg = f"API Endpoint: {self.config.endpoint}"
        template_msg = f"Template ID: {self.config.template_id}"
        if not self.config.quiet:
            print(endpoint_msg)
            print(template_msg)
        self.logger.info(endpoint_msg)
        self.logger.info(template_msg)

        # Create a connection pool with specified limits
        connector = aiohttp.TCPConnector(limit=self.config.concurrency)
        self.logger.debug(f"Created TCP connector with limit {self.config.concurrency}")

        async with aiohttp.ClientSession(connector=connector) as session:
            # Create a list of batch tasks
            tasks = [
                self.send_batch_request(session, i)
                for i in range(0, self.config.requests, self.config.batch_size)
            ]
            self.logger.debug(f"Created {len(tasks)} batch request tasks")

            # Execute tasks in batches to maintain concurrency
            for i in range(0, len(tasks), self.config.concurrency):
                batch = tasks[i : i + self.config.concurrency]
                self.logger.debug(
                    f"Executing batch of {len(batch)} tasks starting at index {i}"
                )
                await asyncio.gather(*batch)

        # Calculate statistics
        self.end_time = time.time()
        duration = self.end_time - self.start_time

        results = {
            "total_time": duration,
            "successful_requests": self.successful_requests,
            "total_requests": self.config.requests,
            "job_ids": self.job_ids,
            "throughput": self.successful_requests / duration if duration > 0 else 0,
        }

        if self.latencies:
            results.update(
                {
                    "min_latency": min(self.latencies),
                    "max_latency": max(self.latencies),
                    "avg_latency": statistics.mean(self.latencies),
                }
            )

            if len(self.latencies) > 1:
                results["latency_stddev"] = statistics.stdev(self.latencies)

        # Extrapolation to 1 million
        if results["throughput"] > 0:
            time_for_million = 1000000 / results["throughput"]
            results["time_for_million_seconds"] = time_for_million
            results["time_for_million_minutes"] = time_for_million / 60

        # Save results
        self._save_results(results)
        self._log_results(results)

        return results

    def _save_results(self, results):
        """
        Save test results to files.

        Args:
            results: Test result dictionary
        """
        # Save job IDs to file for verification
        job_ids_path = self.config.test_dir / "job_ids.txt"
        with open(job_ids_path, "w") as f:
            for job_id in self.job_ids:
                f.write(f"{job_id}\n")
        self.logger.info(f"Saved {len(self.job_ids)} job IDs to {job_ids_path}")

        # Save full results as JSON
        results_path = self.config.test_dir / "load_test_results.json"
        with open(results_path, "w") as f:
            json.dump(results, f, indent=2)
        self.logger.info(f"Saved load test results to {results_path}")

    def _log_results(self, results):
        """
        Log the results of the load test.

        Args:
            results: Load test results dictionary
        """
        # Save results to file
        results_file = self.config.test_dir / "load_test_results.json"
        with open(results_file, "w") as f:
            json.dump(results, f, indent=2)
        self.logger.info(f"Saved load test results to {results_file}")

        # Calculate P90 latency if we have the raw latencies
        if "latencies" in results and len(results["latencies"]) > 0:
            sorted_latencies = sorted(results["latencies"])
            p90_index = int(len(sorted_latencies) * 0.9)
            results["p90_latency"] = sorted_latencies[p90_index]

        # Add to log file, but make console output more minimal
        self.logger.info("\n--- Load Test Results ---")

        time_msg = f"Total time: {results['total_time']:.2f} seconds"
        self.logger.info(time_msg)

        success_msg = f"Successful requests: {results['successful_requests']}/{results['total_requests']}"
        self.logger.info(success_msg)

        throughput_msg = (
            f"Average throughput: {results['throughput']:.2f} requests/second"
        )
        self.logger.info(throughput_msg)

        # Log latency metrics if available
        if "min_latency" in results:
            min_latency_msg = f"Min latency: {results['min_latency']:.4f} seconds"
            max_latency_msg = f"Max latency: {results['max_latency']:.4f} seconds"
            avg_latency_msg = f"Average latency: {results['avg_latency']:.4f} seconds"
            self.logger.info(min_latency_msg)
            self.logger.info(max_latency_msg)
            self.logger.info(avg_latency_msg)

            # Add P90 latency to logs
            if "p90_latency" in results:
                p90_latency_msg = f"P90 latency: {results['p90_latency']:.4f} seconds"
                self.logger.info(p90_latency_msg)

            if "latency_stddev" in results:
                stddev_msg = f"Latency standard deviation: {results['latency_stddev']:.4f} seconds"
                self.logger.info(stddev_msg)

        # Calculate and log extrapolation metrics
        if results["throughput"] > 0:
            million_seconds = 1000000 / results["throughput"]
            million_minutes = million_seconds / 60
            extrapolation_msg = f"\nAt this rate, 1 million PDFs would take {million_seconds:.2f} seconds ({million_minutes:.2f} minutes)"
            self.logger.info(extrapolation_msg)

            required_rate = 1000000 / (10 * 60)  # 10 minutes in seconds
            required_rate_msg = f"Required rate for 1M PDFs in 10 minutes: {required_rate:.0f} PDFs/second"
            self.logger.info(required_rate_msg)

        # The console output is now handled by the TestRunner class
        # to keep the UI more concise according to user's requirements
