import json
import os
from typing import List, Dict, Any
from pathlib import Path
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

class RAGRetrieval:
    """
    Retrieval-Augmented Generation system for intervention suggestions.
    Loads case studies from knowledge base and retrieves similar cases
    based on building context and vulnerability drivers.
    """

    def __init__(self, knowledge_base_path: str = None):
        """
        Initialize RAG system with embedding model and knowledge base.

        Args:
            knowledge_base_path: Path to intervention_cases.json
        """
        # Load embedding model (lightweight, efficient for local use)
        self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')

        # Load knowledge base
        if knowledge_base_path is None:
            # Default path
            knowledge_base_path = os.path.join(
                os.path.dirname(__file__),
                '..',
                'data',
                'intervention_cases.json'
            )

        self.knowledge_base_path = knowledge_base_path
        self.cases = []
        self.case_embeddings = []
        self.similarity_threshold = 0.5

        self._load_knowledge_base()
        self._embed_cases()

    def _load_knowledge_base(self):
        """Load intervention cases from JSON file."""
        try:
            with open(self.knowledge_base_path, 'r') as f:
                data = json.load(f)
                self.cases = data.get('cases', [])
            print(f"Loaded {len(self.cases)} cases from knowledge base")
        except FileNotFoundError:
            print(f"Warning: Knowledge base not found at {self.knowledge_base_path}")
            self.cases = []

    def _embed_cases(self):
        """Create embeddings for all cases for similarity search."""
        if not self.cases:
            return

        # Create text representations of each case for embedding
        case_texts = []
        for case in self.cases:
            text = self._create_case_text(case)
            case_texts.append(text)

        # Embed all cases
        self.case_embeddings = self.embedding_model.encode(case_texts, convert_to_tensor=False)
        print(f"Created embeddings for {len(self.case_embeddings)} cases")

    def _create_case_text(self, case: Dict) -> str:
        """Create text representation of a case for embedding."""
        context = case.get('building_context', {})
        vulnerability = case.get('initial_vulnerability', {})
        metadata = case.get('metadata', {})

        text = f"""
        Climate: {metadata.get('climate_type', 'unknown')}
        Building height: {context.get('avg_height_m', 0)}m
        Building density: {context.get('building_density', 'unknown')}
        Building type: {context.get('building_type', 'unknown')}
        Sky view factor: {context.get('sky_view_factor', 0)}
        Vulnerability score: {vulnerability.get('score', 0)}/10
        Peak UTCI: {vulnerability.get('peak_utci_celsius', 0)}°C
        Drivers: {', '.join(vulnerability.get('drivers', []))}
        Interventions: {self._get_intervention_types(case)}
        Results: {case.get('results', {}).get('net_thermal_improvement', 'unknown')}
        """
        return text

    def _get_intervention_types(self, case: Dict) -> str:
        """Extract intervention types from a case."""
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
        Retrieve similar cases based on building context and vulnerability drivers.

        Args:
            building_context: Dict with avg_height_m, building_density, building_type, etc.
            vulnerability_drivers: List of vulnerability driver names
            climate_type: Climate classification if available
            top_k: Number of similar cases to retrieve

        Returns:
            List of similar case dicts with similarity scores
        """
        if not self.cases or len(self.case_embeddings) == 0:
            return []

        # Create query text from building context and drivers
        query_text = self._create_query_text(
            building_context,
            vulnerability_drivers,
            climate_type
        )

        # Embed query
        query_embedding = self.embedding_model.encode(query_text, convert_to_tensor=False)

        # Calculate similarities
        similarities = cosine_similarity([query_embedding], self.case_embeddings)[0]

        # Get top k similar cases
        top_indices = np.argsort(similarities)[::-1][:top_k]

        similar_cases = []
        for idx in top_indices:
            similarity_score = float(similarities[idx])

            # Filter by threshold
            if similarity_score >= self.similarity_threshold:
                case = self.cases[idx].copy()
                case['similarity_score'] = similarity_score
                similar_cases.append(case)

        return similar_cases

    def _create_query_text(
        self,
        building_context: Dict,
        drivers: List[str],
        climate_type: str = None
    ) -> str:
        """Create query text from building context and drivers."""
        text = f"""
        Climate: {climate_type or 'unknown'}
        Building height: {building_context.get('avg_height_m', 0)}m
        Building density: {building_context.get('building_density', 'unknown')}
        Building type: {building_context.get('building_type', 'unknown')}
        Sky view factor: {building_context.get('sky_view_factor', 0)}
        Vulnerability score: {building_context.get('vulnerability_score', 0)}/10
        Peak UTCI: {building_context.get('peak_utci_celsius', 0)}°C
        Drivers: {', '.join(drivers)}
        """
        return text

    def get_case_interventions(self, case_id: str) -> List[Dict]:
        """Get intervention details from a specific case."""
        for case in self.cases:
            if case.get('case_id') == case_id:
                return case.get('interventions_applied', [])
        return []

    def extract_case_insights(self, cases: List[Dict]) -> Dict:
        """
        Extract key insights from retrieved cases.

        Args:
            cases: List of case study dicts

        Returns:
            Dict with extracted insights
        """
        if not cases:
            return {}

        insights = {
            'successful_interventions': [],
            'avg_thermal_impact': 0,
            'common_patterns': [],
            'implementation_timeline': 0,
            'lessons': []
        }

        # Aggregate intervention types and impacts
        intervention_impacts = {}
        total_impact = 0

        for case in cases:
            interventions = case.get('interventions_applied', [])
            results = case.get('results', {})
            lessons = case.get('lessons_learned', '')

            for intervention in interventions:
                int_type = intervention.get('type', 'unknown')
                if int_type not in intervention_impacts:
                    intervention_impacts[int_type] = []

            thermal_impact = results.get('temperature_reduction_celsius', 0)
            total_impact += thermal_impact

            impl_time = results.get('timeline_months', 0)
            insights['implementation_timeline'] += impl_time

            if lessons:
                insights['lessons'].append(lessons)

        # Calculate averages and compile results
        if len(cases) > 0:
            insights['avg_thermal_impact'] = total_impact / len(cases)
            insights['implementation_timeline'] = insights['implementation_timeline'] / len(cases)

        # Get most common intervention types
        all_interventions = []
        for case in cases:
            for intervention in case.get('interventions_applied', []):
                all_interventions.append(intervention.get('type', 'unknown'))

        from collections import Counter
        if all_interventions:
            counter = Counter(all_interventions)
            insights['successful_interventions'] = [
                {'type': itype, 'frequency': freq}
                for itype, freq in counter.most_common(3)
            ]

        return insights

    def rank_interventions_by_driver(
        self,
        drivers: List[str],
        cases: List[Dict]
    ) -> List[Dict]:
        """
        Rank interventions based on how well they address specific drivers.

        Args:
            drivers: List of vulnerability drivers
            cases: List of case studies

        Returns:
            Ranked list of interventions with driver alignment scores
        """
        if not cases:
            return []

        intervention_scores = {}

        # Collect all interventions and score them
        for case in cases:
            interventions = case.get('interventions_applied', [])
            case_drivers_raw = case.get('initial_vulnerability', {}).get('drivers', [])
            case_impact = case.get('results', {}).get('temperature_reduction_celsius', 0)
            similarity = case.get('similarity_score', 1.0)

            # Extract driver names (handle both string and dict formats)
            case_driver_names = []
            for d in case_drivers_raw:
                if isinstance(d, dict):
                    case_driver_names.append(d.get('driver', 'unknown'))
                elif isinstance(d, str):
                    case_driver_names.append(d)

            # Score based on how many drivers this case addressed
            driver_match = len(set(case_driver_names) & set(drivers)) / max(len(drivers), 1)

            for intervention in interventions:
                int_type = intervention.get('type', 'unknown')

                if int_type not in intervention_scores:
                    intervention_scores[int_type] = {
                        'type': int_type,
                        'total_score': 0,
                        'case_count': 0,
                        'avg_impact': 0,
                        'examples': []
                    }

                # Score: driver match × case similarity × case impact
                score = driver_match * similarity * (case_impact / 10.0)
                intervention_scores[int_type]['total_score'] += score
                intervention_scores[int_type]['case_count'] += 1
                intervention_scores[int_type]['avg_impact'] += case_impact
                intervention_scores[int_type]['examples'].append(case.get('case_id'))

        # Calculate averages and sort
        ranked = []
        for int_type, data in intervention_scores.items():
            if data['case_count'] > 0:
                data['avg_impact'] = data['avg_impact'] / data['case_count']
                data['final_score'] = data['total_score'] / data['case_count']
                ranked.append(data)

        # Sort by final score descending
        ranked.sort(key=lambda x: x['final_score'], reverse=True)

        return ranked
