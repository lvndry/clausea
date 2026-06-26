import asyncio
import os
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
from pymongo import UpdateOne

# Add the packages/backend directory to sys.path to import src
backend_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(backend_dir))

load_dotenv(backend_dir / ".env")

from src.core.database import close_motor_client, db_session


async def stagger_monitoring(batch_size: int = 20, start_days_offset: int = 1):
    """
    One-time script to stagger existing monitoring schedules.
    Spreads them into batches of `batch_size`, starting `start_days_offset` from now.
    """
    try:
        async with db_session() as db:
            schedules = await db.monitoring_schedules.find({"enabled": True}).to_list(None)

            # Sort by current due date to preserve some order.
            # Use 'or datetime.max' to handle cases where next_crawl_due_at is None.
            schedules.sort(key=lambda x: x.get("next_crawl_due_at") or datetime.max)

            total = len(schedules)
            if total == 0:
                print("No enabled schedules found.")
                return

            print(f"Staggering {total} products into batches of {batch_size}...")

            now = datetime.now()
            # Start from the beginning of tomorrow to have clean daily batches
            base_date = (now + timedelta(days=start_days_offset)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )

            requests = []
            for i, schedule in enumerate(schedules):
                batch_num = i // batch_size
                # Set next_due to (batch_num) days from base_date
                # Plus random hours/minutes to spread within that day
                random_offset = timedelta(
                    hours=random.randint(0, 23),
                    minutes=random.randint(0, 59),
                    seconds=random.randint(0, 59),
                )
                new_due = base_date + timedelta(days=batch_num) + random_offset

                requests.append(
                    UpdateOne(
                        {"product_slug": schedule["product_slug"]},
                        {"$set": {"next_crawl_due_at": new_due}},
                    )
                )

            if requests:
                result = await db.monitoring_schedules.bulk_write(requests)
                print(f"Successfully staggered {result.modified_count} products.")
                print(f"First batch starts: {base_date.date()}")
                print(
                    f"Last batch starts:  {(base_date + timedelta(days=(total - 1) // batch_size)).date()}"
                )
    finally:
        close_motor_client()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Stagger monitoring schedules into batches")
    parser.add_argument("--batch-size", type=int, default=20, help="Number of products per day")
    parser.add_argument(
        "--start-offset", type=int, default=1, help="Days from now to start the first batch"
    )
    parser.add_argument(
        "--production",
        action="store_true",
        help="Actually run against production (requires PRODUCTION_MONGO_URI)",
    )

    args = parser.parse_args()

    if args.production:
        prod_uri = os.getenv("PRODUCTION_MONGO_URI")
        if not prod_uri:
            print("ERROR: PRODUCTION_MONGO_URI not set")
            sys.exit(1)
        os.environ["MONGO_URI"] = prod_uri
        print("!!! RUNNING AGAINST PRODUCTION !!!")
    else:
        print("Running against LOCAL database (use --production for prod)")

    asyncio.run(stagger_monitoring(batch_size=args.batch_size, start_days_offset=args.start_offset))
