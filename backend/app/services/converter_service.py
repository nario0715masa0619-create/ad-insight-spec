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

from typing import Dict, Any, List, Optional, Tuple
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
        video_cuts: Optional[List[Dict[str, Any]]] = None,
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
            video_cuts (list): Optional. AnalysisOrchestrator.video_cuts と同一形式
                （[{cut_id, start_seconds, end_seconds, frame_path, ocr_text}, ...]）。
                asset_data.asset_structure.cuts/ocr_segments の一次情報源として使う
                （動画以外、またはカット検出なしの場合は None/空リストで可）。

        Returns:
            dict: ad_insight_spec v0.2（validated by Pydantic）に加えて、
                asset_data / evaluation_data（AssetJsonV0 / EvaluationJsonV0 を
                JSON-safeなdictにしたもの。構築に失敗した場合は両方Noneのまま
                fail-softで、spec_data側の返却は妨げない）を含む。

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

            # asset_data / evaluation_data (v0) の生成。spec_data の正本性・
            # 保存経路には一切影響させない fail-soft 処理（失敗時は両方None、
            # spec_data 側の返却は継続する）。
            asset_data: Optional[Dict[str, Any]] = None
            evaluation_data: Optional[Dict[str, Any]] = None
            try:
                asset_data, evaluation_data = self._build_asset_evaluation_v0(
                    ingestion_result=ingestion_result,
                    metadata_result=metadata_result,
                    video_cuts=video_cuts or [],
                    spec=spec,
                )
            except Exception as e:
                self.logger.warning(
                    f"AssetJson/EvaluationJson generation failed (non-fatal, spec_data unaffected): {str(e)}"
                )
            result["asset_data"] = asset_data
            result["evaluation_data"] = evaluation_data

            self.logger.info("Conversion complete: ad_insight_spec v0.2")
            return result
        
        except (ValidationError, ProcessingError):
            raise
        except Exception as e:
            raise ProcessingError(f"Conversion failed: {str(e)}")
    
    def validate_input(self, *args, **kwargs) -> bool:
        """Input validation (basic)"""
        return True

    def _build_asset_evaluation_v0(
        self,
        ingestion_result: Dict[str, Any],
        metadata_result: Dict[str, Any],
        video_cuts: List[Dict[str, Any]],
        spec: AdInsightSpec,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        asset_data (AssetJsonV0) / evaluation_data (EvaluationJsonV0) を構築する。

        spec_data と重複する項目（asset_meta のlegacy互換フィールド、
        diagnostics/performance/landing_page_analysis）は、二重に組み立てると
        フィールド追加時にドリフトするため、既にPydantic検証済みの `spec` から
        再利用する。ここで新規に組み立てるのは、asset/evaluation分割で新設した
        v0専用フィールド（source_type/source_ref/created_at、media_info、
        asset_structure.cuts/ocr_segments、evaluation_meta）のみ。

        現在のパイプラインからは honest に埋められない項目（asset_annotations、
        transcript_segments）は、捏造しない方針によりスキーマのデフォルト
        （空リスト/None）のままにする。将来 ASR セグメント単位のタイムスタンプや
        ブランド/CTA検出が実装されたら、ここを拡張する。

        Returns:
            (asset_data dict, evaluation_data dict): いずれも
            `json.loads(model.json())` を経由したJSON-safeなdict
            （datetime直列化の既知バグを避けるため、`.dict()`は使わない）。
        """
        from app.schemas.asset_v0 import (
            AssetJsonV0,
            AssetMetaV0,
            MediaInfoV0,
            AssetStructureV0,
            AssetAnnotationsV0,
            CutSpan,
            OcrSegment,
        )
        from app.schemas.evaluation_v0 import EvaluationJsonV0, EvaluationMetaV0

        asset_meta_v0 = AssetMetaV0(
            asset_id=spec.asset_meta.asset_id,
            asset_name=spec.asset_meta.asset_name,
            platform=spec.asset_meta.platform,
            ad_account_id=spec.asset_meta.ad_account_id,
            campaign_name=spec.asset_meta.campaign_name,
            adset_name=spec.asset_meta.adset_name,
            ad_name=spec.asset_meta.ad_name,
            analysis_period=spec.asset_meta.analysis_period,
            external_ids=spec.asset_meta.external_ids,
            source_type=spec.input_metadata.source_type,
            source_ref=ingestion_result.get("file_path"),
            created_at=datetime.now(),
            analysis_version="v0",
        )

        width, height = self._parse_dimensions(metadata_result)
        media_info_v0 = MediaInfoV0(
            media_type=spec.creative_core.format,
            duration_seconds=spec.creative_core.duration_seconds,
            width=width,
            height=height,
            fps=metadata_result.get("fps"),
            aspect_ratio=None,  # 現行パイプラインでは未算出（捏造しない）
            language=metadata_result.get("language"),
        )

        cuts = [
            CutSpan(cut_id=c["cut_id"], start_sec=c["start_seconds"], end_sec=c["end_seconds"])
            for c in video_cuts
            if c.get("cut_id") is not None
            and c.get("start_seconds") is not None
            and c.get("end_seconds") is not None
        ]
        # cutsとは別に、1件ずつtry/exceptで構築する。cuts側はNoneチェックのみで
        # 弾けるが、ocr_segmentsは型不正（例: start_seconds/end_secondsが
        # 数値以外）等、Noneチェックだけでは防ぎきれない壊れ方もあり得る。
        # ここで1件だけ弾いても、他の正常なカット・asset_data/evaluation_data
        # 全体には影響させない（呼び出し元execute()の外側try/exceptに頼らず、
        # このレベルでfail-softにする）。
        ocr_segments: List[OcrSegment] = []
        for c in video_cuts:
            if not c.get("ocr_text"):
                continue
            try:
                ocr_segments.append(
                    OcrSegment(
                        text=c["ocr_text"],
                        start_sec=c.get("start_seconds"),
                        end_sec=c.get("end_seconds"),
                    )
                )
            except Exception as e:
                self.logger.warning(
                    f"Skipping malformed video_cuts OCR segment "
                    f"(cut_id={c.get('cut_id')!r}): {e}"
                )
        asset_structure_v0 = AssetStructureV0(
            cuts=cuts,
            transcript_segments=[],  # ASRはセグメント単位のタイムスタンプを保持していないため空
            ocr_segments=ocr_segments,
        )

        asset_json = AssetJsonV0(
            asset_meta=asset_meta_v0,
            media_info=media_info_v0,
            asset_structure=asset_structure_v0,
            asset_annotations=AssetAnnotationsV0(),
        )

        evaluation_meta_v0 = EvaluationMetaV0(
            evaluated_at=datetime.now(),
            evaluator_model=spec.metadata.ai_model_version,
            # processing_time_ms は AnalysisOrchestrator.run() 完了後、
            # _metadata.processing_time_ms と同じタイミングで上書きされる。
            processing_time_ms=spec.metadata.processing_time_ms,
            validation_status=spec.metadata.validation_status,
            validation_notes=spec.metadata.validation_notes,
            analysis_tools_used=spec.metadata.analysis_tools_used,
        )

        evaluation_json = EvaluationJsonV0(
            evaluation_meta=evaluation_meta_v0,
            diagnostics=spec.diagnostics,
            performance=spec.performance,
            landing_page_analysis=spec.landing_page,
        )

        return json.loads(asset_json.json()), json.loads(evaluation_json.json())

    @staticmethod
    def _parse_dimensions(metadata_result: Dict[str, Any]) -> Tuple[Optional[int], Optional[int]]:
        """
        metadata_result から width/height を honest に取り出す。

        画像は width_pixels/height_pixels、動画は "1920x1080" 形式の
        resolution 文字列で来るため、フォーマットを揃える。どちらも
        取れない、または型が想定と違う場合も例外を投げず、捏造せず
        (None, None) を返す（呼び出し元がメタデータをどう組み立てて来ても、
        このヘルパー自体は落ちない契約にする）。
        """
        width = metadata_result.get("width_pixels")
        height = metadata_result.get("height_pixels")
        if isinstance(width, int) and isinstance(height, int):
            return width, height

        resolution = metadata_result.get("resolution")
        if isinstance(resolution, str) and "x" in resolution:
            try:
                width_str, height_str = resolution.split("x", 1)
                return int(width_str), int(height_str)
            except ValueError:
                pass

        return None, None
    
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
