"""
Verifier module for PDF rendering performance tests.
Handles verification of generated PDFs in S3 bucket.
"""

import boto3
import json
import time
from datetime import datetime
from pathlib import Path
from ..utils.logging import get_logger


class Verifier:
    """
    Verifies the completion of PDF rendering jobs by checking S3.
    """

    def __init__(self, config, job_ids=None):
        """
        Initialize the verifier with configuration.

        Args:
            config: Configuration object with bucket, region, etc.
            job_ids (list, optional): List of job IDs to verify. If None, will be loaded from file.
        """
        self.config = config
        self.logger = get_logger("verifier")
        self.job_ids = job_ids
        self.completed_jobs = set()
        self.start_time = None
        self.end_time = None

        # Initialize S3 client
        self.s3 = boto3.client("s3", region_name=self.config.region)

    def load_job_ids(self, job_ids_file=None):
        """
        Load job IDs from file.

        Args:
            job_ids_file (str, optional): Path to file containing job IDs.
                If None, uses default path in test directory.

        Returns:
            list: List of job IDs
        """
        if not job_ids_file:
            job_ids_file = self.config.test_dir / "job_ids.txt"

        with open(job_ids_file, "r") as f:
            job_ids = [line.strip() for line in f if line.strip()]
            self.logger.debug(f"Loaded {len(job_ids)} job IDs from {job_ids_file}")
            self.job_ids = job_ids
            return job_ids

    def verify(self):
        """
        Verify completion of PDF rendering jobs.

        Returns:
            dict: Verification results
        """
        if not self.job_ids:
            self.load_job_ids()

        total_jobs = len(self.job_ids)
        self.logger.info(f"Starting verification of {total_jobs} job IDs")
        if not self.config.quiet:
            print(f"Verifying {total_jobs} jobs")

        self.start_time = time.time()
        self.completed_jobs = set()

        try:
            while time.time() - self.start_time < self.config.timeout:
                # Check for jobs not yet verified
                jobs_to_check = [
                    job_id
                    for job_id in self.job_ids
                    if job_id not in self.completed_jobs
                ]

                if not jobs_to_check:
                    completion_msg = "All jobs completed!"
                    if not self.config.quiet:
                        print(completion_msg)
                    self.logger.info(completion_msg)
                    break

                check_msg = f"\nChecking {len(jobs_to_check)} remaining jobs..."
                if not self.config.quiet:
                    print(check_msg)
                self.logger.info(check_msg)

                # Check batch of jobs
                newly_completed = 0
                for job_id in jobs_to_check:
                    try:
                        # Check if PDF exists in S3
                        self.s3.head_object(
                            Bucket=self.config.bucket, Key=f"{job_id}.pdf"
                        )
                        self.completed_jobs.add(job_id)
                        newly_completed += 1
                        self.logger.debug(f"Job {job_id} is complete")
                    except Exception as e:
                        # PDF not found, continue checking
                        self.logger.debug(f"Job {job_id} not yet complete: {str(e)}")
                        pass

                # Print progress
                elapsed = time.time() - self.start_time
                completion_percentage = len(self.completed_jobs) / total_jobs * 100
                current_rate = len(self.completed_jobs) / elapsed if elapsed > 0 else 0

                time_msg = f"Time elapsed: {elapsed:.2f}s"
                completion_msg = f"Completed: {len(self.completed_jobs)}/{total_jobs} ({completion_percentage:.2f}%)"
                rate_msg = f"Current rate: {current_rate:.2f} PDFs/second"
                new_msg = f"Newly completed in this batch: {newly_completed}"

                if not self.config.quiet:
                    print(time_msg)
                    print(completion_msg)
                    print(rate_msg)
                    print(new_msg)

                self.logger.info(time_msg)
                self.logger.info(completion_msg)
                self.logger.info(rate_msg)
                self.logger.info(new_msg)

                # Calculate estimated time to completion
                if current_rate > 0:
                    remaining_jobs = total_jobs - len(self.completed_jobs)
                    eta = remaining_jobs / current_rate
                    eta_msg = f"Estimated time remaining: {eta:.2f} seconds"
                    if not self.config.quiet:
                        print(eta_msg)
                    self.logger.info(eta_msg)

                # Wait before next check if not all jobs are complete
                if len(self.completed_jobs) < total_jobs:
                    self.logger.debug(
                        f"Waiting {self.config.interval} seconds before next check"
                    )
                    time.sleep(self.config.interval)

            # Final report
            self.end_time = time.time()
            elapsed = self.end_time - self.start_time

            final_results = {
                "timestamp": str(datetime.now()),
                "total_jobs": total_jobs,
                "completed_jobs": len(self.completed_jobs),
                "elapsed_seconds": elapsed,
                "throughput_per_second": len(self.completed_jobs) / elapsed
                if elapsed > 0
                else 0,
            }

            # Calculate extrapolation to 1 million
            if final_results["throughput_per_second"] > 0:
                time_for_million = 1000000 / final_results["throughput_per_second"]
                final_results["extrapolated_million_seconds"] = time_for_million
                final_results["extrapolated_million_minutes"] = time_for_million / 60

            # Store failed jobs
            if len(self.completed_jobs) < total_jobs:
                failed_jobs = set(self.job_ids) - self.completed_jobs
                final_results["failed_jobs"] = list(failed_jobs)
                final_results["failed_count"] = len(failed_jobs)

            # Save and log results
            self._save_results(final_results)
            self._log_results(final_results)

            return final_results

        except KeyboardInterrupt:
            interrupt_msg = "\nVerification interrupted!"
            if not self.config.quiet:
                print(interrupt_msg)
            self.logger.warning(interrupt_msg)

            elapsed = time.time() - self.start_time
            final_status = f"Completed: {len(self.completed_jobs)}/{total_jobs} ({len(self.completed_jobs) / total_jobs * 100:.2f}%)"
            time_elapsed = f"Time elapsed: {elapsed:.2f}s"

            if not self.config.quiet:
                print(final_status)
                print(time_elapsed)

            self.logger.info(final_status)
            self.logger.info(time_elapsed)

            return {
                "status": "interrupted",
                "completed_jobs": len(self.completed_jobs),
                "total_jobs": total_jobs,
                "elapsed_seconds": elapsed,
            }

        except Exception as e:
            self.logger.exception(f"Error during verification: {str(e)}")
            if not self.config.quiet:
                print(f"Error during verification: {str(e)}")
            return {
                "status": "error",
                "error": str(e),
                "completed_jobs": len(self.completed_jobs),
                "total_jobs": total_jobs,
            }

    def _save_results(self, results):
        """
        Save verification results to file.

        Args:
            results: Verification result dictionary
        """
        results_file = (
            self.config.test_dir / f"verification_results_{int(time.time())}.json"
        )
        with open(results_file, "w") as f:
            json.dump(results, f, indent=2)
        self.logger.info(f"Wrote verification results to {results_file}")

    def _log_results(self, results):
        """
        Log verification results to file and console.

        Args:
            results: Verification results dictionary
        """
        # Save results to JSON file
        output_file = (
            self.config.test_dir / f"verification_results_{int(time.time())}.json"
        )
        with open(output_file, "w") as f:
            json.dump(results, f, indent=2)
        self.logger.info(f"Wrote verification results to {output_file}")

        # Log results to log file only
        self.logger.info("\n--- Final Results ---")
        self.logger.info(
            f"Total jobs completed: {results['completed_jobs']}/{results['total_jobs']} "
            f"({results['completed_jobs'] / results['total_jobs'] * 100:.2f}%)"
        )
        self.logger.info(f"Total time: {results['elapsed_seconds']:.2f} seconds")
        self.logger.info(
            f"Average throughput: {results['throughput_per_second']:.2f} PDFs/second"
        )

        # Log extrapolation info if available
        if "extrapolated_million_seconds" in results:
            self.logger.info(
                f"At this rate, 1 million PDFs would take {results['extrapolated_million_seconds']:.2f}s "
                f"({results['extrapolated_million_minutes']:.2f}min)"
            )

            required_rate = 1000000 / (10 * 60)
            self.logger.info(
                f"   Need at least {required_rate:.0f} PDFs/second, current rate is {results['throughput_per_second']:.2f} PDFs/second"
            )

            # Log goal achievement
            goal_achieved = results["extrapolated_million_minutes"] <= 10
            goal_msg = (
                f"✅ Goal achieved: Would take less than 10 minutes to render 1 million PDFs"
                if goal_achieved
                else f"❌ Goal NOT achieved: Would take more than 10 minutes to render 1 million PDFs"
            )
            self.logger.info(goal_msg)

        # Report on failed jobs if any
        if "failed_jobs" in results and results["failed_count"] > 0:
            self.logger.warning(f"\nFailed jobs: {results['failed_count']}")
            if results["failed_count"] <= 10:
                for job_id in results["failed_jobs"]:
                    self.logger.warning(f"Failed job: {job_id}")

        # Console output is now handled by the TestRunner class to match user's requirements
