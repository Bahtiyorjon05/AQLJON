"""
RAG (Retrieval-Augmented Generation) Module
Implements semantic search and document memory using FAISS and LangChain
"""

from .vector_store import VectorStoreManager
from .rag_chain import RAGChain

__all__ = ['VectorStoreManager', 'RAGChain']
