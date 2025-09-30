"""Document Generation Module

This module provides functionality for generating various document types including:
- PDF documents
- Excel spreadsheets
- Word documents
- PowerPoint presentations

The module follows a facade pattern with a main DocumentGenerator class that
coordinates between specialized generators for each document type.
"""

# Import main classes for easier access
from .document_generator import DocumentGenerator
from .base_generator import BaseDocumentGenerator
from .pdf_generator import PDFGenerator
from .excel_generator import ExcelGenerator
from .word_generator import WordGenerator
from .advanced_ppt_generator import AdvancedPPTGenerator

__all__ = [
    'DocumentGenerator',
    'BaseDocumentGenerator',
    'PDFGenerator',
    'ExcelGenerator',
    'WordGenerator',
    'AdvancedPPTGenerator'
]