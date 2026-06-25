"""Environment helpers for operational scripts."""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

load_dotenv()


def resolve_production(*, use_production: bool, require: bool = False) -> None:
    if not use_production:
        if require:
            print("ERROR: --production is required for this command", file=sys.stderr)
            sys.exit(1)
        return
    prod_uri = os.getenv("PRODUCTION_MONGO_URI")
    if not prod_uri:
        print("ERROR: PRODUCTION_MONGO_URI not set", file=sys.stderr)
        sys.exit(1)
    os.environ["MONGO_URI"] = prod_uri


def mongo_uri(*, prefer_production: bool = False) -> str:
    if prefer_production:
        uri = os.getenv("PRODUCTION_MONGO_URI")
        if uri:
            return uri
    uri = os.getenv("MONGO_URI")
    if not uri:
        print(
            "ERROR: MONGO_URI not set (use --production for PRODUCTION_MONGO_URI)", file=sys.stderr
        )
        sys.exit(1)
    return uri


def open_db(*, prefer_production: bool = False) -> tuple[AsyncIOMotorClient, AsyncIOMotorDatabase]:
    client = AsyncIOMotorClient(mongo_uri(prefer_production=prefer_production))
    db_name = os.getenv("MONGODB_DATABASE", "clausea")
    return client, client[db_name]


def job_url(product) -> str:
    if product.crawl_base_urls:
        return product.crawl_base_urls[0]
    if product.domains:
        return f"https://{product.domains[0]}"
    return f"https://clausea.co/products/{product.slug}"
