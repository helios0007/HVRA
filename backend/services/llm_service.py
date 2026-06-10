import json
import os
from typing import List, Dict, Any
import requests

class LLMService:
    """
    LLM-based intervention suggestion service using Ollama.
    Generates contextual intervention recommendations informed by:
    - Baseline rules-based strategies
    - RAG-retrieved similar case studies
    - Building context and vulnerability analysis
    """

    def __init__(self, model: str = None, ollama_base_url: str = None):
        """
        Initialize LLM service with Ollama.

        Args:
            model: Ollama model name (uses OLLAMA_MODEL env var if not provided, defaults to llama3.1)
            ollama_base_url: Ollama API base URL (uses OLLAMA_BASE_URL env var if not provided)
        """
        if model is None:
            model = os.getenv('OLLAMA_MODEL', 'llama3.1')

        if ollama_base_url is None:
            ollama_base_url = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')

        self.ollama_base_url = ollama_base_url
        self.model = model
        self.max_tokens = 2000

    def generate_suggestions(
        self,
        building: Dict,
        analysis: Dict,
        similar_cases: List[Dict] = None,
        baseline_strategies: List[Dict] = None
    ) -> List[Dict]:
        """
        Generate intervention suggestions using Claude.

        Args:
            building: Building context dict with height, type, location, density, properties
            analysis: Vulnerability analysis dict with score, drivers, climate_context
            similar_cases: Retrieved similar case studies from RAG
            baseline_strategies: Baseline strategies from rule-based engine

        Returns:
            List of LLM-generated intervention suggestions with metadata
        """
        # Build the prompt
        prompt = self._build_prompt(building, analysis, similar_cases, baseline_strategies)

        try:
            # Call Ollama API
            response = requests.post(
                f"{self.ollama_base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "temperature": 0.7,
                    "top_p": 0.9
                },
                timeout=300  # 5 minute timeout for LLM response
            )

            if response.status_code != 200:
                print(f"Error calling Ollama API: {response.status_code}")
                print(f"Response: {response.text}")
                return []

            # Extract response text
            response_json = response.json()
            response_text = response_json.get('response', '')

            # Parse suggestions from response
            suggestions = self._parse_suggestions(response_text)

            return suggestions

        except Exception as e:
            print(f"Error calling Ollama API: {e}")
            return []

    def _build_prompt(
        self,
        building: Dict,
        analysis: Dict,
        similar_cases: List[Dict] = None,
        baseline_strategies: List[Dict] = None
    ) -> str:
        """Build the prompt for Claude with all relevant context."""

        # Extract building context
        building_context = building.get('properties', {}) or {}
        height = building_context.get('height', building.get('height', 0))
        building_type = building_context.get('building_type', 'Unknown')
        location = building.get('location', 'Unknown location')

        # Extract vulnerability context
        vulnerability = analysis.get('vulnerability_analysis', {})
        score = vulnerability.get('score', 0)
        drivers = vulnerability.get('drivers', [])
        climate = analysis.get('vulnerability_analysis', {}).get('climate_context', {})
        peak_utci = climate.get('peak_utci_celsius', 0)

        # Format drivers
        driver_text = self._format_drivers(drivers)

        # Format similar cases
        cases_text = self._format_cases(similar_cases)

        # Format baseline strategies
        baseline_text = self._format_baseline(baseline_strategies)

        prompt = f"""You are an expert urban climate designer analyzing heat vulnerability in buildings and proposing targeted interventions.

BUILDING ANALYSIS

Building Context:
- Height: {height}m
- Type: {building_type}
- Location: {location}
- Building area: {building_context.get('area', 'Unknown')} m²

Current Thermal Vulnerability:
- Overall vulnerability score: {score}/10
- Peak thermal comfort (UTCI): {peak_utci}°C
- Heat stress hours: {climate.get('heat_stress_hours_pct', 0)}% of year

Vulnerability Drivers:
{driver_text}

CONTEXT FROM SUCCESSFUL CASES

The following case studies show successful interventions in similar contexts:
{cases_text}

BASELINE STRATEGIES (from rule-based engine)

Current system recommendations:
{baseline_text}

TASK

Based on this analysis and the successful cases, generate 3-5 intervention suggestions that:

1. DIRECTLY ADDRESS the identified vulnerability drivers
2. Are informed by what worked in similar buildings
3. Are SPECIFIC and ACTIONABLE for this particular building
4. Include realistic implementation considerations

For EACH intervention suggestion, provide JSON with:
{{
  "type": "intervention_type (e.g., urban_forest, cool_pavements, green_roofs, water_features, shade_structures, ventilation_corridors, etc.)",
  "name": "human_readable_name",
  "expected_thermal_impact_celsius": number_with_decimal,
  "implementation_complexity": "low|medium|high",
  "estimated_cost_usd": number_or_range_string,
  "timeline_months": number,
  "primary_drivers_addressed": ["driver1", "driver2"],
  "description": "2-3 sentence explanation of what this does and why it's effective here",
  "implementation_notes": "specific considerations for this building/location",
  "visualization_type": "point|polygon|line",
  "estimated_area_or_scale": "description of spatial extent"
}}

IMPORTANT:
- Return ONLY valid JSON array, no other text
- Each intervention must be achievable within 12 months
- Prioritize interventions addressing the top 2 drivers
- Consider interactions between interventions (some work better together)
- Be specific about quantities, areas, and locations based on {height}m building height and {building_type} type

Return the JSON array now:
"""
        return prompt

    def _format_drivers(self, drivers: List[Dict]) -> str:
        """Format vulnerability drivers for the prompt."""
        if not drivers:
            return "No specific drivers identified"

        text = ""
        for driver in drivers:
            if isinstance(driver, dict):
                name = driver.get('driver', 'Unknown').replace('_', ' ')
                severity = driver.get('severity', 0)
                source = driver.get('data_source', 'Analysis')
                text += f"- {name}: {severity*100:.0f}% severity (source: {source})\n"
            else:
                text += f"- {driver}\n"

        return text

    def _format_cases(self, cases: List[Dict]) -> str:
        """Format similar cases for the prompt."""
        if not cases:
            return "No similar cases found in knowledge base."

        text = ""
        for idx, case in enumerate(cases[:3], 1):  # Use top 3 cases
            metadata = case.get('metadata', {})
            results = case.get('results', {})
            interventions = case.get('interventions_applied', [])

            text += f"\nCase {idx}: {metadata.get('location_name', 'Unknown')} ({metadata.get('climate_type', 'Unknown')} climate)\n"
            text += f"  Initial: {case.get('initial_vulnerability', {}).get('score', 0)}/10 vulnerability score, "
            text += f"{case.get('initial_vulnerability', {}).get('peak_utci_celsius', 0)}°C peak UTCI\n"

            int_types = [i.get('type', 'unknown').replace('_', ' ') for i in interventions]
            text += f"  Interventions: {', '.join(int_types)}\n"

            text += f"  Results: {results.get('temperature_reduction_celsius', 0)}°C reduction, "
            text += f"{results.get('peak_utci_reduction', 0)}°C peak UTCI reduction\n"
            text += f"  Lesson: {case.get('lessons_learned', 'No lessons recorded')}\n"

        return text

    def _format_baseline(self, strategies: List[Dict]) -> str:
        """Format baseline strategies for the prompt."""
        if not strategies:
            return "No baseline strategies available."

        text = ""
        for strategy in strategies[:3]:  # Use top 3
            name = strategy.get('name', 'Unknown')
            impact = strategy.get('thermal_impact', 0)
            text += f"- {name}: {impact}°C thermal improvement\n"

        return text

    def _parse_suggestions(self, response_text: str) -> List[Dict]:
        """
        Parse JSON suggestions from Claude response.

        Handles various JSON formatting issues.
        """
        suggestions = []

        try:
            # Try to extract JSON array from response
            # Claude sometimes adds text before/after the JSON
            start_idx = response_text.find('[')
            end_idx = response_text.rfind(']') + 1

            if start_idx == -1 or end_idx == 0:
                print("No JSON array found in response")
                return []

            json_str = response_text[start_idx:end_idx]

            # Parse JSON
            parsed = json.loads(json_str)

            # Validate and clean suggestions
            for item in parsed:
                suggestion = self._validate_suggestion(item)
                if suggestion:
                    suggestions.append(suggestion)

            return suggestions

        except json.JSONDecodeError as e:
            print(f"Error parsing LLM response JSON: {e}")
            print(f"Response text: {response_text[:500]}...")
            return []

    def _validate_suggestion(self, item: Dict) -> Dict:
        """Validate and normalize a suggestion object."""
        required_fields = [
            'type',
            'name',
            'expected_thermal_impact_celsius',
            'implementation_complexity',
            'description',
            'primary_drivers_addressed'
        ]

        # Check required fields
        for field in required_fields:
            if field not in item:
                print(f"Suggestion missing required field: {field}")
                return None

        # Normalize thermal impact to float
        try:
            impact = float(item.get('expected_thermal_impact_celsius', 0))
            item['expected_thermal_impact_celsius'] = impact
        except (ValueError, TypeError):
            item['expected_thermal_impact_celsius'] = 0.0

        # Set defaults for optional fields
        if 'timeline_months' not in item:
            item['timeline_months'] = 6

        if 'estimated_cost_usd' not in item:
            item['estimated_cost_usd'] = "To be determined"

        if 'visualization_type' not in item:
            item['visualization_type'] = 'polygon'

        if 'implementation_notes' not in item:
            item['implementation_notes'] = ""

        if 'estimated_area_or_scale' not in item:
            item['estimated_area_or_scale'] = "To be determined"

        return item

    def refine_suggestion(
        self,
        suggestion: Dict,
        feedback: str,
        original_context: Dict
    ) -> Dict:
        """
        Refine a suggestion based on user feedback.

        Args:
            suggestion: The original suggestion
            feedback: User feedback on the suggestion
            original_context: Original building/analysis context

        Returns:
            Refined suggestion
        """
        prompt = f"""You are refining an intervention suggestion based on feedback.

Original suggestion:
Type: {suggestion.get('type')}
Description: {suggestion.get('description')}
Expected impact: {suggestion.get('expected_thermal_impact_celsius')}°C
Complexity: {suggestion.get('implementation_complexity')}

User feedback:
{feedback}

Based on this feedback, provide a refined version of this intervention suggestion.
Return ONLY a JSON object with the same structure as the original, with updates applied.

Refined suggestion JSON:"""

        try:
            response = requests.post(
                f"{self.ollama_base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "temperature": 0.7
                },
                timeout=300
            )

            if response.status_code != 200:
                print(f"Error calling Ollama API: {response.status_code}")
                return suggestion

            response_json = response.json()
            response_text = response_json.get('response', '')

            # Extract JSON
            start_idx = response_text.find('{')
            end_idx = response_text.rfind('}') + 1

            if start_idx != -1 and end_idx > start_idx:
                json_str = response_text[start_idx:end_idx]
                refined = json.loads(json_str)
                refined = self._validate_suggestion(refined)
                return refined

        except Exception as e:
            print(f"Error refining suggestion: {e}")

        return suggestion
