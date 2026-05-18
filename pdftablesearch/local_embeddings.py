"""
Local LangChain Embeddings class using SentenceTransformers.

Provides ``SentenceTransformerEmbeddings``, an implementation of
:class:`langchain_core.embeddings.Embeddings` that runs locally
using SentenceTransformers - no API key required.
"""

from __future__ import annotations

from typing import List

import os

os.environ["HF_HUB_OFFLINE"] = "1"

from langchain_core.embeddings import Embeddings
from sentence_transformers import SentenceTransformer

from pdftablesearch.utils import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Default configuration
# ---------------------------------------------------------------------------

_DEFAULT_MODEL = "BAAI/bge-m3"
# Alternative models for Korean:
# - "distiluse-base-multilingual-cased-v2" (lighter, faster)
# - "paraphrase-multilingual-MiniLM-L12-v2" (good for Korean)
# - "sentence-t5-xl-multilingual" (larger, better quality)


class SentenceTransformerEmbeddings(Embeddings):
    """LangChain-compatible Embeddings class using SentenceTransformers.

    Runs locally on your machine - no API key required. Supports Korean
    and multiple languages.

    Args:
        model_name: SentenceTransformers model name to use.
            Defaults to ``BAAI/bge-m3`` which supports Korean
            and 100+ languages with superior retrieval performance.
        device: Device to run on (``cpu`` or ``cuda``). Defaults to ``cpu``.

    Example::

        from pdftablesearch.local_embeddings import SentenceTransformerEmbeddings

        emb = SentenceTransformerEmbeddings()
        vectors = emb.embed_documents(["안녕하세요", "Hello"])
        query_vec = emb.embed_query("검색어")
    """

    def __init__(
        self,
        model_name: str = _DEFAULT_MODEL,
        device: str = "cpu",
    ) -> None:
        self.model_name = model_name
        self.device = device

        logger.info("Loading SentenceTransformer model: %s", model_name)
        self._model = SentenceTransformer(
            model_name,
            device=device,
            trust_remote_code=True,
        )
        logger.info("Model loaded successfully")

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Embed a list of document texts.

        Args:
            texts: List of document strings to embed.

        Returns:
            List of embedding vectors, one per input text.
        """
        if not texts:
            return []

        logger.debug("Embedding %d documents", len(texts))

        # SentenceTransformer.encode returns a numpy array
        embeddings = self._model.encode(
            texts,
            convert_to_numpy=True,
            show_progress_bar=False,
        )

        # Convert to list of lists
        result = embeddings.tolist()
        logger.info("Embedded %d texts successfully", len(result))
        return result

    def embed_query(self, text: str) -> List[float]:
        """Embed a single query string.

        Args:
            text: Query text to embed.

        Returns:
            Single embedding vector.
        """
        logger.debug("Embedding query: %s", text[:100])

        embedding = self._model.encode(
            text,
            convert_to_numpy=True,
            show_progress_bar=False,
        )

        return embedding.tolist()
