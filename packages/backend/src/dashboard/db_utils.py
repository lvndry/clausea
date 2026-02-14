"""Dashboard database utilities using isolated database connections."""

import asyncio
import weakref

import certifi
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from src.core.config import config
from src.core.logging import get_logger
from src.models.document import Document
from src.models.product import Product

logger = get_logger(__name__)

MONGO_URI = config.database.mongodb_uri


def get_database_name() -> str:
    """Get the database name from config or extract from URI."""
    if config.database.mongodb_database:
        return config.database.mongodb_database

    # Extract from URI: mongodb://host:port/database_name
    if "/" in MONGO_URI:
        parts = MONGO_URI.split("/")
        if len(parts) > 1:
            db_name = parts[-1].split("?")[0]  # Remove query parameters
            if db_name:
                logger.info(f"Extracted database name '{db_name}' from MongoDB URI")
                return db_name

    return "clausea"


DATABASE_NAME = get_database_name()

# Cache clients per event loop using weak references
_loop_clients: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, AsyncIOMotorClient] = (
    weakref.WeakKeyDictionary()
)
_loop_dbs: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, AsyncIOMotorDatabase] = (
    weakref.WeakKeyDictionary()
)


def _get_current_loop() -> asyncio.AbstractEventLoop | None:
    """Get the current event loop, or None if no loop is available."""
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        try:
            return asyncio.get_event_loop()
        except RuntimeError:
            return None


def _create_client() -> AsyncIOMotorClient:
    """Create a new MongoDB client."""
    if "+srv" in MONGO_URI:
        return AsyncIOMotorClient(MONGO_URI, tls=True, tlsCAFile=certifi.where())
    return AsyncIOMotorClient(MONGO_URI)


async def _get_dashboard_client() -> AsyncIOMotorClient:
    """Get or create a MongoDB client for the current event loop."""
    loop = _get_current_loop()

    # If no loop, create a standalone client
    if loop is None:
        client = _create_client()
        logger.info(f"Dashboard connected to MongoDB: {MONGO_URI}")
        logger.info(f"Using database: {DATABASE_NAME}")
        return client

    # Check if we already have a client for this event loop
    if loop in _loop_clients:
        return _loop_clients[loop]

    # Create and cache a new client for this event loop
    client = _create_client()
    _loop_clients[loop] = client
    _loop_dbs[loop] = client[DATABASE_NAME]

    logger.info(f"Dashboard connected to MongoDB: {MONGO_URI}")
    logger.info(f"Using database: {DATABASE_NAME}")

    return client


async def _get_dashboard_database() -> AsyncIOMotorDatabase:
    """Get the database instance for the current event loop."""
    loop = _get_current_loop()

    if loop is None:
        # No loop, create client and return its database
        client = await _get_dashboard_client()
        return client[DATABASE_NAME]

    if loop in _loop_dbs:
        return _loop_dbs[loop]

    # Ensure client is created (this will also create the db)
    await _get_dashboard_client()
    assert loop in _loop_dbs
    return _loop_dbs[loop]


class DashboardDB:
    """Database connection wrapper for Streamlit dashboard.

    Creates clients lazily within the current event loop context to avoid
    "Event loop is closed" errors when used across different event loops.
    """

    def __init__(self) -> None:
        self._db: AsyncIOMotorDatabase | None = None
        self._client: AsyncIOMotorClient | None = None

    async def connect(self) -> None:
        """Ensure connection is available - creates client in current event loop."""
        if self._client is None:
            self._client = await _get_dashboard_client()
            self._db = await _get_dashboard_database()

    @property
    def db(self) -> AsyncIOMotorDatabase:
        """Get the database instance."""
        if self._db is None:
            raise ValueError("Database not initialized - call connect() first")
        return self._db

    @property
    def client(self) -> AsyncIOMotorClient:
        """Get the client instance."""
        if self._client is None:
            raise ValueError("Client not initialized - call connect() first")
        return self._client


async def get_dashboard_db(cached: bool = True) -> DashboardDB:
    """
    Get a dashboard database instance.

    Args:
        cached: Ignored - we always cache clients per event loop.

    Returns:
        DashboardDB instance
    """
    db = DashboardDB()
    await db.connect()
    return db


def _normalize_mongo_doc(doc: dict) -> dict:
    doc_dict = dict(doc)
    # Always remove _id - we only use id in Clausea
    doc_dict.pop("_id", None)
    return doc_dict


# Product functions
async def get_all_products_isolated() -> list[Product]:
    """Get all products with an isolated database connection, sorted by name."""
    db = await get_dashboard_db()
    try:
        raw_products = await db.db.products.find().sort("name", 1).to_list(length=None)
        logger.info(f"Retrieved {len(raw_products)} raw product documents from MongoDB")

        if not raw_products:
            logger.warning("No products found in database")
            return []

        products = []
        for raw_product in raw_products:
            try:
                product_dict = _normalize_mongo_doc(raw_product)

                # Ensure id exists and is a string
                if "id" not in product_dict:
                    logger.error(f"Product document missing 'id' field: {raw_product}")
                    continue

                product_dict["id"] = str(product_dict["id"])
                products.append(Product(**product_dict))
            except Exception as e:
                logger.error(f"Error converting product document to Product object: {e}")
                logger.error(f"Problematic document: {raw_product}")
                continue

        logger.info(f"Successfully converted {len(products)} products")

        if raw_products and not products:
            logger.warning(
                f"Retrieved {len(raw_products)} documents from MongoDB but failed to convert any to Product objects. "
                "Check the error logs above for details about conversion failures."
            )

        return products
    except Exception as e:
        logger.error(f"Error getting products: {e}", exc_info=True)
        return []


async def get_product_by_slug_isolated(slug: str) -> Product | None:
    """Get a product by slug with an isolated database connection."""
    db = await get_dashboard_db()
    try:
        product = await db.db.products.find_one({"slug": slug})
        if product:
            product_dict = _normalize_mongo_doc(product)
            return Product(**product_dict)
        return None
    except Exception as e:
        logger.error(f"Error getting product by slug {slug}: {e}")
        return None


async def create_product_isolated(product: Product) -> bool:
    """Create a new product with an isolated database connection."""
    db = await get_dashboard_db()
    try:
        await db.db.products.insert_one(product.model_dump())
        logger.info(f"Created product {product.name} with ID {product.id}")
        return True
    except Exception as e:
        logger.error(f"Error creating product {product.name}: {e}")
        return False


async def update_product_isolated(product: Product) -> bool:
    """Update an existing product with an isolated database connection."""
    db = await get_dashboard_db()
    try:
        result = await db.db.products.update_one({"id": product.id}, {"$set": product.model_dump()})
        success = result.modified_count > 0
        if success:
            logger.info(f"Updated product {product.id}")
        return bool(success)
    except Exception as e:
        logger.error(f"Error updating product {product.id}: {e}")
        return False


async def delete_product_isolated(product_id: str) -> bool:
    """Delete a product with an isolated database connection."""
    db = await get_dashboard_db()
    try:
        result = await db.db.products.delete_one({"id": product_id})
        success = result.deleted_count > 0
        if success:
            logger.info(f"Deleted product {product_id}")
        return bool(success)
    except Exception as e:
        logger.error(f"Error deleting product {product_id}: {e}")
        return False


# Document functions
async def get_product_documents_isolated(product_slug: str) -> list[Document]:
    """Get all documents for a product with an isolated database connection."""
    db = await get_dashboard_db()
    try:
        product = await db.db.products.find_one({"slug": product_slug})
        if not product:
            logger.warning(f"Product with slug {product_slug} not found")
            return []

        product_id = product.get("id")
        if not product_id:
            logger.error(f"Product {product_slug} has no ID")
            return []

        documents = await db.db.documents.find({"product_id": product_id}).to_list(length=None)
        result = []
        for doc in documents:
            try:
                doc_dict = _normalize_mongo_doc(doc)
                result.append(Document(**doc_dict))
            except Exception as e:
                logger.error(f"Error converting document to Document object: {e}")
                continue
        return result
    except Exception as e:
        logger.error(f"Error getting documents for product {product_slug}: {e}")
        return []


async def get_product_documents_by_id_isolated(product_id: str) -> list[Document]:
    """Get all documents for a product by product_id with an isolated database connection."""
    db = await get_dashboard_db()
    try:
        documents = await db.db.documents.find({"product_id": product_id}).to_list(length=None)
        result = []
        for doc in documents:
            try:
                doc_dict = _normalize_mongo_doc(doc)
                result.append(Document(**doc_dict))
            except Exception as e:
                logger.error(f"Error converting document to Document object: {e}")
                continue
        return result
    except Exception as e:
        logger.error(f"Error getting documents for product_id {product_id}: {e}")
        return []


async def get_all_documents_isolated() -> list[Document]:
    """Get all documents with an isolated database connection."""
    db = await get_dashboard_db()
    try:
        documents = await db.db.documents.find().to_list(length=None)
        result = []
        for doc in documents:
            try:
                doc_dict = _normalize_mongo_doc(doc)
                result.append(Document(**doc_dict))
            except Exception as e:
                logger.error(f"Error converting document to Document object: {e}")
                continue
        return result
    except Exception as e:
        logger.error(f"Error getting all documents: {e}")
        return []


async def get_document_counts_by_product() -> dict[str, int]:
    """Get document counts for all products with an isolated database connection.

    Returns:
        Dictionary mapping product_id to document count
    """
    db = await get_dashboard_db()
    try:
        pipeline = [{"$group": {"_id": "$product_id", "count": {"$sum": 1}}}]
        results = await db.db.documents.aggregate(pipeline).to_list(length=None)

        counts = {result["_id"]: result["count"] for result in results if result.get("_id")}
        logger.info(f"Retrieved document counts for {len(counts)} products")
        return counts
    except Exception as e:
        logger.error(f"Error getting document counts by product: {e}")
        return {}
