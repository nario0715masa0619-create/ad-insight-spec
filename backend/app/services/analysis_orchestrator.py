"""
AnalysisOrchestrator - Orchestrates the entire analysis pipeline

Responsible for:
- Calling services in correct order
- Passing outputs between services
- Error handling and logging
- Merging results into final spec

Flow: Ingestion ↁEMetadata ↁE(Video/OCR/LP parallel) ↁELLM ↁEConverter ↁEspec
"""

from typing import Dict, Any, Optional
from datetime import datetime
import logging

from app.services.base_service import ServiceError, ProcessingError

logger = logging.getLogger(__name__)

class AnalysisOrchestrator:
    """
    Main orchestrator for the analysis pipeline.
    
    Coordinates service execution and data flow.
    """

    def __init__(
        self,
        input_path: str,
        lp_input: Optional[str] = None,
        kpi_path: Optional[str] = None,
        mode: str = "file_plus_lp_plus_manual_kpi",
    ):
        """
        Initialize orchestrator with input parameters.
        
        Args:
            input_path: Path to creative file (video/image/text)
            lp_input: LP URL or HTML file path (optional)
            kpi_path: KPI JSON file path (optional)
            mode: Input mode (file_only / file_plus_lp / file_plus_lp_plus_manual_kpi / api_import_ready)
        """
        self.input_path = input_path
        self.lp_input = lp_input
        self.kpi_path = kpi_path
        self.mode = mode
        self.start_time = datetime.now()
        
        # Results from each service
        self.ingested_asset: Optional[Dict[str, Any]] = None
        self.metadata: Optional[Dict[str, Any]] = None
        self.video_result: Optional[Dict[str, Any]] = None
        self.ocr_result: Optional[Dict[str, Any]] = None
        self.lp_result: Optional[Dict[str, Any]] = None
        self.llm_result: Optional[Dict[str, Any]] = None
        self.kpi_data: Optional[Dict[str, Any]] = None
        self.final_spec: Optional[Dict[str, Any]] = None

    def run(self) -> Dict[str, Any]:
        """
        Execute the full analysis pipeline.
        
        Returns:
            dict: Final ad_insight_spec (v0.2)
        
        Raises:
            ProcessingError: If any step fails
        """
        try:
            logger.info(f"Starting analysis pipeline: mode={self.mode}")
            
            # Step 1: Ingestion
            logger.info("Step 1: Ingestion Service")
            self._step_ingest()
            
            # Step 2: Metadata Extraction
            logger.info("Step 2: Metadata Service")
            self._step_metadata()
            
            # Step 3: Content Analysis (parallel)
            logger.info("Step 3: Content Analysis (Video/OCR/LP)")
            self._step_content_analysis()
            
            # Step 4: LLM Labeling
            logger.info("Step 4: LLM Service")
            self._step_llm()
            
            # Step 5: Load KPI (if provided)
            if self.kpi_path:
                logger.info("Step 5: Load KPI")
                self._step_load_kpi()
            
            # Step 6: Converter
            logger.info("Step 6: Converter Service")
            self._step_converter()
            
            processing_time_ms = int((datetime.now() - self.start_time).total_seconds() * 1000)
            logger.info(f"Analysis complete: {processing_time_ms}ms")
            
            # Add processing time to spec
            if self.final_spec and "_metadata" in self.final_spec:
                self.final_spec["_metadata"]["processing_time_ms"] = processing_time_ms
            
            return self.final_spec or {}
        
        except Exception as e:
            logger.error(f"Pipeline failed: {str(e)}")
            raise ProcessingError(f"Analysis failed: {str(e)}") from e

    def _step_ingest(self) -> None:
        """
        Step 1: Ingest file
        
        Responsibilities:
        - Load file from disk
        - Validate format
        - Return normalized IngestedAsset
        """
        # Import and call IngestionService
        from app.services.ingestion_service import IngestionService
        service = IngestionService()
        self.ingested_asset = service.execute(self.input_path)
        
        if not self.ingested_asset:
            raise ProcessingError("Ingestion failed")

    def _step_metadata(self) -> None:
        """
        Step 2: Extract metadata
        
        Responsibilities:
        - Generate asset_id
        - Extract video/image/text metadata
        - Prepare asset_meta section
        """
        # Import and call MetadataService
        from app.services.metadata_service import MetadataService
        service = MetadataService()
        self.metadata = service.execute(self.ingested_asset)
        
        if not self.metadata:
            raise ProcessingError("Metadata extraction failed")

    def _step_content_analysis(self) -> None:
        """
        Step 3: Content Analysis (parallel execution)
        
        Responsibilities:
        - Extract video frames (if video)
        - OCR text (if image - currently mock)
        - Parse LP (if LP provided)
        
        Can be parallelized in future with ThreadPoolExecutor.
        """
        from app.services.video_service import VideoService
        from app.services.ocr_service import OCRService
        from app.services.lp_service import LPService
        
        # Extract video frames if input is video
        if self.ingested_asset and self.ingested_asset.get("format") == "video_static":
            try:
                video_service = VideoService(num_frames=5)
                # Assume ingested_asset has file_path
                video_file_path = self.ingested_asset.get("file_path")
                if video_file_path:
                    self.video_result = video_service.execute(video_file_path)
                    logger.info("Video processing successful")
                    # Cleanup temp files
                    video_service.cleanup()
            except Exception as e:
                logger.warning(f"Video processing failed (non-fatal): {str(e)}")
                self.video_result = {"success": False, "message": str(e)}
        else:
            self.video_result = {}
        
        # OCR (currently mock implementation - will be upgraded Phase 2)
        try:
            ocr_service = OCRService(engine="mock")
            # Placeholder - would need actual image paths in future
            self.ocr_result = ocr_service.execute("dummy_path")
            logger.info("OCR processing complete (mock)")
        except Exception as e:
            logger.warning(f"OCR processing failed (non-fatal): {str(e)}")
            self.ocr_result = {"success": False, "message": str(e)}
        
        # Parse LP if provided
        if self.lp_input:
            try:
                lp_service = LPService()
                self.lp_result = lp_service.execute(self.lp_input)
                logger.info("LP parsing successful")
            except Exception as e:
                logger.warning(f"LP parsing failed (non-fatal): {str(e)}")
                self.lp_result = {}
        else:
            self.lp_result = {}
        
        logger.info("Content analysis complete (Video/OCR/LP)")

    def _step_llm(self) -> None:
        """
        Step 4: LLM Labeling
        
        Uses Gemini 2.0 Flash / GPT-4o integration via LLMService
        """
        from app.services.llm_service import LLMService
        import os
        
        try:
            file_path = self.ingested_asset.get("file_path", "unknown") if self.ingested_asset else "unknown"
            format_type = self.ingested_asset.get("format", "") if self.ingested_asset else ""
            
            if format_type == "video_static":
                description = f"Video from {file_path}, extracted frames analyzed"
            else:
                description = f"Image from {file_path}"
                
            lp_content = self.lp_result.get("fv_copy") if self.lp_result else None
            llm_model = os.getenv("LLM_MODEL", "gpt")
            
            llm_result = LLMService.analyze_creative(
                image_description=description,
                lp_content=lp_content,
                model=llm_model
            )
            
            cc_dict = llm_result.creative_core.model_dump() if llm_result.creative_core else {}
            
            self.llm_result = {
                "creative_core": {
                    "visuals": cc_dict.get("visuals", {}),
                    "tone": cc_dict.get("tone", {}),
                    "ai_labels": cc_dict.get("ai_labels", []),
                    "llm_model": llm_result.model,
                    "llm_success": llm_result.success,
                    "llm_retry_count": llm_result.retry_count,
                    "llm_error": llm_result.error_details
                }
            }
            logger.info("LLM analysis complete")
        except Exception as e:
            logger.warning(f"LLM analysis failed (non-fatal): {str(e)}")
            self.llm_result = {"creative_core": {}}

    def _step_load_kpi(self) -> None:
        """
        Step 5: Load KPI (if provided)
        """
        import json
        try:
            with open(self.kpi_path, 'r', encoding='utf-8') as f:
                self.kpi_data = json.load(f)
            logger.info(f"KPI loaded: {self.kpi_path}")
        except Exception as e:
            raise ProcessingError(f"Failed to load KPI: {str(e)}")

    def _step_converter(self) -> None:
        """
        Step 6: Convert to ad_insight_spec v0.2
        
        Aggregate all Service outputs and convert to final spec.
        Validate against Pydantic model.
        """
        from app.services.converter_service import ConverterService
        
        try:
            converter_service = ConverterService()
            self.final_spec = converter_service.execute(
                mode=self.mode,
                ingestion_result=self.ingested_asset or {},
                metadata_result=self.metadata or {},
                lp_result=self.lp_result or {},
                video_result=self.video_result or {},
                ocr_result=self.ocr_result or {},
                llm_result=self.llm_result or {},
                kpi_result=self.kpi_data,
            )
            logger.info("Conversion to ad_insight_spec complete")
        except Exception as e:
            raise ProcessingError(f"Converter failed: {str(e)}")

    def get_spec(self) -> Dict[str, Any]:
        """Return final spec (after run())"""
        return self.final_spec or {}
