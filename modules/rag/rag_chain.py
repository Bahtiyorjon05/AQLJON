"""
RAG Chain - Combines vector search with Gemini for intelligent answers
Based on 2025 LangChain best practices
"""
import logging
from typing import List, Optional
from .vector_store import VectorStoreManager

logger = logging.getLogger(__name__)


class RAGChain:
    """
    RAG Chain that combines semantic search with Gemini AI

    Features:
    - Retrieves relevant context from user's documents
    - Generates answers using Gemini with retrieved context
    - Handles cases when no relevant documents found
    """

    def __init__(self, gemini_model, vector_store: VectorStoreManager):
        """
        Initialize RAG chain

        Args:
            gemini_model: Gemini model instance
            vector_store: VectorStoreManager instance
        """
        self.model = gemini_model
        self.vector_store = vector_store
        logger.info("✅ RAGChain initialized")

    async def query(self, chat_id: str, question: str, k: int = 3, context_window: int = 500) -> str:
        """
        Query user's documents and generate answer

        Args:
            chat_id: User's chat ID
            question: User's question
            k: Number of documents to retrieve
            context_window: Max characters per document chunk

        Returns:
            Generated answer based on retrieved documents
        """
        try:
            # Retrieve relevant documents
            results = self.vector_store.search(chat_id, question, k=k)

            if not results:
                return (
                    "🔍 Afsuski, sizning hujjatlaringizda bu mavzuga oid ma'lumot topmadim.\n\n"
                    "💡 Biror hujjat yuboring, keyin qayta so'rang!"
                )

            # Build context from retrieved documents
            context_parts = []
            for i, result in enumerate(results, 1):
                content = result['content'][:context_window]
                metadata = result['metadata']
                file_name = metadata.get('file_name', 'Unknown')

                context_parts.append(
                    f"[Hujjat {i}: {file_name}]\n{content}\n"
                )

            context = "\n\n".join(context_parts)

            # Generate answer using Gemini
            prompt = f"""Sizda foydalanuvchining hujjatlaridan quyidagi ma'lumotlar bor:

{context}

Foydalanuvchi savoli: {question}

Faqat yuqoridagi hujjatlardagi ma'lumotlarga asoslanib javob bering.
Agar javob hujjatlarda bo'lmasa, "Bu haqda hujjatlarda ma'lumot yo'q" deb ayting.
Javobingizda qaysi hujjatdan foydalanganingizni ko'rsating.
Do'stona va tabiiy tilda javob bering, emoji ishlating."""

            response = self.model.generate_content(prompt)

            # Extract text from response
            if response and hasattr(response, 'text'):
                return response.text.strip()
            elif response and hasattr(response, 'candidates') and response.candidates:
                candidate = response.candidates[0]
                if hasattr(candidate, 'content') and candidate.content:
                    return candidate.content.parts[0].text.strip()

            return "❌ Javob generatsiya qilishda xatolik yuz berdi."

        except Exception as e:
            logger.error(f"Error in RAG query for {chat_id}: {e}")
            return "❌ Xatolik yuz berdi. Qaytadan urinib ko'ring."

    def add_document_to_memory(self, chat_id: str, content: str, metadata: dict):
        """
        Add document to vector store (convenience method)

        Args:
            chat_id: User's chat ID
            content: Document content
            metadata: Document metadata
        """
        self.vector_store.add_document(chat_id, content, metadata)
        logger.info(f"Added document to RAG memory for user {chat_id}")

    def get_user_stats(self, chat_id: str) -> dict:
        """Get user's RAG statistics"""
        return self.vector_store.get_stats(chat_id)
