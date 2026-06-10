from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Optional, Any
import json

from services.rag_retrieval import RAGRetrieval
from services.llm_service import LLMService
from services.chat_service import ChatService
from services.intervention_engine import match_and_rank_strategies
from services.image_generation import ImageGenerator
from services.thermal_to_design import map_thermal_to_design, DesignSpecificationResponse

router = APIRouter(prefix="/api/interventions", tags=["interventions"])

# Initialize RAG, LLM, Chat and Image Generation services (singleton pattern)
_rag_service = None
_llm_service = None
_chat_service = None
_image_generator = None

def get_rag_service():
    global _rag_service
    if _rag_service is None:
        _rag_service = RAGRetrieval()
    return _rag_service

def get_llm_service():
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service

def get_chat_service():
    global _chat_service
    if _chat_service is None:
        _chat_service = ChatService()
    return _chat_service

def get_image_generator():
    global _image_generator
    if _image_generator is None:
        _image_generator = ImageGenerator()
    return _image_generator

# Request/Response models
class BuildingContextRequest(BaseModel):
    height: float
    building_type: str = "Mixed"
    location: str = "Unknown"
    properties: Optional[Dict[str, Any]] = None
    class Config:
        extra = "allow"

class VulnerabilityAnalysisRequest(BaseModel):
    score: float
    drivers: List[Dict[str, Any]]
    climate_context: Dict[str, Any]
    vulnerability_analysis: Optional[Dict[str, Any]] = None
    class Config:
        extra = "allow"

class SuggestEnhancedRequest(BaseModel):
    building: Dict[str, Any]
    analysis: Dict[str, Any]
    climate_type: Optional[str] = None

class InterventionSuggestion(BaseModel):
    type: str
    name: str
    expected_thermal_impact_celsius: float
    implementation_complexity: str
    description: str
    primary_drivers_addressed: List[str]
    timeline_months: int = 6
    estimated_cost_usd: str = "To be determined"
    visualization_type: str = "polygon"
    implementation_notes: str = ""
    estimated_area_or_scale: str = ""
    source: str = "llm"  # "llm", "rules", "hybrid"
    similarity_score: Optional[float] = None

class SuggestEnhancedResponse(BaseModel):
    suggestions: List[InterventionSuggestion]
    knowledge_cases: int
    hybrid_approach: str
    reasoning: str

class ChatRequest(BaseModel):
    message: str
    building: Dict[str, Any]
    analysis: Dict[str, Any]
    climate_type: Optional[str] = None
    chat_history: List[Dict[str, str]] = []

class ChatResponse(BaseModel):
    response: str
    suggestions: List[Dict[str, Any]]
    knowledge_sources: Dict[str, int]
    retrieved_cases: List[Dict[str, Any]] = []
    retrieved_papers: List[Dict[str, Any]] = []

@router.post("/chat", response_model=ChatResponse)
async def chat_about_interventions(request: ChatRequest) -> ChatResponse:
    """
    Have a conversational discussion about building interventions.
    Uses RAG to find relevant cases and research, then Ollama to generate contextual responses.

    Args:
        request: Chat message + building context + analysis

    Returns:
        Conversational response with suggestions and knowledge sources
    """
    try:
        chat_service = get_chat_service()
        result = chat_service.chat(
            message=request.message,
            building=request.building,
            analysis=request.analysis,
            climate_type=request.climate_type,
            chat_history=request.chat_history
        )

        return ChatResponse(**result)

    except Exception as e:
        import traceback
        print(f"Error in chat_about_interventions: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/suggest-enhanced", response_model=SuggestEnhancedResponse)
async def suggest_enhanced_interventions(request: SuggestEnhancedRequest) -> SuggestEnhancedResponse:
    """
    Generate enhanced intervention suggestions using hybrid approach:
    1. Baseline rules-based strategies
    2. RAG retrieval of similar cases
    3. LLM generation of contextual suggestions
    4. Hybrid ranking combining all approaches

    Args:
        request: Building context and vulnerability analysis

    Returns:
        Enhanced intervention suggestions with metadata
    """
    try:
        print(f"DEBUG: request type: {type(request)}")
        print(f"DEBUG: request: {request}")

        building = request.building
        analysis = request.analysis
        climate_type = request.climate_type

        print(f"DEBUG: building type: {type(building)}, value: {building}")
        print(f"DEBUG: analysis type: {type(analysis)}, keys: {list(analysis.keys()) if hasattr(analysis, 'keys') else 'N/A'}")

        # Extract context for RAG
        building_context = building.get('properties', {}) or {}
        height = building_context.get('height', building.get('height', 0))
        building_type = building_context.get('building_type', 'Unknown')
        location = building.get('location', 'Unknown location')

        print(f"DEBUG: Extracting vulnerability from analysis...")
        vulnerability = analysis.get('vulnerability_analysis', {}) if hasattr(analysis, 'get') else {}
        print(f"DEBUG: vulnerability: {vulnerability}")
        vuln_score = vulnerability.get('score', 0) if hasattr(vulnerability, 'get') else 0
        drivers_raw = vulnerability.get('drivers', []) if hasattr(vulnerability, 'get') else []
        print(f"DEBUG: drivers_raw type: {type(drivers_raw)}, value: {drivers_raw}")

        # Defensively extract driver names from any format
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
                    print(f"DEBUG: Error processing driver {d}: {e}")

        climate_context = vulnerability.get('climate_context', {}) if hasattr(vulnerability, 'get') else {}
        peak_utci = climate_context.get('peak_utci_celsius', 0)

        # Step 1: Get baseline rules-based strategies
        baseline_strategies = match_and_rank_strategies(vulnerability)

        # Step 2: Retrieve similar cases via RAG
        rag_service = get_rag_service()
        similar_cases = rag_service.retrieve_similar_cases(
            building_context={
                'avg_height_m': height,
                'building_density': building_context.get('building_density', 'unknown'),
                'building_type': building_type,
                'sky_view_factor': building_context.get('sky_view_factor', 0),
                'vulnerability_score': vuln_score,
                'peak_utci_celsius': peak_utci
            },
            vulnerability_drivers=driver_names,
            climate_type=climate_type,
            top_k=3
        )

        # Get insights from similar cases
        case_insights = rag_service.extract_case_insights(similar_cases)

        # Rank interventions by driver relevance
        ranked_interventions = rag_service.rank_interventions_by_driver(
            driver_names,
            similar_cases
        )

        # Step 3: Generate LLM suggestions
        llm_service = get_llm_service()
        llm_suggestions = llm_service.generate_suggestions(
            building=building,
            analysis=analysis,
            similar_cases=similar_cases,
            baseline_strategies=baseline_strategies
        )

        # Step 4: Combine and rank suggestions (hybrid approach)
        all_suggestions = _combine_suggestions(
            llm_suggestions=llm_suggestions,
            baseline_strategies=baseline_strategies,
            similar_cases=similar_cases,
            drivers=driver_names
        )

        # Sort by thermal impact (descending)
        all_suggestions.sort(
            key=lambda x: x.get('expected_thermal_impact_celsius', 0),
            reverse=True
        )

        # Convert to response models
        suggestion_responses = [
            InterventionSuggestion(**s) for s in all_suggestions[:8]  # Return top 8
        ]

        return SuggestEnhancedResponse(
            suggestions=suggestion_responses,
            knowledge_cases=len(similar_cases),
            hybrid_approach="rules + RAG + LLM",
            reasoning=f"Generated {len(llm_suggestions)} LLM suggestions informed by {len(similar_cases)} similar cases and {len(baseline_strategies)} baseline strategies"
        )

    except Exception as e:
        import traceback
        import sys
        error_msg = traceback.format_exc()
        print(f"Error in suggest_enhanced_interventions: {e}", file=sys.stderr)
        print(error_msg, file=sys.stderr)
        sys.stderr.flush()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/generate-from-analysis", response_model=dict)
async def generate_design_from_analysis(request: Dict[str, Any]) -> Dict[str, Any]:
    """
    PHASE 1: Thermal-to-Design Rules Engine

    Map thermal vulnerability analysis results directly to architectural design specifications.
    This is the foundation: converts UTCI/MRT/drivers into parametric design parameters and
    visualization geometries for urban-scale and building-scale interventions.

    Args:
        request: Dict with:
            - vulnerability_analysis: Full vulnerability analysis output from Infrared
                - vulnerability_score: float (0-10)
                - peak_utci_celsius: float
                - drivers: List[Dict] with 'driver' and 'severity'
                - climate_context: Dict
            - zone_geojson: Optional GeoJSON of vulnerable zone (for geometry generation)

    Returns:
        Design specifications with:
        - Ranked design interventions with parameters
        - GeoJSON visualization layers (ready for MapView)
        - Expected thermal impact (°C reduction)
        - Cost estimates and feasibility scores
        - Recommended priority combination
    """
    try:
        vulnerability_analysis = request.get("vulnerability_analysis", {})
        zone_geojson = request.get("zone_geojson")

        if not vulnerability_analysis:
            raise HTTPException(status_code=400, detail="vulnerability_analysis required")

        result = map_thermal_to_design(
            vulnerability_analysis=vulnerability_analysis,
            zone_geojson=zone_geojson
        )

        return {
            "status": "success",
            "zone_id": result.zone_id,
            "vulnerability_drivers": result.vulnerability_drivers,
            "combined_thermal_impact_celsius": round(result.combined_thermal_impact, 2),
            "design_specs": [
                {
                    "intervention_id": spec.intervention_id,
                    "type": spec.type,
                    "name": spec.name,
                    "priority": spec.priority,
                    "parameters": spec.parameters,
                    "expected_impact_celsius": spec.expected_impact_celsius,
                    "implementation_months": spec.implementation_months,
                    "cost_estimate_usd": round(spec.cost_estimate_usd, 2),
                    "feasibility_score": round(spec.feasibility_score, 2),
                    "implementation_priority": spec.implementation_priority,
                    "rationale": spec.rationale,
                    "visualization_geojson": spec.visualization_geojson,
                }
                for spec in result.design_specs
            ],
            "recommended_combination": result.recommended_combination,
            "next_step": "Visualize on map using intervention_geojson layers. Then iterate with /evaluate-custom or generate photorealistic views with /generate-image"
        }

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"Error in generate_design_from_analysis: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/evaluate-custom")
async def evaluate_custom_interventions(request: Dict[str, Any]) -> Dict[str, Any]:
    """
    Evaluate a custom combination of interventions.
    This is a quick evaluation endpoint (doesn't re-run full Infrared analysis).

    Args:
        request: Dict with:
            - zone_geojson: GeoJSON of zone
            - interventions: List of intervention dicts
            - building: Building data
            - baseline_analysis: Original analysis for comparison

    Returns:
        Estimated impact and modified analysis
    """
    try:
        # For now, return estimated impact based on intervention types
        interventions = request.get('interventions', [])
        baseline_analysis = request.get('baseline_analysis', {})

        estimated_thermal_impact = 0.0
        estimated_utci_reduction = 0.0

        # Calculate estimated impacts based on intervention types
        intervention_impacts = {
            'urban_forest': {'thermal': 2.5, 'utci': 3.2},
            'trees': {'thermal': 2.5, 'utci': 3.2},
            'cool_pavements': {'thermal': 1.8, 'utci': 2.4},
            'cool_roofs': {'thermal': 2.0, 'utci': 2.6},
            'water_features': {'thermal': 1.5, 'utci': 1.9},
            'green_roofs': {'thermal': 1.6, 'utci': 2.1},
            'shade_structures': {'thermal': 1.2, 'utci': 1.6},
            'vertical_greening': {'thermal': 1.4, 'utci': 1.8},
            'permeable_pavements': {'thermal': 1.0, 'utci': 1.3},
            'ventilation_corridors': {'thermal': 0.8, 'utci': 1.1},
        }

        # Sum impacts from all interventions
        for intervention in interventions:
            int_type = intervention.get('type', 'unknown')
            if int_type in intervention_impacts:
                estimated_thermal_impact += intervention_impacts[int_type]['thermal']
                estimated_utci_reduction += intervention_impacts[int_type]['utci']

        # Estimate new vulnerability score
        baseline_score = baseline_analysis.get('vulnerability_analysis', {}).get('score', 7.0)
        estimated_reduction = min(baseline_score * 0.3, estimated_thermal_impact / 5.0)
        new_score = max(1.0, baseline_score - estimated_reduction)

        return {
            "status": "success",
            "estimated_thermal_impact_celsius": round(estimated_thermal_impact, 2),
            "estimated_utci_reduction_celsius": round(estimated_utci_reduction, 2),
            "baseline_vulnerability_score": round(baseline_score, 1),
            "estimated_new_vulnerability_score": round(new_score, 1),
            "estimated_score_reduction": round(estimated_reduction, 1),
            "interventions_evaluated": len(interventions),
            "note": "This is an estimate based on intervention types. Actual impact requires full Infrared analysis."
        }

    except Exception as e:
        print(f"Error in evaluate_custom_interventions: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/generate-image")
async def generate_intervention_image(request: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate photorealistic visualization of building with proposed interventions.

    Args:
        request: Dict with:
            - building: Building context
            - analysis: Vulnerability analysis
            - interventions: List of proposed interventions
            - view_type: "street_level" (default), "aerial", "section", or "before_after"

    Returns:
        Dict with generated image URL(s) and metadata
    """
    try:
        building = request.get('building', {})
        analysis = request.get('analysis', {})
        interventions = request.get('interventions', [])
        view_type = request.get('view_type', 'street_level')

        image_generator = get_image_generator()

        if view_type == "before_after":
            result = image_generator.generate_before_after_comparison(
                building, analysis, interventions
            )
        else:
            result = image_generator.generate_intervention_visualization(
                building, analysis, interventions, view_type
            )

        return result

    except Exception as e:
        print(f"Error in generate_intervention_image: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cases/{case_id}")
async def get_case_details(case_id: str) -> Dict[str, Any]:
    """Get details of a specific case study from the knowledge base."""
    try:
        rag_service = get_rag_service()
        interventions = rag_service.get_case_interventions(case_id)

        if not interventions:
            raise HTTPException(status_code=404, detail=f"Case {case_id} not found")

        return {
            "case_id": case_id,
            "interventions": interventions
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Helper function
def _combine_suggestions(
    llm_suggestions: List[Dict],
    baseline_strategies: List[Dict],
    similar_cases: List[Dict],
    drivers: List[str]
) -> List[Dict]:
    """
    Combine LLM suggestions with baseline strategies using hybrid ranking.

    Priority:
    1. LLM suggestions (most contextual)
    2. Baseline strategies (rules-based fallback)
    3. Case-derived suggestions (historical data)
    """
    combined = []

    # Add LLM suggestions (highest priority)
    for suggestion in llm_suggestions:
        suggestion['source'] = 'llm'
        suggestion['priority'] = 1
        combined.append(suggestion)

    # Add baseline strategies (medium priority)
    for strategy in baseline_strategies:
        # Convert to intervention format
        converted = {
            'type': strategy.get('strategy_id', 'unknown'),
            'name': strategy.get('name', 'Unknown'),
            'expected_thermal_impact_celsius': strategy.get('thermal_impact', 0),
            'implementation_complexity': 'medium',
            'description': f"Baseline strategy: {strategy.get('name', '')}",
            'primary_drivers_addressed': drivers[:2],  # Top 2 drivers
            'timeline_months': strategy.get('implementation_months', 6),
            'estimated_cost_usd': str(strategy.get('cost_estimate', {}).get('min', 'Unknown')),
            'source': 'rules',
            'priority': 2
        }
        combined.append(converted)

    # Add case-derived suggestions (lower priority)
    case_interventions = {}
    for case in similar_cases:
        for intervention in case.get('interventions_applied', []):
            int_type = intervention.get('type', 'unknown')
            if int_type not in case_interventions:
                case_interventions[int_type] = {
                    'type': int_type,
                    'name': int_type.replace('_', ' ').title(),
                    'expected_thermal_impact_celsius': case.get('results', {}).get('temperature_reduction_celsius', 0),
                    'implementation_complexity': 'medium',
                    'description': f"Proven intervention from similar buildings",
                    'primary_drivers_addressed': drivers[:2],
                    'timeline_months': intervention.get('implementation_months', 6),
                    'estimated_cost_usd': str(intervention.get('cost_estimate_usd', 'Unknown')),
                    'source': 'cases',
                    'priority': 3
                }

    combined.extend(case_interventions.values())

    # Remove duplicates by type, keeping highest priority
    seen_types = {}
    for suggestion in combined:
        int_type = suggestion.get('type', 'unknown')
        if int_type not in seen_types or suggestion.get('priority', 99) < seen_types[int_type].get('priority', 99):
            seen_types[int_type] = suggestion

    return list(seen_types.values())
