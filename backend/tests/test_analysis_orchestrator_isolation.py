"""
_step_llm の並列生成（improvements / decision_support / video_cuts）が
互いに独立してfail-softであることを検証する回帰テスト。

背景: video_cuts_future.result() のみが個別のtry/exceptで保護されており、
improvements_future/decision_support_future の .result() は無保護だった。
そのため decision_support 側で予期しない例外が発生すると、_step_llm 全体の
except に落ちて self.llm_result が丸ごと空になり、既に成功していた
improvements/video_cuts まで巻き添えで消えていた（本番での実観測: 5軸診断が
出ない時にカット別分析も出ない、という非対称な巻き込み）。
3方向すべてで対称にfail-softであることをここで固定する。
"""
from unittest.mock import patch

from app.services.analysis_orchestrator import AnalysisOrchestrator
from app.schemas.llm_response import (
    LLMResponseSchema,
    CreativeCoreSchema,
    VisualsSchema,
    ToneSchema,
    ImprovementCommentsSchema,
    ImprovementComment,
    VideoCutAnalysis,
    VideoCutContent,
)


def _make_creative_response():
    return LLMResponseSchema(
        success=True,
        model="gpt-4o",
        creative_core=CreativeCoreSchema(
            visuals=VisualsSchema(dominant_colors=["青", "白"], composition="中央に商品を配置した構図", style="モダン", clarity="高"),
            tone=ToneSchema(primary_tone=["信頼感"], emotional_appeal="論理的", call_to_action="強"),
            ai_labels=["広告", "マーケティング"],
        ),
        retry_count=0,
    )


def _make_improvements():
    return ImprovementCommentsSchema(
        comments=[
            ImprovementComment(
                issue_summary="CTAボタンのテキストが曖昧",
                target_scope="CTAボタン",
                evidence="ボタンテキストが『詳細を見る』で行動を促す動詞がない",
                recommended_action="『今すぐ登録する』に変更する",
                expected_impact="クリック率5〜10%向上",
            )
        ],
        total_count=1,
        summary="CTA周りの改善が優先",
    )


def _make_video_cuts():
    return VideoCutAnalysis(
        cuts=[
            VideoCutContent(
                cut_id="cut_1",
                role_tag="hook",
                summary="画面内容の要約テキスト",
                improvement_suggestion="具体的な改善提案テキスト",
            )
        ]
    )


def _make_orchestrator_ready_for_step_llm(video_static: bool = True):
    orch = AnalysisOrchestrator(input_path="dummy.mp4")
    orch.ingested_asset = {"file_path": "dummy.mp4", "format": "video_static" if video_static else "image_static"}
    orch.ocr_result = {"success": True, "ocr_extracted_text": "", "frames": []}
    orch.lp_result = {}
    if video_static:
        orch.video_cuts = [
            {"cut_id": "cut_1", "start_seconds": 0.0, "end_seconds": 5.0, "frame_path": "/tmp/f1.png", "ocr_text": ""}
        ]
    return orch


class TestParallelGenerationIsolation:
    """improvements/decision_support/video_cutsのいずれか1つが予期せず例外を投げても、他の2つの結果は保持される"""

    @patch("app.services.llm_service.LLMService.analyze_video_cuts")
    @patch("app.services.llm_service.LLMService.generate_decision_support")
    @patch("app.services.llm_service.LLMService.analyze_creative_improvements")
    @patch("app.services.llm_service.LLMService.analyze_creative")
    def test_decision_support_crash_does_not_wipe_out_video_cuts_or_improvements(
        self, mock_analyze_creative, mock_improvements, mock_decision_support, mock_video_cuts
    ):
        mock_analyze_creative.return_value = _make_creative_response()
        mock_improvements.return_value = _make_improvements()
        mock_decision_support.side_effect = RuntimeError("unexpected connection reset")
        mock_video_cuts.return_value = _make_video_cuts()

        orch = _make_orchestrator_ready_for_step_llm(video_static=True)
        orch._step_llm()

        assert orch.llm_result is not None
        assert orch.llm_result.get("improvements") is not None
        assert orch.llm_result.get("decision_support") is None
        assert orch.llm_result.get("decision_support_error", {}).get("error_code") == "LLM_ERROR"
        video_cuts_block = orch.llm_result.get("video_cuts")
        assert video_cuts_block is not None
        assert video_cuts_block["generation_status"]["status"] == "success"
        assert len(video_cuts_block["video_cuts"]) == 1

    @patch("app.services.llm_service.LLMService.analyze_video_cuts")
    @patch("app.services.llm_service.LLMService.generate_decision_support")
    @patch("app.services.llm_service.LLMService.analyze_creative_improvements")
    @patch("app.services.llm_service.LLMService.analyze_creative")
    def test_video_cuts_crash_does_not_wipe_out_decision_support_or_improvements(
        self, mock_analyze_creative, mock_improvements, mock_decision_support, mock_video_cuts
    ):
        from app.schemas.llm_response import DecisionSupport, DecisionSupportSummary, AxisBlock, AXIS_IDS

        mock_analyze_creative.return_value = _make_creative_response()
        mock_improvements.return_value = _make_improvements()

        def _axis(axis_id, label):
            evidence = {
                "location": "テスト対象箇所",
                "viewpoint": "視認性",
                "evaluation": "良好",
                "rationale": "テストのための根拠テキスト",
            }
            return AxisBlock(
                axis=axis_id,
                axis_label=label,
                score=4,
                strength={
                    "target_element": "テスト要素",
                    "description": "テスト用の説明テキストです",
                    "reason": "テスト用の理由テキストです",
                    "keep_reason": "テスト用の維持理由テキストです",
                    "evidence": evidence,
                },
                weakness={
                    "target_element": "テスト要素",
                    "description": "テスト用の説明テキストです",
                    "reason": "テスト用の理由テキストです",
                    "impact": "テスト用の影響テキストです",
                    "evidence": evidence,
                },
                recommendation={
                    "what": "テスト用の変更内容テキストです",
                    "why": "テスト用の理由テキストです",
                    "how": "テスト用の検証方法テキストです",
                    "expected_effect": "CVR+5%向上を見込む",
                },
            )

        from app.schemas.llm_response import EVALUATION_AXES

        mock_decision_support.return_value = DecisionSupport(
            summary=DecisionSupportSummary(headline="判定：テスト用の一言結論", decision="改修推奨", rationale="テスト用の判断理由テキストです"),
            axes=[_axis(axis_id, label) for axis_id, label in EVALUATION_AXES],
        )
        mock_video_cuts.side_effect = RuntimeError("unexpected vision api timeout")

        orch = _make_orchestrator_ready_for_step_llm(video_static=True)
        orch._step_llm()

        assert orch.llm_result is not None
        assert orch.llm_result.get("improvements") is not None
        assert orch.llm_result.get("decision_support") is not None
        assert orch.llm_result.get("decision_support", {}).get("axes")
        video_cuts_block = orch.llm_result.get("video_cuts")
        assert video_cuts_block is not None
        assert video_cuts_block["generation_status"]["status"] == "failed"
        assert video_cuts_block["generation_status"]["error_code"] == "LLM_ERROR"

    @patch("app.services.llm_service.LLMService.generate_decision_support")
    @patch("app.services.llm_service.LLMService.analyze_creative_improvements")
    @patch("app.services.llm_service.LLMService.analyze_creative")
    def test_improvements_crash_does_not_wipe_out_decision_support(
        self, mock_analyze_creative, mock_improvements, mock_decision_support
    ):
        from app.schemas.llm_response import LLMDecisionSupportValidationError

        mock_analyze_creative.return_value = _make_creative_response()
        mock_improvements.side_effect = RuntimeError("unexpected connection reset")
        mock_decision_support.return_value = LLMDecisionSupportValidationError(
            success=False, error_code="TIME_BUDGET_EXCEEDED", reason="budget exceeded"
        )

        orch = _make_orchestrator_ready_for_step_llm(video_static=False)
        orch._step_llm()

        assert orch.llm_result is not None
        assert orch.llm_result.get("improvements") is None
        assert orch.llm_result.get("improvements_error", {}).get("error_code") == "LLM_ERROR"
        assert orch.llm_result.get("decision_support") is None
        assert orch.llm_result.get("decision_support_error", {}).get("error_code") == "TIME_BUDGET_EXCEEDED"
