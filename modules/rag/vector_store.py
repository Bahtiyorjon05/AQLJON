"""
Vector Store Manager using FAISS for semantic search
Based on 2025 best practices for RAG implementations
"""
import os
import pickle
import logging
from typing import List, Dict, Optional
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np

logger = logging.getLogger(__name__)


class VectorStoreManager:
    """
    Manages vector embeddings and semantic search using FAISS

    Features:
    - Per-user vector stores for privacy
    - Persistent storage with pickle
    - Fast similarity search
    - Automatic chunking for large documents
    """

    def __init__(self, model_name='all-MiniLM-L6-v2', storage_dir='./vector_stores'):
        """
        Initialize vector store manager

        Args:
            model_name: Sentence transformer model (all-MiniLM-L6-v2 best for speed/accuracy balance)
            storage_dir: Directory to store vector databases
        """
        self.model = SentenceTransformer(model_name)
        self.embedding_dim = 384  # all-MiniLM-L6-v2 outputs 384-dim vectors
        self.storage_dir = storage_dir
        self.user_stores = {}  # chat_id -> {index, documents, metadata}

        # Create storage directory if it doesn't exist
        os.makedirs(storage_dir, exist_ok=True)

        logger.info(f"✅ VectorStoreManager initialized with model: {model_name}")

    def _get_store_path(self, chat_id: str) -> str:
        """Get file path for user's vector store"""
        return os.path.join(self.storage_dir, f"user_{chat_id}.pkl")

    def _load_user_store(self, chat_id: str):
        """Load user's vector store from disk"""
        store_path = self._get_store_path(chat_id)

        if os.path.exists(store_path):
            try:
                with open(store_path, 'rb') as f:
                    self.user_stores[chat_id] = pickle.load(f)
                logger.info(f"Loaded vector store for user {chat_id}")
            except Exception as e:
                logger.error(f"Error loading vector store for {chat_id}: {e}")
                self._create_user_store(chat_id)
        else:
            self._create_user_store(chat_id)

    def _create_user_store(self, chat_id: str):
        """Create new vector store for user"""
        # Using IndexFlatL2 for exact search (good for <1M vectors)
        index = faiss.IndexFlatL2(self.embedding_dim)
        self.user_stores[chat_id] = {
            'index': index,
            'documents': [],
            'metadata': []
        }
        logger.info(f"Created new vector store for user {chat_id}")

    def _save_user_store(self, chat_id: str):
        """Save user's vector store to disk"""
        if chat_id not in self.user_stores:
            return

        store_path = self._get_store_path(chat_id)
        try:
            with open(store_path, 'wb') as f:
                pickle.dump(self.user_stores[chat_id], f)
            logger.info(f"Saved vector store for user {chat_id}")
        except Exception as e:
            logger.error(f"Error saving vector store for {chat_id}: {e}")

    def add_document(self, chat_id: str, content: str, metadata: Optional[Dict] = None):
        """
        Add document to user's vector store

        Args:
            chat_id: User's chat ID
            content: Document text content
            metadata: Optional metadata (file_name, type, timestamp, etc.)
        """
        # Load user store if not in memory
        if chat_id not in self.user_stores:
            self._load_user_store(chat_id)

        # Generate embedding
        try:
            embedding = self.model.encode([content])[0]

            # Add to FAISS index
            self.user_stores[chat_id]['index'].add(
                np.array([embedding], dtype='float32')
            )

            # Store document and metadata
            self.user_stores[chat_id]['documents'].append(content)
            self.user_stores[chat_id]['metadata'].append(metadata or {})

            # Save to disk
            self._save_user_store(chat_id)

            logger.info(f"Added document for user {chat_id}. Total docs: {len(self.user_stores[chat_id]['documents'])}")

        except Exception as e:
            logger.error(f"Error adding document for {chat_id}: {e}")

    def search(self, chat_id: str, query: str, k: int = 5) -> List[Dict]:
        """
        Semantic search in user's documents

        Args:
            chat_id: User's chat ID
            query: Search query
            k: Number of results to return

        Returns:
            List of dicts with 'content', 'metadata', 'score'
        """
        # Load user store if not in memory
        if chat_id not in self.user_stores:
            self._load_user_store(chat_id)

        store = self.user_stores.get(chat_id)
        if not store or len(store['documents']) == 0:
            return []

        try:
            # Generate query embedding
            query_embedding = self.model.encode([query])[0]

            # Search in FAISS
            distances, indices = store['index'].search(
                np.array([query_embedding], dtype='float32'),
                min(k, len(store['documents']))
            )

            # Prepare results
            results = []
            for i, (dist, idx) in enumerate(zip(distances[0], indices[0])):
                if idx < len(store['documents']):
                    results.append({
                        'content': store['documents'][idx],
                        'metadata': store['metadata'][idx],
                        'score': float(dist),
                        'rank': i + 1
                    })

            logger.info(f"Search for user {chat_id}: found {len(results)} results")
            return results

        except Exception as e:
            logger.error(f"Error searching for {chat_id}: {e}")
            return []

    def get_stats(self, chat_id: str) -> Dict:
        """Get statistics for user's vector store"""
        if chat_id not in self.user_stores:
            self._load_user_store(chat_id)

        store = self.user_stores.get(chat_id)
        if not store:
            return {'total_documents': 0}

        return {
            'total_documents': len(store['documents']),
            'index_size': store['index'].ntotal
        }

    def clear_user_store(self, chat_id: str):
        """Clear all documents for a user"""
        if chat_id in self.user_stores:
            del self.user_stores[chat_id]

        store_path = self._get_store_path(chat_id)
        if os.path.exists(store_path):
            os.remove(store_path)

        logger.info(f"Cleared vector store for user {chat_id}")
