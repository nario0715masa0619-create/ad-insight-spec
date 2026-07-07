"""
ConverterService - Convert analysis results to ad_insight_spec v0.2

Responsibilities:
- Aggregate all Service outputs (ingestion, metadata, content analysis, llm)
- Populate ad_insight_spec v0.2 sections
- Handle mode-dependent optional fields
- Validate against Pydantic schema
- Return JSON-serializable dict

Input: Results from all upstream services
Output: ad_insight_spec dict (validated against Pydantic v0.2)
"""

from typing import Dict, Any, Optional
from datetime import datetime
import logging
import json

from app.services.base_service import BaseService, ValidationError, ProcessingError
from app.schemas.ad_insight import AdInsightSpec, InputModeEnum


logger = logging.getLogger(__name__)


class ConverterService(BaseService):
    """
    Service for converting analysis results to ad_insight_spec v0.2.
    
    Aggregates outputs from:
    - IngestionService
    - MetadataService
    - LPService
    - VideoService
    - OCRService
    - LLMService
    - Optional KPI
    
    Produces:
    - ad_insight_spec dict (v0.2 schema)
    - Pydantic validation passed
    """
    
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def execute(
        self,
        mode: str,
        ingestion_result: Dict[str, Any],
        metadata_result: Dict[str, Any],
        lp_result: Dict[str, Any],
        video_result: Dict[str, Any],
        ocr_result: Dict[str, Any],
        llm_result: Dict[str, Any],
        kpi_result: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Convert all analysis results to ad_insight_spec v0.2.
        
        Args:
            mode (str): file_only / file_plus_lp / file_plus_lp_plus_manual_kpi
            ingestion_result (dict): From IngestionService
            metadata_result (dict): From MetadataService
            lp_result (dict): From LPService
            video_result (dict): From VideoService
            ocr_result (dict): From OCRService
            llm_result (dict): From LLMService
            kpi_result (dict): Optional KPI data
        
        Returns:
            dict: ad_insight_spec v0.2 (validated by Pydantic)
        
        Raises:
            ValidationError: If conversion fails
            ProcessingError: If Pydantic validation fails
        """
        try:
            self.logger.info(f"Converting to ad_insight_spec (mode: {mode})")
            
            # Build spec sections
            input_metadata = self._populate_input_metadata(mode, ingestion_result)
            asset_meta = self._populate_asset_meta(metadata_result)
            creative_core = self._populate_creative_core(ingestion_result, metadata_result, llm_result)
            landing_page = self._populate_landing_page(lp_result, llm_result) if lp_result else None
            performance = self._populate_performance(kpi_result) if kpi_result else None
            diagnostics = self._populate_diagnostics(llm_result, performance)
            views = self._populate_views(performance, llm_result)
            metadata_section = self._populate_metadata(mode, llm_result, ocr_result)
            
            # Build complete spec dict
            spec_dict = {
                "input_metadata": input_metadata,
                "asset_meta": asset_meta,
                "creative_core": creative_core,
                "landing_page": landing_page,
                "performance": performance,
                "diagnostics": diagnostics,
                "views": views,
                "_metadata": metadata_section,
            }
            
            # Validate against Pydantic v0.2
            self.logger.info("Validating against Pydantic v0.2 schema")
            try:
                spec = AdInsightSpec(**spec_dict)
                self.logger.info("Pydantic validation passed")
            except Exception as e:
                raise ProcessingError(f"Pydantic validation failed: {str(e)}")
            
            # Convert back to dict for JSON serialization
            result = spec.dict(by_alias=True, exclude_none=False)
            
            self.logger.info("Conversion complete: ad_insight_spec v0.2")
            return result
        
        except (ValidationError, ProcessingError):
            raise
        except Exception as e:
            raise ProcessingError(f"Conversion failed: {str(e)}")
    
    def validate_input(self, *args, **kwargs) -> bool:
        """Input validation (basic)"""
        return True
    
    def _populate_input_metadata(self, mode: str, ingestion_result: Dict[str, Any]) -> Dict[str, Any]:
        """Populate input_metadata section"""
        return {
            "mode": mode,
            "source_type": "local_file",
            "input_timestamp": datetime.now().isoformat() + "Z",
            "file_paths": {
                "creative_video": ingestion_result.get("file_path") if ingestion_result.get("format") == "video_static" else None,
                "creative_images": [ingestion_result.get("file_path")] if ingestion_result.get("format") == "image_static" else None,
                "landing_page_html": None,
            },
            "api_source": None,
        }
    
    def _populate_asset_meta(self, metadata_result: Dict[str, Any]) -> Dict[str, Any]:
        """Populate asset_meta section"""
        return {
            "asset_id": metadata_result.get("asset_id", "unknown"),
            "asset_name": metadata_result.get("asset_name"),
            "platform": "unknown",
            "ad_account_id": None,
            "campaign_name": None,
            "adset_name": None,
            "ad_name": None,
            "analysis_period": {
                "start": None,
                "end": None,
            },
            "external_ids": None,
        }
    
    def _populate_creative_core(
        self,
        ingestion_result: Dict[str, Any],
        metadata_result: Dict[str, Any],
        llm_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Populate creative_core section"""
        creative_core = llm_result.get("creative_core", {})
        
        return {
            "format": ingestion_result.get("format", "unknown"),
            "duration_seconds": metadata_result.get("duration_seconds"),
            "primary_text": None,  # Would come from OCR in full implementation
            "headline": None,
            "body_text": None,
            "call_to_action": None,
            "visuals": creative_core.get("visuals", {}),
            "tone": creative_core.get("tone", {}),
            "ai_labels": creative_core.get("ai_labels", []),
            "platform_specific": None,
        }
    
    def _populate_landing_page(self, lp_result: Dict[str, Any], llm_result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Populate landing_page section (optional)"""
        if not lp_result:
            return None
        
        consistency = llm_result.get("message_consistency", {})
        
        return {
            "url": lp_result.get("url"),
            "fv_copy": lp_result.get("fv_copy"),
            "fv_headline": lp_result.get("fv_headline"),
            "offer": lp_result.get("offer"),
            "form_difficulty": None,
            "form_field_count": lp_result.get("form_fields_count"),
            "cta_button_text": lp_result.get("primary_cta"),
            "message_consistency": {
                "match_score": consistency.get("match_score"),
                "consistency_basis": consistency.get("consistency_basis"),
                "key_alignment_points": consistency.get("key_alignment_points"),
                "mismatch_areas": consistency.get("mismatch_areas"),
                "analyzed_at": datetime.now().isoformat() + "Z" if consistency.get("match_score") is not None else None,
            },
            "lp_page_structure": {
                "has_hero_section": lp_result.get("has_hero_section"),
                "has_social_proof": lp_result.get("has_social_proof"),
                "has_faq_section": lp_result.get("has_faq_section"),
                "estimated_scroll_depth_for_form": lp_result.get("estimated_scroll_depth_for_form"),
            },
        }
    
    def _populate_performance(self, kpi_result: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Populate performance section (optional, KPI-dependent)"""
        if not kpi_result:
            return None
        
        return {
            "impressions": kpi_result.get("impressions"),
            "clicks": kpi_result.get("clicks"),
            "ctr": kpi_result.get("ctr"),
            "spend": kpi_result.get("spend"),
            "conversions": kpi_result.get("conversions"),
            "conversion_value": kpi_result.get("conversion_value"),
            "cpa": kpi_result.get("cpa"),
            "cvr": kpi_result.get("cvr"),
            "roas": kpi_result.get("roas"),
            "reach": kpi_result.get("reach"),
            "frequency": kpi_result.get("frequency"),
        }
    
    def _populate_diagnostics(
        self,
        llm_result: Dict[str, Any],
        performance: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Populate diagnostics section"""
        llm_analysis = llm_result.get("creative_analysis", {})
        consistency = llm_result.get("message_consistency", {})
        creative_core = llm_result.get("creative_core", {})
        
        qualitative = {
            "creative_fatigue_risk": "low",  # Mock: always low
            "creative_fatigue_basis": "Mock analysis - no fatigue risk detected",
            "creative_fatigue_indicators": [],
            "message_clarity_score": 0.8,
            "message_clarity_basis": "Mock analysis - message is clear",
            "lp_message_match_risk": "low" if consistency.get("match_score", 0) > 0.7 else "medium",
            "lp_message_match_basis": f"Mock analysis - match score: {consistency.get('match_score', 'unknown')}",
            "form_usability_concern": "low",
            "form_usability_basis": "Mock analysis - form is usable",
            "audience_relevance_concern": "low",
            "audience_relevance_basis": f"Inferred audience: {llm_analysis.get('target_audience_inferred', 'unknown')}",
            "recommended_creative_improvements": llm_result.get("recommendations", []),
        }
        
        quantitative = None
        if performance:
            quantitative = {
                "performance_status": "good",  # Mock: always good
                "performance_status_basis": "Mock analysis - performance is good",
                "ctr_assessment": "good",
                "ctr_benchmark_comparison": "CTR is within expected range",
                "cvr_assessment": "good",
                "cvr_benchmark_comparison": "CVR is within expected range",
                "roas_assessment": "good",
                "roas_benchmark_comparison": "ROAS is within expected range",
                "efficiency_score": 0.75,
                "recommended_optimizations": [
                    "Continue current strategy",
                    "Test minor variations",
                    "Monitor performance trends",
                ],
            }
        
        return {
            "qualitative": qualitative,
            "quantitative": quantitative,
            "llm_model": creative_core.get("llm_model"),
            "llm_success": creative_core.get("llm_success"),
            "llm_retry_count": creative_core.get("llm_retry_count"),
            "llm_error": creative_core.get("llm_error"),
            "improvements": llm_result.get("improvements"),
            "improvements_error": llm_result.get("improvements_error"),
            "decision_support": llm_result.get("decision_support"),
            "decision_support_error": llm_result.get("decision_support_error"),
            "video_cuts": llm_result.get("video_cuts"),
            "video_cuts_error": llm_result.get("video_cuts_error"),
        }
    
    def _populate_views(
        self,
        performance: Optional[Dict[str, Any]],
        llm_result: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Populate views section (UI display data)"""
        return {
            "dashboard_summary": {
                "status_label": "Good",
                "key_metric_highlight": "Analysis complete",
                "status_color": "#FFAA00",
            },
            "performance_ranking": "Average",
            "trend_indicator": None,
            "creative_fatigue_visual": "● Low",
            "lp_match_visual": "✓ Aligned",
            "recommended_actions_display": [
                {
                    "priority": "medium",
                    "action": rec,
                    "expected_impact": "Potential improvement",
                }
                for rec in llm_result.get("recommendations", [])[:3]
            ],
        }
    
    def _populate_metadata(
        self,
        mode: str,
        llm_result: Dict[str, Any],
        ocr_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Populate _metadata section

        以前は ai_model_version / validation_notes が常に固定の "mock" 文言
        だったため、実際に GPT-4o 等で分析が成功していても "mock" と表示され
        誤解を招いていた。実際の llm_result / ocr_result を反映する。
        """
        creative_core_llm = (llm_result or {}).get("creative_core", {}) or {}
        llm_model = creative_core_llm.get("llm_model")
        llm_success = creative_core_llm.get("llm_success")
        llm_error = creative_core_llm.get("llm_error")

        ocr_success = bool((ocr_result or {}).get("success"))
        ocr_engine = "tesseract" if ocr_success else "tesseract (no text detected / unavailable)"

        validation_notes = []
        if llm_model:
            validation_notes.append(f"LLM analysis: {llm_model} ({'success' if llm_success else 'failed'})")
        else:
            validation_notes.append("LLM analysis: not executed")
        if llm_error:
            validation_notes.append(f"LLM error: {llm_error}")
        validation_notes.append(f"OCR: {ocr_engine}")
        if (llm_result or {}).get("decision_support_error"):
            validation_notes.append("decision_support generation failed (fail-soft, see diagnostics.decision_support_error)")
        if (llm_result or {}).get("improvements_error"):
            validation_notes.append("improvements generation failed (fail-soft, see diagnostics.improvements_error)")

        return {
            "generated_at": datetime.now().isoformat() + "Z",
            "data_source": "local_file",
            "ai_model_version": llm_model or "unavailable",
            "json_schema_version": "v0.2",
            "input_mode": mode,
            "analysis_tools_used": {
                "ocr_engine": ocr_engine,
                "video_frame_extractor": "ffmpeg",
                "web_scraper": "beautifulsoup",
            },
            # 実測値は AnalysisOrchestrator.run() 完了後に上書きされる
            "processing_time_ms": 0,
            "validation_status": "passed" if llm_success else "degraded",
            "validation_notes": validation_notes,
        }
