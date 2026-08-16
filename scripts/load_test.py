"""Simple API load test for production readiness checks."""

from __future__ import annotations

import argparse
import asyncio
import statistics
import time

import httpx


async def _worker(
    client: httpx.AsyncClient,
    path: str,
    iterations: int,
    latencies: list[float],
) -> None:
    for _ in range(iterations):
        started = time.perf_counter()
        response = await client.get(path)
        response.raise_for_status()
        latencies.append((time.perf_counter() - started) * 1000)


async def _run(args: argparse.Namespace) -> None:
    latencies: list[float] = []
    async with httpx.AsyncClient(base_url=args.base_url, timeout=30.0) as client:
        await asyncio.gather(
            *[
                _worker(client, args.path, args.iterations, latencies)
                for _ in range(args.concurrency)
            ]
        )
    print(f"requests={len(latencies)} concurrency={args.concurrency}")
    print(f"p50={statistics.median(latencies):.1f}ms p95={statistics.quantiles(latencies, n=20)[-1]:.1f}ms")


def main() -> None:
    parser = argparse.ArgumentParser(description="Load test the OIA API")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--path", default="/api/v1/health/live")
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--iterations", type=int, default=20)
    args = parser.parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
