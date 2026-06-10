import json
import os
from typing import List, Dict, Any
from pathlib import Path
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
from .document_processor import DocumentProcessor

class RAGRetrievalEnhanced:
    """
    Enhanced Retrieval-Augmented Generation system.
    Loads both case studies AND research documents,
    provides unified semantic search across all sources.
    """

    def __init__(self, knowledge_base_path: str = None, documents_dir: str = None):
        """
        Initialize enhanced RAG system.

        Args:
            knowledge_base_path: Path to intervention_cases.json
            documents_dir: Path to documents folder
        """
        # Load embedding model
        self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')

        # Set paths
        if knowledge_base_path is None:
            knowledge_base_path = os.path.join(
                os.path.dirname(__file__),
                '..',
                'data',
                'intervention_cases.json'
            )

        if documents_dir is None:
            documents_dir = os.path.join(
                os.path.dirname(__file__),
                '..',
                'data',
                'documents'
            )

        self.knowledge_base_path = knowledge_base_path
        self.documents_dir = documents_dir

        # Storage
        self.cases = []
        self.documents = []
        self.case_embeddings = []
        self.document_embeddings = []
        self.similarity_threshold = 0.5

        # Initialize
        self._load_knowledge_base()
        self._load_documents()
        self._embed_cases()
        self._embed_documents()

    def _load_knowledge_base(self):
        """Load case studies from JSON."""
        try:
            with open(self.knowledge_base_path, 'r') as f:
                data = json.load(f)
                self.cases = data.get('cases', [])
            print(f"✓ Loaded {len(self.cases)} case studies")
        except FileNotFoundError:
            print(f"⚠ Case studies not found at {self.knowledge_base_path}")
            self.cases = []

    def _load_documents(self):
        """Load processed research documents."""
        doc_index_path = os.path.join(
            os.path.dirname(self.documents_dir),
            'documents_index.json'
        )

        # If index doesn't exist, process documents first
        if not os.path.exists(doc_index_path):
            print("Processing research documents...")
            processor = DocumentProcessor(self.documents_dir)
            processor.process_all_documents()
            processor.save_document_index(doc_index_path)

        # Load processed documents
        try:
            with open(doc_index_path, 'r') as f:
                data = json.load(f)
                self.documents = data.get('documents', [])
            print(f"✓ Loaded {len(self.documents)} research documents")
        except FileNotFoundError:
            print(f"⚠ Documents not found at {doc_index_path}")
            self.documents = []

    def _embed_cases(self):
        """Create embeddings for case studies."""
        if not self.cases:
            return

        case_texts = [self._create_case_text(case) for case in self.cases]
        self.case_embeddings = self.embedding_model.encode(case_texts, convert_to_tensor=False)
        print(f"✓ Created embeddings for {len(self.case_embeddings)} cases")

    def _embed_documents(self):
        """Create embeddings for research documents."""
        if not self.documents:
            return

        doc_texts = [self._create_document_text(doc) for doc in self.documents]
        self.document_embeddings = self.embedding_model.encode(doc_texts, convert_to_tensor=False)
        print(f"✓ Created embeddings for {len(self.document_embeddings)} documents")

    def _create_case_text(self, case: Dict) -> str:
        """Create searchable text from case study."""
        context = case.get('building_context', {})
        vulnerability = case.get('initial_vulnerability', {})
        metadata = case.get('metadata', {})

        text = f"""
        Case: {case.get('case_id', 'unknown')}
        Climate: {metadata.get('climate_type', 'unknown')}
        Height: {context.get('avg_height_m', 0)}m
        Density: {context.get('building_density', 'unknown')}
        Type: {context.get('building_type', 'unknown')}
        SVF: {context.get('sky_view_factor', 0)}
        Score: {vulnerability.get('score', 0)}/10
        UTCI: {vulnerability.get('peak_utci_celsius', 0)}°C
        Drivers: {', '.join(vulnerability.get('drivers', []))}
        Interventions: {self._get_intervention_types(case)}
        Impact: {case.get('results', {}).get('temperature_reduction_celsius', 0)}°C
        {case.get('lessons_learned', '')}
        """
        return text

    def _create_document_text(self, doc: Dict) -> str:
        """Create searchable text from research document."""
        text = f"""
        Title: {doc.get('title', 'unknown')}
        Author: {doc.get('author', 'unknown')}
        Keywords: {', '.join(doc.get('keywords', []))}
        Concepts: {', '.join(doc.get('concepts', []))}
        Interventions: {', '.join(doc.get('intervention_types', []))}
        Climates: {', '.join(doc.get('climate_types', []))}
        Text: {doc.get('extracted_text', '')[:1000]}
        """
        return text

    def _get_intervention_types(self, case: Dict) -> str:
        """Extract intervention types from case."""
        interventions = case.get('interventions_applied', [])
        types = [i.get('type', 'unknown') for i in interventions]
        return ', '.join(types)

    def retrieve_similar_cases(
        self,
        building_context: Dict,
        vulnerability_drivers: List[str],
        climate_type: str = None,
        top_k: int = 3
    ) -> List[Dict]:
        """
        Retrieve similar case studies.

        Args:
            building_context: Building characteristics
            vulnerability_drivers: List of drivers
            climate_type: Climate classification
            top_k: Number to retrieve

        Returns:
            List of similar cases with scores
        """
        if not self.cases or len(self.case_embeddings) == 0:
            return []

        # Create query
        query_text = self._create_query_text(
            building_context,
            vulnerability_drivers,
            climate_type
        )

        # Embed and search
        query_embedding = self.embedding_model.encode(query_text, convert_to_tensor=False)
        similarities = cosine_similarity([query_embedding], self.case_embeddings)[0]

        # Get top k
        top_indices = np.argsort(similarities)[::-1][:top_k]

        similar_cases = []
        for idx in top_indices:
            similarity_score = float(similarities[idx])

            if similarity_score >= self.similarity_threshold:
                case = self.cases[idx].copy()
                case['similarity_score'] = similarity_score
                case['source'] = 'case_study'
                similar_cases.append(case)

        return similar_cases

    def retrieve_relevant_documents(
        self,
        building_context: Dict,
        vulnerability_drivers: List[str],
        intervention_types: List[str] = None,
        climate_type: str = None,
        top_k: int = 3
    ) -> List[Dict]:
        """
        Retrieve relevant research documents.

        Args:
            building_context: Building characteristics
            vulnerability_drivers: Drivers to address
            intervention_types: Proposed interventions
            climate_type: Climate
            top_k: Number to retrieve

        Returns:
            List of relevant documents with scores
        """
        if not self.documents or len(self.document_embeddings) == 0:
            return []

        # Create query emphasizing interventions
        query_text = self._create_document_query(
            vulnerability_drivers,
            intervention_types,
            climate_type
        )

        # Search
        query_embedding = self.embedding_model.encode(query_text, convert_to_tensor=False)
        similarities = cosine_similarity([query_embedding], self.document_embeddings)[0]

        # Get top k
        top_indices = np.argsort(similarities)[::-1][:top_k]

        relevant_docs = []
        for idx in top_indices:
            similarity_score = float(similarities[idx])

            if similarity_score >= self.similarity_threshold - 0.1:  # Slightly lower threshold
                doc = self.documents[idx].copy()
                doc['similarity_score'] = similarity_score
                doc['source'] = 'research_paper'
                relevant_docs.append(doc)

        return relevant_docs

    def _create_query_text(
        self,
        building_context: Dict,
        drivers: List[str],
        climate_type: str = None
    ) -> str:
        """Create query for case studies."""
        text = f"""
        Climate: {climate_type or 'unknown'}
        Height: {building_context.get('avg_height_m', 0)}m
        Density: {building_context.get('building_density', 'unknown')}
        Type: {building_context.get('building_type', 'unknown')}
        SVF: {building_context.get('sky_view_factor', 0)}
        Drivers: {', '.join(drivers)}
        """
        return text

    def _create_document_query(
        self,
        drivers: List[str],
        interventions: List[str] = None,
        climate_type: str = None
    ) -> str:
        """Create query for research documents."""
        intervention_text = ', '.join(interventions) if interventions else 'various'
        text = f"""
        Climate: {climate_type or 'any'}
        Drivers: {', '.join(drivers)}
        Interventions: {intervention_text}
        Urban design heat mitigation cooling thermal comfort
        """
        return text

    def retrieve_all_relevant(
        self,
        building_context: Dict,
        vulnerability_drivers: List[str],
        intervention_types: List[str] = None,
        climate_type: str = None,
        cases_top_k: int = 3,
        docs_top_k: int = 3
    ) -> Dict[str, List]:
        """
        Unified retrieval: get both case studies AND relevant papers.

        Returns:
            Dict with 'cases' and 'documents' lists
        """
        cases = self.retrieve_similar_cases(
            building_context,
            vulnerability_drivers,
            climate_type,
            cases_top_k
        )

        docs = self.retrieve_relevant_documents(
            building_context,
            vulnerability_drivers,
            intervention_types,
            climate_type,
            docs_top_k
        )

        return {
            'cases': cases,
            'documents': docs,
            'total_sources': len(cases) + len(docs)
        }

    def get_document_summary(self, doc_id: str) -> Dict:
        """Get summary of a research document."""
        for doc in self.documents:
            if doc.get('document_id') == doc_id:
                return {
                    'id': doc_id,
                    'title': doc.get('title'),
                    'filename': doc.get('filename'),
                    'keywords': doc.get('keywords', [])[:10],
                    'concepts': doc.get('concepts', []),
                    'intervention_types': doc.get('intervention_types', []),
                    'climate_types': doc.get('climate_types', []),
                    'thermal_impacts': doc.get('thermal_impacts', {})
                }
        return {}

    def extract_case_insights(self, cases: List[Dict]) -> Dict:
        """Extract insights from case studies."""
        if not cases:
            return {}

        insights = {
            'successful_interventions': [],
            'avg_thermal_impact': 0,
            'lessons': []
        }

        intervention_impacts = {}
        total_impact = 0

        for case in cases:
            interventions = case.get('interventions_applied', [])
            results = case.get('results', {})

            for intervention in interventions:
                int_type = intervention.get('type', 'unknown')
                if int_type not in intervention_impacts:
                    intervention_impacts[int_type] = []

            thermal_impact = results.get('temperature_reduction_celsius', 0)
            total_impact += thermal_impact

            if case.get('lessons_learned'):
                insights['lessons'].append(case['lessons_learned'])

        if len(cases) > 0:
            insights['avg_thermal_impact'] = total_impact / len(cases)

        all_interventions = []
        for case in cases:
            for intervention in case.get('interventions_applied', []):
                all_interventions.append(intervention.get('type', 'unknown'))

        from collections import Counter
        if all_interventions:
            counter = Counter(all_interventions)
            insights['successful_interventions'] = [
                {'type': itype, 'frequency': freq}
                for itype, freq in counter.most_common(5)
            ]

        return insights

    def get_statistics(self) -> Dict:
        """Get RAG system statistics."""
        return {
            'total_cases': len(self.cases),
            'total_documents': len(self.documents),
            'case_embeddings': len(self.case_embeddings),
            'document_embeddings': len(self.document_embeddings),
            'embedding_model': 'all-MiniLM-L6-v2',
            'similarity_threshold': self.similarity_threshold
        }
