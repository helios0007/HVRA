#!/usr/bin/env python3
"""
Process all research documents and create searchable index.
Run this once to index all PDFs in the documents folder.

Usage:
    python scripts/process_documents.py
"""

import os
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from services.document_processor import DocumentProcessor

def main():
    """Process all documents and create index."""
    print("=" * 70)
    print("RESEARCH DOCUMENT PROCESSOR")
    print("=" * 70)

    # Initialize processor
    documents_dir = os.path.join(
        os.path.dirname(__file__),
        '..',
        'data',
        'documents'
    )

    print(f"\nDocuments directory: {documents_dir}")
    print(f"Checking for PDFs...\n")

    processor = DocumentProcessor(documents_dir)

    # Process all documents
    print("Processing research papers...")
    documents = processor.process_all_documents()

    if not documents:
        print("\n⚠ No documents found to process!")
        return

    print(f"\n✓ Successfully processed {len(documents)} documents\n")

    # Display statistics
    print("=" * 70)
    print("DOCUMENT INDEX STATISTICS")
    print("=" * 70)

    print(f"\nTotal documents: {processor.document_index['total_documents']}")

    print("\nIntervention types found:")
    for intervention, doc_ids in processor.document_index['by_intervention'].items():
        print(f"  • {intervention}: {len(doc_ids)} documents")

    print("\nClimate types found:")
    for climate, doc_ids in processor.document_index['by_climate'].items():
        print(f"  • {climate}: {len(doc_ids)} documents")

    print("\nConcepts found:")
    for concept, doc_ids in processor.document_index['by_concept'].items():
        print(f"  • {concept}: {len(doc_ids)} documents")

    # Save index
    print("\n" + "=" * 70)
    print("SAVING INDEX")
    print("=" * 70)

    index_path = processor.save_document_index()
    print(f"\n✓ Document index saved to: {index_path}")

    # Sample document summaries
    print("\n" + "=" * 70)
    print("SAMPLE DOCUMENTS")
    print("=" * 70)

    for i, doc in enumerate(documents[:5]):
        print(f"\n[{i+1}] {doc['filename']}")
        print(f"    Title: {doc['title']}")
        print(f"    Pages: {doc['page_count']}")
        print(f"    Keywords: {', '.join(doc['keywords'][:5])}")
        print(f"    Interventions: {', '.join(doc['intervention_types'])}")
        print(f"    Climates: {', '.join(doc['climate_types'])}")

    print("\n" + "=" * 70)
    print("✓ DOCUMENT PROCESSING COMPLETE")
    print("=" * 70)
    print("\nYour research documents are now indexed and ready for RAG!")
    print("The RAG system will automatically use them for similarity search.\n")

if __name__ == '__main__':
    main()
