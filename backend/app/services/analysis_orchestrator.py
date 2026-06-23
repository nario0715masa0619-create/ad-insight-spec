"""
AnalysisOrchestrator - Orchestrates the entire analysis pipeline

Responsible for:
- Calling services in correct order
- Passing outputs between services
- Error handling and logging
- Merging results into final spec

Flow: Ingestion → Metadata → (Video/OCR/LP parallel) → LLM → Converter → spec
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
        - OCR text (if image)
        - Parse LP (if LP provided)
        """
        self.video_result = {"frames": [], "duration_seconds": None}
        self.ocr_result = {"text": "", "confidence": 0.0}
        self.lp_result = {"fv_copy": "", "form_fields": []}
        
        logger.info("Content analysis (using mock data for now)")

    def _step_llm(self) -> None:
        """
        Step 4: LLM Labeling
        
        Responsibilities:
        - Analyze creative (hook, tone, emotion)
        - Calculate message consistency (if LP provided)
        - Generate recommendations
        """
        self.llm_result = {
            "hook_type": "benefit",
            "primary_tone": "inspirational",
            "detected_emotions": [],
            "message_consistency_score": None,
            "message_consistency_basis": None,
        }
        logger.info("LLM labeling (using mock data for now)")

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
        """
        from datetime import datetime as dt
        
        self.final_spec = {
            "input_metadata": {
                "mode": self.mode,
                "source_type": "local_file",
                "input_timestamp": dt.now().isoformat() + "Z",
            },
            "asset_meta": self.metadata or {},
            "creative_core": {},
            "landing_page": self.lp_result if self.lp_input else None,
            "performance": self.kpi_data if self.kpi_path else None,
            "diagnostics": {
                "qualitative": {},
                "quantitative": None,
            },
            "views": None,
            "_metadata": {
                "generated_at": dt.now().isoformat() + "Z",
                "data_source": "local_file",
                "ai_model_version": "gemini-2.0-flash",
                "json_schema_version": "v0.2",
                "input_mode": self.mode,
            }
        }
        
        logger.info("Converter: Spec generated (placeholder)")

    def get_spec(self) -> Dict[str, Any]:
        """Return final spec (after run())"""
        return self.final_spec or {}
