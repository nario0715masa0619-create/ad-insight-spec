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
import time

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
        asset_name: Optional[str] = None,
    ):
        """
        Initialize orchestrator with input parameters.

        Args:
            input_path: Path to creative file (video/image/text)
            lp_input: LP URL or HTML file path (optional)
            kpi_path: KPI JSON file path (optional)
            mode: Input mode (file_only / file_plus_lp / file_plus_lp_plus_manual_kpi / api_import_ready)
            asset_name: ユーザー指定の広告名/キャンペーン名（optional。未指定ならフォールバックなし=None）
        """
        self.input_path = input_path
        self.lp_input = lp_input
        self.kpi_path = kpi_path
        self.mode = mode
        self.asset_name = asset_name
        self.start_time = datetime.now()
        
        # Results from each service
        self.ingested_asset: Optional[Dict[str, Any]] = None
        self.metadata: Optional[Dict[str, Any]] = None
        self.video_result: Optional[Dict[str, Any]] = None
        self.ocr_result: Optional[Dict[str, Any]] = None
        # カット別分析（動画のみ）: [{cut_id, start_seconds, end_seconds, frame_path, ocr_text}, ...]
        # カットの代表フレームは _step_llm（Vision API呼び出し）まで生存させる必要があるため、
        # 全体動画用の VideoService とは別インスタンスで管理し、run() の最後に明示的に破棄する。
        self.video_cuts: list = []
        self._cut_video_service = None
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

            # 各ステップの所要時間をログに出す（本番でどの段階が遅いかを
            # 事後調査できるように。特定ファイルでのみ発生するタイムアウトの
            # 切り分けに使う）。
            step_start = time.time()

            def _log_step(step_name: str) -> None:
                nonlocal step_start
                now = time.time()
                logger.info(f"Step timing: {step_name} took {now - step_start:.2f}s")
                step_start = now

            # Step 1: Ingestion
            logger.info("Step 1: Ingestion Service")
            self._step_ingest()
            _log_step("1_ingest")

            # Step 2: Metadata Extraction
            logger.info("Step 2: Metadata Service")
            self._step_metadata()
            _log_step("2_metadata")

            # Step 3: Content Analysis (parallel)
            logger.info("Step 3: Content Analysis (Video/OCR/LP)")
            self._step_content_analysis()
            _log_step("3_content_analysis")

            # Step 4: LLM Labeling
            logger.info("Step 4: LLM Service")
            self._step_llm()
            _log_step("4_llm")

            # Step 5: Load KPI (if provided)
            if self.kpi_path:
                logger.info("Step 5: Load KPI")
                self._step_load_kpi()
                _log_step("5_load_kpi")

            # Step 6: Converter
            logger.info("Step 6: Converter Service")
            self._step_converter()
            _log_step("6_converter")

            processing_time_ms = int((datetime.now() - self.start_time).total_seconds() * 1000)
            logger.info(f"Analysis complete: {processing_time_ms}ms")
            
            # Add processing time to spec
            if self.final_spec and "_metadata" in self.final_spec:
                self.final_spec["_metadata"]["processing_time_ms"] = processing_time_ms
            
            return self.final_spec or {}

        except Exception as e:
            logger.error(f"Pipeline failed: {str(e)}")
            raise ProcessingError(f"Analysis failed: {str(e)}") from e
        finally:
            # カット代表フレームの一時ディレクトリは _step_llm での
            # Vision API呼び出しまで生存させる必要があったため cleanup を
            # 遅延させていた。パイプライン完了・失敗を問わずここで破棄する。
            if self._cut_video_service is not None:
                self._cut_video_service.cleanup()

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

        if self.asset_name:
            self.metadata["asset_name"] = self.asset_name

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
            video_file_path = self.ingested_asset.get("file_path")
            try:
                video_service = VideoService(num_frames=5)
                if video_file_path:
                    self.video_result = video_service.execute(video_file_path)
                    logger.info("Video processing successful")
                    # Cleanup temp files（この用途のフレームは以降どこにも使われない）
                    video_service.cleanup()
            except Exception as e:
                logger.warning(f"Video processing failed (non-fatal): {str(e)}")
                self.video_result = {"success": False, "message": str(e)}

            # カット別分析用: シーン切り替え目安でカット分割し、各カットの
            # 代表フレームを抽出してOCRする。代表フレームは _step_llm の
            # Vision API呼び出しまで使うため、ここではcleanup()しない
            # （run() の最後で明示的に破棄する）。失敗しても全体分析には
            # 影響させない（fail-soft、video_cuts は空リストのまま）。
            try:
                from app.services.ocr_service import OCRService as _OCRServiceForCuts
                if video_file_path:
                    duration = (self.video_result or {}).get("duration_seconds", 0)
                    self._cut_video_service = VideoService()
                    cut_ranges = self._cut_video_service.detect_cuts(video_file_path, duration)
                    video_cuts = []
                    for idx, (start, end) in enumerate(cut_ranges, start=1):
                        frame_path = self._cut_video_service.extract_cut_frame(
                            video_file_path, (start + end) / 2
                        )
                        if not frame_path:
                            continue
                        ocr = _OCRServiceForCuts.extract_text_from_image(frame_path)
                        video_cuts.append({
                            "cut_id": f"cut_{idx}",
                            "start_seconds": start,
                            "end_seconds": end,
                            "frame_path": frame_path,
                            "ocr_text": ocr.get("ocr_extracted_text", ""),
                        })
                    self.video_cuts = video_cuts
                    logger.info(f"Detected {len(video_cuts)} video cuts")
            except Exception as e:
                logger.warning(f"Video cut detection failed (non-fatal): {str(e)}")
                self.video_cuts = []
        else:
            self.video_result = {}
        
        # OCR processing
        try:
            from app.services.ocr_service import OCRService
            media_type = "video" if self.ingested_asset and self.ingested_asset.get("format") == "video_static" else "image"
            file_path = self.ingested_asset.get("file_path", "") if self.ingested_asset else ""
            if file_path:
                self.ocr_result = OCRService.extract_text(file_path, media_type=media_type)
                logger.info(f"OCR processing complete ({media_type})")
            else:
                self.ocr_result = {"success": False, "ocr_extracted_text": "", "confidence": 0.0}
        except Exception as e:
            logger.warning(f"OCR processing failed (non-fatal): {str(e)}")
            self.ocr_result = {"success": False, "ocr_extracted_text": "", "confidence": 0.0}
        
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
        from concurrent.futures import ThreadPoolExecutor
        import os

        try:
            file_path = self.ingested_asset.get("file_path", "unknown") if self.ingested_asset else "unknown"
            format_type = self.ingested_asset.get("format", "") if self.ingested_asset else ""
            
            if format_type == "video_static":
                description = f"Video from {file_path}, extracted frames analyzed"
                frames_data = self.ocr_result.get("frames", []) if self.ocr_result else []
                ocr_text = self.ocr_result.get("ocr_extracted_text", "") if self.ocr_result else ""
                if ocr_text:
                    description += f"\n\n[OCR from {len(frames_data)} frames]\n{ocr_text}"
            else:
                description = f"Image from {file_path}"
                ocr_text = self.ocr_result.get("ocr_extracted_text", "") if self.ocr_result else ""
                if ocr_text:
                    description += f"\n\n[OCR Extracted Text]\n{ocr_text}"
                
            lp_content = self.lp_result.get("fv_copy") if self.lp_result else None
            llm_model = os.getenv("LLM_MODEL", "gpt")

            llm_step_start = time.time()
            llm_result = LLMService.analyze_creative(
                image_description=description,
                lp_content=lp_content,
                model=llm_model
            )
            logger.info(f"Step timing: 4a_analyze_creative took {time.time() - llm_step_start:.2f}s")

            def _dump_model(m):
                return m.model_dump() if hasattr(m, "model_dump") else m.dict()

            cc_dict = _dump_model(llm_result.creative_core) if llm_result.creative_core else {}

            # P0 改善コメント生成・意思決定支援ブロック生成・（動画のみ）カット別分析は
            # いずれも独立した呼び出しであり、互いの結果には影響しない（fail-soft）。
            # それぞれ最大3回までリトライするため直列実行だと合計待ち時間が長くなり
            # すぎ（実測: decision_support単体でリトライ込み最大70秒超）、本番で
            # クライアント側タイムアウトを引き起こしていた。並列実行に変更し、
            # 合計待ち時間を「全体の合計」から「最も遅いもの」に短縮する。
            parallel_start = time.time()
            with ThreadPoolExecutor(max_workers=3) as executor:
                improvements_future = executor.submit(
                    LLMService.analyze_creative_improvements,
                    creative_analysis=cc_dict,
                    model=llm_model,
                )
                decision_support_future = executor.submit(
                    LLMService.generate_decision_support,
                    creative_analysis=cc_dict,
                    model=llm_model,
                )
                video_cuts_future = None
                if self.video_cuts:
                    video_cuts_future = executor.submit(
                        LLMService.analyze_video_cuts,
                        video_cuts=self.video_cuts,
                        model=llm_model,
                    )

                improvements_result = improvements_future.result()
                logger.info(f"Step timing: 4b_analyze_creative_improvements (parallel) took {time.time() - parallel_start:.2f}s")
                decision_support_result = decision_support_future.result()
                logger.info(f"Step timing: 4c_generate_decision_support (parallel) took {time.time() - parallel_start:.2f}s")

                # video_cuts_future.result() で万一未捕捉の例外が上がると、この
                # try ブロックの外側（_step_llm 全体）の except に落ちて
                # self.llm_result が丸ごと空になり、既に成功している
                # improvements/decision_support まで巻き添えで消えてしまう。
                # カット別分析はあくまで付加機能であり、全体分析を道連れに
                # してはならないため、ここだけ個別に fail-soft で受け止める。
                video_cuts_result = None
                if video_cuts_future:
                    try:
                        video_cuts_result = video_cuts_future.result()
                    except Exception as e:
                        logger.warning(f"Video cut analysis failed unexpectedly (non-fatal): {str(e)}")
                        from app.schemas.llm_response import LLMVideoCutAnalysisValidationError as _VCErr
                        video_cuts_result = _VCErr(
                            success=False,
                            error_code="LLM_ERROR",
                            reason=f"Video cut analysis failed unexpectedly: {str(e)}",
                        )
                    logger.info(f"Step timing: 4d_analyze_video_cuts (parallel) took {time.time() - parallel_start:.2f}s")

            from app.schemas.llm_response import LLMImprovementValidationError
            if isinstance(improvements_result, LLMImprovementValidationError):
                improvements_data = None
                improvements_error = _dump_model(improvements_result)
            else:
                improvements_data = _dump_model(improvements_result)
                improvements_error = None

            from app.schemas.llm_response import LLMDecisionSupportValidationError
            if isinstance(decision_support_result, LLMDecisionSupportValidationError):
                decision_support_data = None
                decision_support_error = _dump_model(decision_support_result)
            else:
                decision_support_data = _dump_model(decision_support_result)
                decision_support_error = None

            # ===== video_cuts（v1.0 最小構造化スキーマ）の組み立て =====
            # diagnostics.video_cuts は schema_version/generation_status/video_summary/
            # video_cuts を1つにまとめたブロック（docs/specs/video_cuts_json_schema_v1_0.md）。
            # 画像フォーマットではこの概念自体が存在しないため None のまま。
            from app.schemas.llm_response import LLMVideoCutAnalysisValidationError
            video_cuts_block = None
            if format_type == "video_static":
                if video_cuts_result is None:
                    # カット検出自体が行われなかった（動画処理失敗等、fail-soft）
                    video_cuts_block = {
                        "schema_version": "1.0",
                        "generation_status": {"status": "not_attempted", "error_code": None},
                        "video_summary": None,
                        "video_cuts": [],
                    }
                elif isinstance(video_cuts_result, LLMVideoCutAnalysisValidationError):
                    video_cuts_block = {
                        "schema_version": "1.0",
                        "generation_status": {
                            "status": "failed",
                            "error_code": video_cuts_result.error_code,
                        },
                        "video_summary": None,
                        "video_cuts": [],
                    }
                else:
                    video_cuts_dump = _dump_model(video_cuts_result)
                    # LLMは時間範囲を出力しない（バックエンド側で確定済みのため）。
                    # ここで self.video_cuts（検出済みの start/end）を cut_id で
                    # マージしてから最終結果に格納する。
                    timing_by_cut_id = {c["cut_id"]: c for c in self.video_cuts}
                    cuts_list = []
                    for cut in video_cuts_dump.get("cuts", []):
                        timing = timing_by_cut_id.get(cut.get("cut_id"))
                        if timing:
                            cut["start_seconds"] = timing["start_seconds"]
                            cut["end_seconds"] = timing["end_seconds"]
                        cuts_list.append(cut)
                    total_duration = max(
                        (c["end_seconds"] for c in cuts_list if c.get("end_seconds") is not None),
                        default=0.0,
                    )
                    video_cuts_block = {
                        "schema_version": "1.0",
                        "generation_status": {"status": "success", "error_code": None},
                        "video_summary": {
                            "total_duration_seconds": total_duration,
                            "cut_count": len(cuts_list),
                        },
                        "video_cuts": cuts_list,
                    }

            self.llm_result = {
                "creative_core": {
                    "visuals": cc_dict.get("visuals", {}),
                    "tone": cc_dict.get("tone", {}),
                    "ai_labels": cc_dict.get("ai_labels", []),
                    "ocr_extracted_text": ocr_text,
                    "llm_model": llm_result.model,
                    "llm_success": llm_result.success,
                    "llm_retry_count": llm_result.retry_count,
                    "llm_error": llm_result.error_details
                },
                "improvements": improvements_data,
                "improvements_error": improvements_error,
                "decision_support": decision_support_data,
                "decision_support_error": decision_support_error,
                "video_cuts": video_cuts_block,
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
