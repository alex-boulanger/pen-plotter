"""
Populate the cache — the only file in the series that touches the network.

Queries Open Topo Data for each place in `data/places.json` and writes one
elevation tile per place in `data/cache/`. The sketch only reads this cache.

Public service limits (api.opentopodata.org):
    100 points per request, 1 request per second, 1000 requests per day.

A 48 x 48 grid contains 2304 points, so 24 requests and ~30 s per place.

The script is resumable. Progress is written into a `.partial.npz` file.

    python fetch_all.py                  # all missing places
    python fetch_all.py --only cervin    # one place
    python fetch_all.py --force          # fetch again even if cache exists
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import requests

from terrain import (
    CACHE_DIR,
    DATASET,
    EXTENT_M,
    GRID_N,
    cache_path,
    grid_points,
    load_places,
    save_tile,
)

API_URL = "https://api.opentopodata.org/v1/{dataset}"

BATCH_SIZE = 100          # maximum de points par requête
MIN_INTERVAL_S = 1.1      # 1 req/s, avec une marge
DAILY_LIMIT = 1000
SAFETY_LIMIT = 950        # on n'épuise pas le quota jusqu'à la dernière requête

MAX_RETRIES = 5
BACKOFF_BASE_S = 2.0
RETRY_STATUS = {429, 500, 502, 503, 504}

REQUEST_TIMEOUT_S = 30.0


class QuotaExhausted(RuntimeError):
    """The request budget for this session is exhausted."""


class Fetcher:
    """Rate-limited Open Topo Data client."""

    def __init__(self, budget: int = SAFETY_LIMIT, dataset: str = DATASET):
        self.budget = budget
        self.dataset = dataset
        self.used = 0
        self._last_call = 0.0
        self._session = requests.Session()

    def _wait_turn(self) -> None:
        elapsed = time.monotonic() - self._last_call
        if elapsed < MIN_INTERVAL_S:
            time.sleep(MIN_INTERVAL_S - elapsed)

    def elevations(self, points: np.ndarray) -> list[float | None]:
        """Elevations for a batch of at most 100 (lat, lon) points."""
        if len(points) > BATCH_SIZE:
            raise ValueError(f"batch has {len(points)} points, maximum {BATCH_SIZE}")
        if self.used >= self.budget:
            raise QuotaExhausted(f"request budget reached: {self.budget}")

        locations = "|".join(f"{lat:.6f},{lon:.6f}" for lat, lon in points)
        url = API_URL.format(dataset=self.dataset)

        for attempt in range(MAX_RETRIES):
            self._wait_turn()
            self.used += 1
            self._last_call = time.monotonic()
            try:
                response = self._session.get(
                    url, params={"locations": locations}, timeout=REQUEST_TIMEOUT_S
                )
            except requests.RequestException as exc:
                last_error: str | Exception = exc
            else:
                if response.status_code == 200:
                    payload = response.json()
                    if payload.get("status") == "OK":
                        return [r["elevation"] for r in payload["results"]]
                    last_error = f"application status {payload.get('status')!r}"
                elif response.status_code in RETRY_STATUS:
                    last_error = f"HTTP {response.status_code}"
                else:
                    raise RuntimeError(
                        f"HTTP {response.status_code} : {response.text[:200]}"
                    )

            if attempt < MAX_RETRIES - 1:
                delay = BACKOFF_BASE_S * (2**attempt)
                print(f"      {last_error} — retrying in {delay:.0f} s")
                time.sleep(delay)
            if self.used >= self.budget:
                raise QuotaExhausted(f"request budget reached: {self.budget}")

        raise RuntimeError(f"failed after {MAX_RETRIES} attempts: {last_error}")


def partial_path(slug: str) -> Path:
    return CACHE_DIR / f"{slug}.partial.npz"


def _load_partial(slug: str, total: int) -> tuple[np.ndarray, int]:
    """Resume an interrupted acquisition, or start a new one."""
    path = partial_path(slug)
    if path.exists():
        with np.load(path, allow_pickle=False) as npz:
            values, done = npz["values"], int(npz["done"])
        if values.shape == (total,) and 0 <= done <= total:
            return values, done
        print(f"      incompatible partial cache, ignored ({path.name})")
    return np.full(total, np.nan), 0


def fetch_place(place: dict, fetcher: Fetcher, extent_m: float, n: int) -> Path:
    """Fetch one place tile and write it to cache."""
    slug = place["slug"]
    points = grid_points(place["lat"], place["lon"], extent_m, n)
    total = len(points)

    values, done = _load_partial(slug, total)
    n_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE
    if done:
        print(f"      resuming at {done}/{total} points")

    try:
        while done < total:
            batch = points[done : done + BATCH_SIZE]
            got = fetcher.elevations(batch)
            values[done : done + len(batch)] = [
                np.nan if e is None else float(e) for e in got
            ]
            done += len(batch)
            print(
                f"      batch {done // BATCH_SIZE}/{n_batches}"
                f"  ({done}/{total} points, {fetcher.used} requests)",
                end="\r",
                flush=True,
            )
    finally:
        print()
        if done < total:
            partial_path(slug).parent.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(partial_path(slug), values=values, done=done)
            print(f"      progress saved ({done}/{total})")

    path = save_tile(
        slug,
        values.reshape(n, n),
        name=place["name"],
        lat=place["lat"],
        lon=place["lon"],
        alt_m=float(place.get("alt_m", 0.0)),
        extent_m=extent_m,
        dataset=fetcher.dataset,
        fetched_at=datetime.now(UTC).isoformat(timespec="seconds"),
    )
    partial_path(slug).unlink(missing_ok=True)
    report(place, values.reshape(n, n), extent_m)
    return path


def report(place: dict, tile: np.ndarray, extent_m: float) -> None:
    """Basic plausibility report for a tile."""
    missing = int(np.isnan(tile).sum())
    n = tile.shape[0]
    peak = float(np.nanmax(tile))
    row, col = np.unravel_index(np.nanargmax(tile), tile.shape)
    step_m = extent_m / (n - 1)
    offset_m = np.hypot(row - (n - 1) / 2.0, col - (n - 1) / 2.0) * step_m

    print(f"      altitudes {np.nanmin(tile):.0f}-{peak:.0f} m, {missing} missing")
    expected = float(place.get("alt_m", 0.0))
    if not expected:
        return

    centre = float(tile[(n - 1) // 2 : n // 2 + 1, (n - 1) // 2 : n // 2 + 1].max())
    delta = centre - expected
    print(
        f"      expected place {expected:.0f} m — center {centre:.0f} m "
        f"({delta:+.0f} m); highest point {peak:.0f} m at {offset_m:.0f} m"
    )
    if delta > 100.0 or delta < -700.0:
        print("      <-- large center delta: check coordinates")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--only", metavar="SLUG", help="fetch only this place")
    parser.add_argument(
        "--force", action="store_true", help="fetch again even if cache exists"
    )
    parser.add_argument(
        "--budget",
        type=int,
        default=SAFETY_LIMIT,
        help=f"request cap for this session (quota: {DAILY_LIMIT}/day)",
    )
    parser.add_argument("--extent", type=float, default=EXTENT_M, help="extent, in m")
    parser.add_argument("--grid", type=int, default=GRID_N, help="grid side")
    args = parser.parse_args(argv)

    places = load_places()
    if args.only:
        places = [s for s in places if s["slug"] == args.only]
        if not places:
            print(f"unknown place: {args.only}", file=sys.stderr)
            return 2

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    fetcher = Fetcher(budget=args.budget)

    todo = [s for s in places if args.force or not cache_path(s["slug"]).exists()]
    skipped = len(places) - len(todo)
    if skipped:
        print(f"{skipped} place(s) already cached, skipped.")
    if not todo:
        print("Nothing to do.")
        return 0

    batches = (args.grid**2 + BATCH_SIZE - 1) // BATCH_SIZE
    print(
        f"{len(todo)} place(s) to fetch — {batches} requests each, "
        f"~{batches * MIN_INTERVAL_S:.0f} s, budget {args.budget}.\n"
    )

    failed: list[tuple[str, str]] = []
    for i, place in enumerate(todo, 1):
        print(f"[{i}/{len(todo)}] {place['name']} ({place['slug']})")
        try:
            path = fetch_place(place, fetcher, args.extent, args.grid)
        except QuotaExhausted as exc:
            print(f"\nStop: {exc}.")
            print("Partial cache kept; rerun later to resume.")
            failed.append((place["slug"], str(exc)))
            break
        except KeyboardInterrupt:
            print("\nInterrupted.")
            return 130
        except Exception as exc:
            print(f"      failed: {exc}")
            failed.append((place["slug"], str(exc)))
            continue
        shown = path.relative_to(Path.cwd()) if path.is_relative_to(Path.cwd()) else path
        print(f"      -> {shown}\n")

    print(f"\n{fetcher.used} requests used.")
    if failed:
        print(f"{len(failed)} failed place(s):")
        for slug, why in failed:
            print(f"  {slug} : {why}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
