"""Round management CLI for CPC server administrators.

Usage:
  # Manual step-by-step:
  uv run python scripts/run_round.py --task-id my-task start
  uv run python scripts/run_round.py --task-id my-task pair
  uv run python scripts/run_round.py --task-id my-task complete

  # Auto mode (start → wait for agents → pair → wait for reviews → complete):
  uv run python scripts/run_round.py --task-id my-task auto --wait-for-agents 3
"""

from __future__ import annotations

import argparse
import sys
import time

import httpx


def main() -> None:
    parser = argparse.ArgumentParser(description="CPC Round Manager")
    parser.add_argument("--server-url", default="http://localhost:8000",
                        help="FastAPI server URL (ignored if --supabase-url is set)")
    parser.add_argument("--supabase-url", default="", help="Supabase project URL")
    parser.add_argument("--supabase-key", default="", help="Supabase anon key")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("action", choices=["start", "pair", "complete", "status", "auto"])
    parser.add_argument("--wait-for-agents", type=int, default=2,
                        help="Number of proposals to wait for in auto mode")
    parser.add_argument("--poll-interval", type=int, default=5,
                        help="Seconds between polls in auto mode")
    parser.add_argument("--review-timeout", type=int, default=300,
                        help="Seconds to wait for reviews before forcing completion")
    args = parser.parse_args()

    if args.supabase_url and args.supabase_key:
        from cpc.supabase_client import SupabaseAPIClient
        client = SupabaseAPIClient(args.supabase_url, args.supabase_key)
        print(f"Using Supabase: {args.supabase_url}")
    else:
        client = httpx.Client(base_url=args.server_url, timeout=30)
        try:
            client.get("/health").raise_for_status()
        except Exception:
            print(f"Cannot connect to {args.server_url}")
            sys.exit(1)

    if args.action == "start":
        do_start(client, args.task_id)
    elif args.action == "pair":
        do_pair(client, args.task_id)
    elif args.action == "complete":
        do_complete(client, args.task_id)
    elif args.action == "status":
        do_status(client, args.task_id)
    elif args.action == "auto":
        do_auto(client, args.task_id, args.wait_for_agents, args.poll_interval, args.review_timeout)


def do_start(client: httpx.Client, task_id: str) -> None:
    resp = client.post(f"/rounds/{task_id}/start")
    resp.raise_for_status()
    data = resp.json()
    print(f"Round {data['round_index']} started (phase: {data['phase']})")


def do_pair(client, task_id: str) -> int:
    resp = client.post(f"/rounds/{task_id}/pair")
    if hasattr(resp, 'raise_for_status'):
        resp.raise_for_status()
    data = resp.json() if hasattr(resp, 'json') else resp
    num = data.get('num_pairings', 0)
    print(f"Created {num} pairings:")
    for p in data.get("pairings", []):
        print(f"  {p['proposer_id']} → reviewed by {p['reviewer_id']}")
    return num


def do_complete(client: httpx.Client, task_id: str) -> None:
    resp = client.post(f"/rounds/{task_id}/complete")
    resp.raise_for_status()
    data = resp.json()
    print(f"Round completed: {data['num_accepted']}/{data['num_samples']} accepted")

    # Show latest w
    latest = client.get(f"/samples/{task_id}/latest").json()
    if latest.get("status") != "no_samples":
        print(f"\nLatest w ({len(latest['content'])} chars):")
        print(latest["content"][:500])
        if len(latest["content"]) > 500:
            print("...")


def do_status(client: httpx.Client, task_id: str) -> None:
    rnd = client.get(f"/rounds/{task_id}/current").json()
    print(f"Current round: {rnd}")

    proposals = client.get(f"/proposals/{task_id}").json()
    reviews = client.get(f"/reviews/{task_id}").json()
    samples = client.get(f"/samples/{task_id}").json()
    diag = client.get(f"/diagnostics/{task_id}").json()

    print(f"Proposals: {len(proposals)}")
    print(f"Reviews: {len(reviews)}")
    print(f"Samples: {len(samples)} ({sum(1 for s in samples if s['accepted'])} accepted)")
    print(f"Diagnostics: {diag}")


def do_auto(client, task_id: str, wait_for: int, poll: int, review_timeout: int = 300) -> None:
    """Automated rounds: loops until Ctrl+C.

    Each round: start → wait for proposals → pair → wait for reviews → complete → next.
    Handles odd agent counts and review timeouts.
    """
    # Initialize W pool
    print(f"Initializing W pool with {wait_for} slots...")
    client.post(f"/w-pool/{task_id}/init", json={"num_slots": wait_for})

    # Wait for agents to register
    print(f"Waiting for {wait_for} agents to register...")
    while True:
        agents = client.get("/agents").json()
        if len(agents) >= wait_for:
            print(f"Got {len(agents)} agents: {[a.get('id', a.get('agent_id', '?')) for a in agents]}")
            break
        print(f"  {len(agents)}/{wait_for} agents, waiting {poll}s...")
        time.sleep(poll)

    round_num = 0
    try:
        while True:
            round_num += 1
            print(f"\n{'='*50}")
            print(f"AUTO ROUND {round_num}")
            print(f"{'='*50}")

            # Start
            do_start(client, task_id)
            rnd = client.get(f"/rounds/{task_id}/current").json()
            round_index = rnd.get("round_index", 0)

            # Wait for proposals
            print(f"\nWaiting for {wait_for} proposals...")
            while True:
                proposals = client.get(f"/proposals/{task_id}").json()
                current_round_proposals = [p for p in proposals if p.get("round_index") == round_index]
                count = len(current_round_proposals)
                if count >= wait_for:
                    print(f"Got {count} proposals")
                    break
                print(f"  {count}/{wait_for} proposals, waiting {poll}s...")
                time.sleep(poll)

            # Pair (handles odd counts — one reviewer gets 2 assignments)
            print()
            pair_result = do_pair(client, task_id)
            num_pairings = pair_result if isinstance(pair_result, int) else 0

            # Wait for reviews with timeout
            print(f"\nWaiting for reviews (timeout: {review_timeout}s)...")
            review_start = time.time()
            while True:
                reviews = client.get(f"/reviews/{task_id}").json()
                current_round_reviews = [r for r in reviews if r.get("round_index") == round_index]

                # Check if we have all expected reviews
                if len(current_round_reviews) >= num_pairings and num_pairings > 0:
                    print(f"Got all {len(current_round_reviews)} reviews")
                    break

                # At least some reviews came in
                if len(current_round_reviews) > 0:
                    elapsed = time.time() - review_start
                    if elapsed > review_timeout / 2:
                        print(f"Got {len(current_round_reviews)} reviews, proceeding (partial timeout)")
                        break

                # Full timeout
                elapsed = time.time() - review_start
                if elapsed > review_timeout:
                    print(f"Review timeout ({review_timeout}s). Got {len(current_round_reviews)} reviews, proceeding.")
                    break

                print(f"  {len(current_round_reviews)} reviews, waiting {poll}s... ({int(elapsed)}s/{review_timeout}s)")
                time.sleep(poll)

            # Complete
            print()
            do_complete(client, task_id)

            print(f"\nRound {round_num} done. Starting next round...")
            time.sleep(2)

    except KeyboardInterrupt:
        print(f"\n\nStopped after {round_num} rounds.")


if __name__ == "__main__":
    main()
