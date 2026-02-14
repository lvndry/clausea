import os

from pinecone import Pinecone, ServerlessSpec

from src.core.logging import get_logger

logger = get_logger(__name__)

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
if not PINECONE_API_KEY:
    raise ValueError("PINECONE_API_KEY is not set")


pc = Pinecone(api_key=PINECONE_API_KEY)
INDEX_NAME = "clausea-pinecone"


def init_pinecone_index(dimension: int, index_name: str = INDEX_NAME) -> None:
    """
    Initialize a Pinecone index with the specified dimension.

    Args:
        dimension: The dimension of the vectors to be stored in the index
        index_name: The name of the index (defaults to INDEX_NAME)
    """
    if not pc.has_index(index_name):
        pc.create_index(
            name=index_name,
            dimension=dimension,
            vector_type="dense",
            metric="dotproduct",
            spec=ServerlessSpec(cloud="aws", region="us-east-1"),
        )
        logger.info(f"Index '{index_name}' created with dimension {dimension}")
    else:
        logger.info(f"Index '{index_name}' successfully initialized")
