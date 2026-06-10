import json
from typing import List, Dict, Any, Optional
from .llm_service import LLMService
from .rag_retrieval_enhanced import RAGRetrievalEnhanced

class ChatService:
    """
    Conversational design service combining RAG + Ollama.
    Allows users to chat about interventions and get dynamic suggestions.
    """

    def __init__(self):
        """Initialize chat service with RAG and LLM."""
        self.llm_service = LLMService()
        self.rag_service = RAGRetrievalEnhanced()

    def chat(
        self,
        message: str,
        building: Dict[str, Any],
        analysis: Dict[str, Any],
        climate_type: Optional[str] = None,
        chat_history: List[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Have a conversation about building interventions.

        Args:
            message: User's message
            building: Building context
            analysis: Vulnerability analysis
            climate_type: Climate classification
            chat_history: Previous messages for context

        Returns:
            Dict with response, suggestions, and sources
        """
        if chat_history is None:
            chat_history = []

        # Extract building/analysis context
        building_context = building.get('properties', {}) or {}
        height = building_context.get('height', building.get('height', 0))
        building_type = building_context.get('building_type', 'Unknown')
        location = building.get('location', 'Unknown location')

        vulnerability = analysis.get('vulnerability_analysis', {})
        vuln_score = vulnerability.get('score', 0)
        drivers_raw = vulnerability.get('drivers', [])

        # Extract driver names
        driver_names = []
        if drivers_raw:
            for d in (drivers_raw if isinstance(drivers_raw, list) else [drivers_raw]):
                try:
                    if isinstance(d, dict):
                        name = d.get('driver', 'unknown')
                    else:
                        name = str(d)
                    if name and name != 'unknown':
                        driver_names.append(name)
                except Exception as e:
                    print(f"Error processing driver {d}: {e}")

        climate_context = vulnerability.get('climate_context', {})
        peak_utci = climate_context.get('peak_utci_celsius', 0)

        # Step 1: RAG retrieval - get relevant cases and papers
        rag_results = self.rag_service.retrieve_all_relevant(
            building_context={
                'avg_height_m': height,
                'building_density': building_context.get('building_density', 'unknown'),
                'building_type': building_type,
                'sky_view_factor': building_context.get('sky_view_factor', 0),
            },
            vulnerability_drivers=driver_names,
            intervention_types=self._extract_intervention_types_from_message(message),
            climate_type=climate_type,
            cases_top_k=3,
            docs_top_k=3
        )

        similar_cases = rag_results.get('cases', [])
        relevant_docs = rag_results.get('documents', [])

        # Step 2: Build context-aware prompt for Ollama
        prompt = self._build_chat_prompt(
            message=message,
            building=building,
            analysis=analysis,
            similar_cases=similar_cases,
            relevant_docs=relevant_docs,
            chat_history=chat_history,
            driver_names=driver_names
        )

        # Step 3: Call Ollama for response
        llm_response = self.llm_service.generate_suggestions(
            building=building,
            analysis=analysis,
            similar_cases=similar_cases,
            baseline_strategies=[]
        )

        # Step 4: Generate conversational response
        conversational_response = self._generate_conversational_response(
            message=message,
            building=building,
            analysis=analysis,
            similar_cases=similar_cases,
            llm_response=llm_response
        )

        # Step 5: Extract intervention suggestions from response
        suggestions = self._extract_suggestions_from_response(llm_response)

        return {
            "response": conversational_response,
            "suggestions": suggestions,
            "knowledge_sources": {
                "case_studies": len(similar_cases),
                "research_papers": len(relevant_docs),
                "total": len(similar_cases) + len(relevant_docs)
            },
            "retrieved_cases": similar_cases[:2],  # Return top 2 for reference
            "retrieved_papers": relevant_docs[:2]
        }

    def _extract_intervention_types_from_message(self, message: str) -> List[str]:
        """Extract intervention types mentioned in user message."""
        intervention_keywords = {
            'tree': 'urban_forest',
            'trees': 'urban_forest',
            'forest': 'urban_forest',
            'pavement': 'cool_pavements',
            'cool': 'cool_pavements',
            'roof': 'cool_roofs',
            'water': 'water_features',
            'green': 'green_roofs',
            'shade': 'shade_structures',
            'ventilation': 'ventilation_corridors',
            'vegetation': 'green_walls'
        }

        message_lower = message.lower()
        found_types = set()

        for keyword, intervention_type in intervention_keywords.items():
            if keyword in message_lower:
                found_types.add(intervention_type)

        return list(found_types)

    def _build_chat_prompt(
        self,
        message: str,
        building: Dict,
        analysis: Dict,
        similar_cases: List[Dict],
        relevant_docs: List[Dict],
        chat_history: List[Dict],
        driver_names: List[str]
    ) -> str:
        """Build context-aware prompt for Ollama."""

        building_context = building.get('properties', {}) or {}
        vulnerability = analysis.get('vulnerability_analysis', {})

        prompt = f"""You are an expert urban climate designer having a conversation about building interventions.

BUILDING CONTEXT:
- Height: {building_context.get('height', 0)}m
- Type: {building_context.get('building_type', 'Unknown')}
- Location: {building.get('location', 'Unknown')}
- Current vulnerability score: {vulnerability.get('score', 0)}/10
- Peak UTCI: {vulnerability.get('climate_context', {}).get('peak_utci_celsius', 0)}°C
- Main issues: {', '.join(driver_names) if driver_names else 'Not specified'}

RELEVANT PRECEDENTS (from similar projects):
"""
        for case in similar_cases[:2]:
            prompt += f"- {case.get('metadata', {}).get('location_name')}: "
            prompt += f"Applied {len(case.get('interventions_applied', []))} interventions, "
            prompt += f"achieved {case.get('results', {}).get('temperature_reduction_celsius', 0)}°C improvement\n"

        prompt += f"""
RESEARCH INSIGHTS (from academic papers):
"""
        for doc in relevant_docs[:2]:
            prompt += f"- {doc.get('title')}: "
            prompt += f"Covers {', '.join(doc.get('intervention_types', [])[:2])}\n"

        prompt += f"""
CONVERSATION HISTORY:
"""
        for msg in chat_history[-3:]:  # Last 3 messages for context
            prompt += f"User: {msg.get('user_message', '')}\n"
            prompt += f"Assistant: {msg.get('assistant_message', '')}\n"

        prompt += f"""
CURRENT USER MESSAGE:
"{message}"

TASK:
Respond conversationally to the user's question about interventions for their building.
Be specific to their building context. Suggest practical interventions based on:
1. What worked in similar projects (precedents)
2. What research shows is effective
3. Their specific climate and building type

If asking about specific interventions, provide:
- Expected thermal impact (°C)
- Implementation complexity (low/medium/high)
- Timeline
- Why it works for THEIR specific building

Keep response concise (2-3 sentences) and conversational.
If suggesting interventions, format them as a simple list at the end.
"""
        return prompt

    def _generate_conversational_response(
        self,
        message: str,
        building: Dict,
        analysis: Dict,
        similar_cases: List[Dict],
        llm_response: List[Dict]
    ) -> str:
        """Generate a conversational response from LLM suggestions."""

        building_context = building.get('properties', {}) or {}

        # Start with context acknowledgment
        response = f"For your {building_context.get('height', 0)}m {building_context.get('building_type', 'building')} "
        response += f"in {building.get('location', 'this location')}, "

        # Add suggestion summary
        if llm_response:
            top_suggestion = llm_response[0]
            response += f"I'd recommend focusing on **{top_suggestion.get('name', 'intervention')}** "
            response += f"(expected ~{top_suggestion.get('expected_thermal_impact_celsius', 0)}°C improvement). "

            if similar_cases:
                case = similar_cases[0]
                response += f"We've seen this work well in {case.get('metadata', {}).get('location_name', 'similar urban contexts')}."
        else:
            response += "Let me suggest some interventions based on your building's specific challenges."

        return response

    def _extract_suggestions_from_response(self, llm_response: List[Dict]) -> List[Dict]:
        """Extract intervention suggestions from LLM response."""
        suggestions = []

        for item in llm_response:
            suggestion = {
                "type": item.get('type', 'unknown'),
                "name": item.get('name', 'Intervention'),
                "thermal_impact": item.get('expected_thermal_impact_celsius', 0),
                "complexity": item.get('implementation_complexity', 'medium'),
                "description": item.get('description', ''),
                "drivers_addressed": item.get('primary_drivers_addressed', [])
            }
            suggestions.append(suggestion)

        return suggestions

    def refine_suggestion(
        self,
        suggestion: Dict,
        feedback: str,
        building: Dict,
        analysis: Dict
    ) -> Dict:
        """
        Refine a suggestion based on user feedback.

        Args:
            suggestion: Original suggestion
            feedback: User feedback
            building: Building context
            analysis: Analysis context

        Returns:
            Refined suggestion
        """
        refined = self.llm_service.refine_suggestion(
            suggestion=suggestion,
            feedback=feedback,
            original_context={
                'building': building,
                'analysis': analysis
            }
        )
        return refined
