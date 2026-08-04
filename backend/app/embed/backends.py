"""Embedding 后端实现：sentence-transformers（本地）与 Ollama（BGE-M3）"""

import logging

from ..config import settings

logger = logging.getLogger(__name__)


class EmbeddingBackend:
    """统一的 Embedding 接口"""

    def __init__(self):
        self._model = None
        self._loaded = False

    def load(self):
        raise NotImplementedError

    def encode(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError

    @property
    def is_loaded(self) -> bool:
        return self._loaded


class SentenceTransformerBackend(EmbeddingBackend):
    """使用 sentence-transformers 本地模型"""

    def load(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            logger.info("Loading embedding model: %s ...", settings.EMBED_MODEL)
            self._model = SentenceTransformer(settings.EMBED_MODEL)
            self._loaded = True
            logger.info("Embedding model loaded: %s", settings.EMBED_MODEL)
        return self

    def encode(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        self.load()
        # 分批编码，避免大批量文本 OOM
        batch_size = 32
        all_embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            batch_embeddings = self._model.encode(batch, normalize_embeddings=True)
            all_embeddings.extend(batch_embeddings.tolist())
        return all_embeddings


class OllamaBackend(EmbeddingBackend):
    """使用 Ollama 的 Embedding API"""

    def load(self):
        self._loaded = True
        return self

    def encode(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        import requests
        embeddings = []
        for text in texts:
            resp = requests.post(
                f"{settings.OLLAMA_HOST}/api/embeddings",
                json={"model": settings.EMBED_MODEL, "prompt": text},
                timeout=30,
            )
            resp.raise_for_status()
            embeddings.append(resp.json()["embedding"])
        return embeddings
