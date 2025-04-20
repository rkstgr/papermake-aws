#!/usr/bin/env python
import json
import os
import time
import asyncio
import aiohttp
import argparse
import numpy as np
from generate_sample_data import generate_for_multiple_customers


async def send_request(
    session, lambda_url, data, stats, semaphore, max_retries=3, retry_delay=1
):
    """Send a single request asynchronously and record timing statistics with retries"""
    start_time = time.time()
    job_id = "unknown"
    retries = 0

    # Use semaphore to limit concurrent requests
    async with semaphore:
        while retries <= max_retries:
            try:
                async with session.post(lambda_url, json=data) as response:
                    content_type = response.headers.get("Content-Type", "")

                    # If we get a 503, retry after a delay
                    if response.status == 503:
                        if retries < max_retries:
                            retries += 1
                            await asyncio.sleep(retry_delay)
                            print(
                                f"Retrying request (attempt {retries}/{max_retries})..."
                            )
                            continue
                        else:
                            print(f"Failed after {max_retries} retries with 503 error")
                            job_id = f"failed-503-after-{max_retries}-retries"
                            break

                    if "application/json" in content_type:
                        response_data = await response.json()
                        job_id = response_data.get("job_id", "no-id")
                    else:
                        # Handle non-JSON response
                        text = await response.text()

                        # Try to parse the text as JSON
                        try:
                            response_data = json.loads(text)
                            job_id = response_data.get("job_id", "no-id")
                        except json.JSONDecodeError:
                            job_id = f"text-response-{response.status}"
                            print(
                                f"Warning: Received non-JSON response with status {response.status}"
                            )

                    # Ensure job_id is always set
                    if not job_id:
                        job_id = f"unknown-{response.status}"

                    # Check for successful response status
                    if response.status >= 400:
                        print(f"Error: Received status code {response.status}")

                    # If we got here, we either succeeded or failed with a non-503 error
                    break

            except Exception as e:
                if retries < max_retries:
                    retries += 1
                    await asyncio.sleep(retry_delay)
                    print(
                        f"Retrying after error: {str(e)} (attempt {retries}/{max_retries})..."
                    )
                    continue
                else:
                    print(f"Error during request after {retries} retries: {str(e)}")
                    job_id = f"error-{str(e)[:20]}"
                    break

    end_time = time.time()
    duration_ms = (end_time - start_time) * 1000

    stats.append(duration_ms)
    return job_id, duration_ms


async def send_all_requests(requests_data, lambda_url, concurrency_limit=10):
    """Send all requests with limited concurrency and collect statistics"""
    stats = []
    results = []

    # Create a semaphore to limit concurrent requests
    semaphore = asyncio.Semaphore(concurrency_limit)

    # Start measuring total processing time
    total_start_time = time.time()

    async with aiohttp.ClientSession() as session:
        tasks = []
        for data in requests_data:
            request_body = {"template_id": "trade_confirmation.typ", "data": data}
            tasks.append(
                send_request(session, lambda_url, request_body, stats, semaphore)
            )

        results = await asyncio.gather(*tasks)

    # Calculate total processing time
    total_end_time = time.time()
    total_duration_seconds = total_end_time - total_start_time

    return stats, results, total_duration_seconds


def print_stats(stats):
    """Calculate and print statistics"""
    if not stats:
        print("No requests were made!")
        return

    stats_array = np.array(stats)

    print("\n--- Request Statistics ---")
    print(f"Total requests: {len(stats)}")
    print(f"Min time: {np.min(stats_array):.2f} ms")
    print(f"Average time: {np.mean(stats_array):.2f} ms")
    print(f"P90 time: {np.percentile(stats_array, 90):.2f} ms")
    print(f"Max time: {np.max(stats_array):.2f} ms")
    print("------------------------\n")


def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Send multiple fake requests to Lambda API"
    )
    parser.add_argument(
        "-c", "--customers", type=int, default=1, help="Number of customers to generate"
    )
    parser.add_argument(
        "-cn",
        "--confirmations",
        type=int,
        default=1,
        help="Number of confirmations per customer",
    )
    parser.add_argument(
        "-cl",
        "--concurrency-limit",
        type=int,
        default=10,
        help="Maximum number of concurrent requests",
    )
    args = parser.parse_args()

    # Get Lambda URL from environment variable
    lambda_url = os.environ.get("LAMBDA_URL")
    if not lambda_url:
        print("Error: LAMBDA_URL environment variable not set")
        return

    print(
        f"Generating data for {args.customers} customers with {args.confirmations} confirmations each..."
    )

    # Generate the trade confirmation data
    all_confirmations = generate_for_multiple_customers(
        num_customers=args.customers, confirmations_per_customer=args.confirmations
    )

    total_requests = len(all_confirmations)
    print(
        f"Sending {total_requests} requests to {lambda_url} with max {args.concurrency_limit} concurrent requests"
    )

    # Send all requests and collect statistics
    stats, results, total_duration = asyncio.run(
        send_all_requests(all_confirmations, lambda_url, args.concurrency_limit)
    )

    # Print statistics
    print_stats(stats)

    # Print total execution time
    print(f"Total time to process all requests: {total_duration:.2f} seconds")

    # Print a few sample results
    if results:
        sample_size = min(5, len(results))
        print(f"Sample of {sample_size} results:")
        for i in range(sample_size):
            job_id, duration = results[i]
            print(f"  Job {i + 1}: ID {job_id}, took {duration:.2f} ms")


if __name__ == "__main__":
    main()
