"""
Unified embedding provider factory for PDFTableSearch.

Provides a single entry point to create embedding instances
based on configuration, supporting both local SentenceTransformers
and remote z.ai API providers.
"""

from __future__ import annotations

from typing import Literal, Optional

from langchain_core.embeddings import Embeddings

from pdftablesearch.utils import get_logger

logger = get_logger(__name__)

ProviderType = Literal["local", "remote"]


def create_embeddings(
    provider: ProviderType = "local",
    *,
    # Remote (z.ai) settings
    api_key: Optional[str] = None,
    endpoint: Optional[str] = None,
    model: Optional[str] = None,
    timeout: int = 30,
    batch_size: int = 20,
    # Local (SentenceTransformers) settings
    local_model: str = "BAAI/bge-m3",
    device: str = "cpu",
) -> Embeddings:
    """Create an Embeddings instance based on the specified provider.

    Args:
        provider: Which embedding provider to use.
            ``"local"`` uses SentenceTransformers (no API key needed).
            ``"remote"`` uses the z.ai API (requires API key).
        api_key: z.ai API key (only for ``"remote"``).
            Falls back to ``ZAI_API_KEY`` env var.
        endpoint: Override embedding API endpoint.
        model: Override embedding model name.
        timeout: API request timeout in seconds.
        batch_size: Maximum texts per batch for remote API.
        local_model: SentenceTransformers model name.
        device: Device for local model (``"cpu"`` or ``"cuda"``).

    Returns:
        LangChain-compatible Embeddings instance.

    Example::

        from pdftablesearch.embedding_provider import create_embeddings

        # Local (default, no API key needed)
        emb = create_embeddings("local")

        # Remote (z.ai API)
        emb = create_embeddings("remote", api_key="your-key")

        # Custom local model
        emb = create_embeddings("local", local_model="distiluse-base-multilingual-cased-v2")
    """
    if provider == "local":
        from pdftablesearch.local_embeddings import SentenceTransformerEmbeddings

        actual_model = model or local_model
        logger.info(
            "Creating local embedding provider: model=%s, device=%s",
            actual_model,
            device,
        )
        return SentenceTransformerEmbeddings(
            model_name=actual_model,
            device=device,
        )

    if provider == "remote":
        from pdftablesearch.embeddings import ZaiEmbeddings

        logger.info(
            "Creating remote embedding provider: model=%s",
            model or "embedding-3",
        )
        return ZaiEmbeddings(
            api_key=api_key,
            model=model or "embedding-3",
            endpoint=endpoint,
            timeout=timeout,
            batch_size=batch_size,
        )

    raise ValueError(
        f"Unknown embedding provider: {provider!r}. "
        f"Must be 'local' or 'remote'."
    )
