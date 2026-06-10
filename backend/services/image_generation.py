import json
import os
from typing import List, Dict, Any, Optional
from openai import OpenAI

class ImageGenerator:
    """
    AI image generation service for photorealistic urban intervention visualizations.
    Uses OpenAI DALL-E to generate street-level, aerial, and section views
    of buildings before and after proposed interventions.
    """

    def __init__(self, api_key: str = None):
        """
        Initialize image generation service with OpenAI client.

        Args:
            api_key: OpenAI API key (uses OPENAI_API_KEY env var if not provided)
        """
        if api_key is None:
            api_key = os.getenv('OPENAI_API_KEY')

        self.client = OpenAI(api_key=api_key)
        self.model = "dall-e-3"
        self.size = "1024x1024"
        self.quality = "hd"

    def generate_intervention_visualization(
        self,
        building: Dict[str, Any],
        analysis: Dict[str, Any],
        interventions: List[Dict[str, Any]],
        view_type: str = "street_level"
    ) -> Dict[str, Any]:
        """
        Generate a photorealistic visualization of building with interventions.

        Args:
            building: Building context dict with height, type, location, density
            analysis: Vulnerability analysis dict with score, drivers, climate_context
            interventions: List of proposed interventions with types and descriptions
            view_type: "street_level", "aerial", "section", or "before_after"

        Returns:
            Dict with generated image URL and metadata
        """
        if not self.client.api_key:
            return {
                "status": "error",
                "message": "OpenAI API key not configured. Set OPENAI_API_KEY environment variable.",
                "image_url": None
            }

        try:
            # Build detailed prompt for the visualization
            prompt = self._build_visualization_prompt(
                building, analysis, interventions, view_type
            )

            # Generate image
            response = self.client.images.generate(
                model=self.model,
                prompt=prompt,
                size=self.size,
                quality=self.quality,
                n=1
            )

            image_url = response.data[0].url

            return {
                "status": "success",
                "view_type": view_type,
                "image_url": image_url,
                "prompt_used": prompt[:200] + "...",
                "building": building.get('properties', {}).get('building_type', 'Unknown'),
                "interventions_count": len(interventions),
                "thermal_improvement": sum(
                    i.get('expected_thermal_impact_celsius', 0) for i in interventions
                )
            }

        except Exception as e:
            print(f"Error generating image: {e}")
            return {
                "status": "error",
                "message": str(e),
                "image_url": None
            }

    def generate_before_after_comparison(
        self,
        building: Dict[str, Any],
        analysis: Dict[str, Any],
        interventions: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Generate before/after side-by-side or blended visualization.

        Args:
            building: Building context
            analysis: Vulnerability analysis
            interventions: Proposed interventions

        Returns:
            Dict with before and after image URLs
        """
        try:
            before_prompt = self._build_before_prompt(building, analysis)
            after_prompt = self._build_after_prompt(building, analysis, interventions)

            # Generate before image
            before_response = self.client.images.generate(
                model=self.model,
                prompt=before_prompt,
                size=self.size,
                quality=self.quality,
                n=1
            )

            # Generate after image
            after_response = self.client.images.generate(
                model=self.model,
                prompt=after_prompt,
                size=self.size,
                quality=self.quality,
                n=1
            )

            thermal_impact = sum(
                i.get('expected_thermal_impact_celsius', 0) for i in interventions
            )

            return {
                "status": "success",
                "before_url": before_response.data[0].url,
                "after_url": after_response.data[0].url,
                "thermal_improvement_celsius": thermal_impact,
                "description": f"Building before and after {len(interventions)} proposed interventions"
            }

        except Exception as e:
            print(f"Error generating before/after comparison: {e}")
            return {
                "status": "error",
                "message": str(e),
                "before_url": None,
                "after_url": None
            }

    def generate_street_view(
        self,
        building: Dict[str, Any],
        analysis: Dict[str, Any],
        interventions: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Generate street-level pedestrian view with interventions."""
        return self.generate_intervention_visualization(
            building, analysis, interventions, "street_level"
        )

    def generate_aerial_view(
        self,
        building: Dict[str, Any],
        analysis: Dict[str, Any],
        interventions: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Generate aerial/drone perspective view."""
        return self.generate_intervention_visualization(
            building, analysis, interventions, "aerial"
        )

    def generate_section_view(
        self,
        building: Dict[str, Any],
        analysis: Dict[str, Any],
        interventions: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Generate sectional/architectural view showing vertical relationships."""
        return self.generate_intervention_visualization(
            building, analysis, interventions, "section"
        )

    def _build_visualization_prompt(
        self,
        building: Dict[str, Any],
        analysis: Dict[str, Any],
        interventions: List[Dict[str, Any]],
        view_type: str
    ) -> str:
        """
        Build detailed, optimized prompt for photorealistic image generation.
        """
        # Extract building context
        building_context = building.get('properties', {}) or {}
        height = building_context.get('height', building.get('height', 0))
        building_type = building_context.get('building_type', 'Mixed-use')
        location = building.get('location', 'Urban area')

        # Extract vulnerability context
        vulnerability = analysis.get('vulnerability_analysis', {})
        peak_utci = vulnerability.get('climate_context', {}).get('peak_utci_celsius', 0)
        drivers = vulnerability.get('drivers', [])

        # Format interventions for prompt
        interventions_text = self._format_interventions_for_prompt(interventions)

        # Build view-specific prompts
        view_instructions = {
            "street_level": "photorealistic street-level perspective showing pedestrians walking, cars, storefronts, and the surrounding urban context. Show the new green infrastructure, shade structures, and cooler surfaces clearly visible from ground level.",
            "aerial": "photorealistic aerial/drone perspective showing the building roof, surrounding area, and the spatial layout of all proposed interventions. Show tree canopy coverage, water features, and light-colored surfaces from above.",
            "section": "architectural sectional drawing style showing a vertical cross-section through the building and surrounding area. Illustrate how interventions like green roofs, vertical greening, ventilation corridors, and shade structures improve thermal conditions.",
            "before_after": "split-screen or blended comparison showing the building's current thermal conditions on one side and the improved state with interventions on the other side. Use warm colors (reds/oranges) for hot areas before interventions and cool colors (blues/greens) after."
        }

        view_instruction = view_instructions.get(view_type, view_instructions["street_level"])

        prompt = f"""Create a professional, photorealistic architectural visualization showing urban design interventions:

BUILDING CONTEXT:
- Building: {height}m tall {building_type} in {location}
- Current thermal stress: Peak apparent temperature {peak_utci}°C
- Current problems: {self._format_drivers(drivers)}

PROPOSED INTERVENTIONS:
{interventions_text}

EXPECTED THERMAL IMPACT:
- Temperature reduction: {sum(i.get('expected_thermal_impact_celsius', 0) for i in interventions):.1f}°C
- Improved thermal comfort and livability for occupants and pedestrians

VISUALIZATION STYLE:
- Photorealistic architectural rendering
- Professional quality suitable for stakeholder presentation
- Daytime lighting, summer peak heat conditions
- Include human figures for scale and activity
- Show context buildings and urban fabric
- Emphasize the cooling effects of new vegetation, water features, and lighter surfaces

VIEW: {view_instruction}

QUALITY REQUIREMENTS:
- High-resolution professional rendering
- Technically accurate architectural details
- Realistic materials, lighting, and shadows
- Clear visibility of all interventions
- Contemporary urban design aesthetic
- Climate-responsive design focus

Generate the visualization now:"""

        return prompt

    def _build_before_prompt(
        self,
        building: Dict[str, Any],
        analysis: Dict[str, Any]
    ) -> str:
        """Build prompt for 'before' state visualization."""
        building_context = building.get('properties', {}) or {}
        height = building_context.get('height', building.get('height', 0))
        building_type = building_context.get('building_type', 'Mixed-use')
        location = building.get('location', 'Urban area')

        vulnerability = analysis.get('vulnerability_analysis', {})
        peak_utci = vulnerability.get('climate_context', {}).get('peak_utci_celsius', 0)
        drivers = vulnerability.get('drivers', [])

        prompt = f"""Create a photorealistic street-level visualization of the CURRENT STATE of this building before any interventions:

BUILDING:
- {height}m tall {building_type} in {location}
- Peak thermal stress: {peak_utci}°C (very hot conditions)
- Challenges: {self._format_drivers(drivers)}

CURRENT CONDITIONS TO SHOW:
- Limited vegetation and tree canopy
- Hard paved surfaces (asphalt, concrete)
- Minimal shade or cooling features
- Intense solar radiation on building and streets
- Visible heat haze/shimmer effect showing extreme heat
- Urban canyon effect with tall buildings blocking wind

VISUALIZATION:
- Street-level pedestrian perspective
- Summer peak heat time (bright, intense sunlight)
- Warm color palette (reds, oranges, yellows) emphasizing heat
- Include pedestrians experiencing discomfort/heat stress
- Show thermometer or heat intensity visualization
- Professional architectural quality

Generate this "before" state visualization:"""

        return prompt

    def _build_after_prompt(
        self,
        building: Dict[str, Any],
        analysis: Dict[str, Any],
        interventions: List[Dict[str, Any]]
    ) -> str:
        """Build prompt for 'after' state visualization."""
        building_context = building.get('properties', {}) or {}
        height = building_context.get('height', building.get('height', 0))
        building_type = building_context.get('building_type', 'Mixed-use')
        location = building.get('location', 'Urban area')

        vulnerability = analysis.get('vulnerability_analysis', {})
        peak_utci = vulnerability.get('climate_context', {}).get('peak_utci_celsius', 0)
        interventions_text = self._format_interventions_for_prompt(interventions)

        thermal_reduction = sum(
            i.get('expected_thermal_impact_celsius', 0) for i in interventions
        )
        new_utci = peak_utci - thermal_reduction

        prompt = f"""Create a photorealistic street-level visualization of this building AFTER implementing the proposed interventions:

BUILDING:
- {height}m tall {building_type} in {location}
- Original thermal stress: {peak_utci}°C
- Improved thermal stress: {new_utci:.0f}°C (reduction of {thermal_reduction:.1f}°C)

IMPLEMENTED INTERVENTIONS:
{interventions_text}

IMPROVED CONDITIONS TO SHOW:
- Abundant new vegetation and mature tree canopy providing shade
- Cool, light-colored paved surfaces
- Water features creating evaporative cooling and visual appeal
- Visible shade structures and cooling features
- Cooler environment with reduced heat haze
- Comfortable pedestrian environment
- Clear visual improvements in public space quality

VISUALIZATION:
- Same street-level perspective as before state
- Summer conditions but with visible thermal comfort improvements
- Cooler color palette (greens, blues) showing reduced heat
- Pedestrians comfortable, relaxed, enjoying the improved environment
- Show thermometer or thermal visualization showing lower temperature
- Professional architectural quality
- Clear before/after comparison capability

Generate this "after" state visualization:"""

        return prompt

    def _format_interventions_for_prompt(
        self,
        interventions: List[Dict[str, Any]]
    ) -> str:
        """Format intervention list for inclusion in prompt."""
        if not interventions:
            return "No interventions specified"

        text = ""
        for i, intervention in enumerate(interventions[:6], 1):  # Max 6 interventions
            int_type = intervention.get('type', 'unknown').replace('_', ' ')
            impact = intervention.get('expected_thermal_impact_celsius', 0)
            description = intervention.get('description', 'Urban intervention')
            area = intervention.get('estimated_area_or_scale', 'specified area')

            text += f"{i}. {int_type.title()} ({impact}°C reduction)\n"
            text += f"   Scale: {area}\n"
            text += f"   Purpose: {description}\n"

        return text

    def _format_drivers(self, drivers: List[Dict]) -> str:
        """Format vulnerability drivers for prompt."""
        if not drivers:
            return "General urban heat stress"

        driver_names = []
        for driver in drivers[:3]:  # Max 3 drivers
            if isinstance(driver, dict):
                name = driver.get('driver', 'Unknown').replace('_', ' ')
            else:
                name = str(driver).replace('_', ' ')
            driver_names.append(name)

        return ", ".join(driver_names)
