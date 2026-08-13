"""
AnalysisOrchestratorがLPUnsafeRedirectError（Issue #97、lp_urlのredirect経由
SSRF対策）を、他のLP取得失敗（タイムアウト・404等）と違いfail-softで握り
つぶさず、呼び出し元まで正しく伝播させることを検証する回帰テスト。

背景: _step_content_analysis() 内のLP解析は元々「非fatal」として全ての
例外をexcept Exceptionで捕まえ、self.lp_result = {} にフォールバックしていた
（LP取得に失敗しても分析全体は継続する設計）。しかしLPUnsafeRedirectErrorは
SSRF対策の一環であり、握りつぶすとユーザーに何のフィードバックもないまま
（200 OKでLPデータ無しの結果が返るだけ）になってしまう。また run() 側の
包括的な `except Exception as e: raise ProcessingError(...)` も、
LPUnsafeRedirectError特有の型（ValueErrorを継承しており、specs.py側の
既存の`except ValueError`分岐で400として扱われる）を消してしまうため、
_step_content_analysis()・run()の両方でLPUnsafeRedirectErrorだけを
re-raiseする特別扱いを入れている。この2箇所を直接検証する。
"""
from unittest.mock import patch

import pytest

from app.services.analysis_orchestrator import AnalysisOrchestrator
from app.services.base_service import ProcessingError
from app.services.lp_service import LPUnsafeRedirectError


def _make_orchestrator_ready_for_content_analysis():
    orch = AnalysisOrchestrator(input_path="dummy.png", lp_input="https://93.184.216.34/lp")
    orch.ingested_asset = {"file_path": "dummy.png", "format": "image_static"}
    return orch


class TestStepContentAnalysisDoesNotSwallowUnsafeRedirect:
    def test_lp_unsafe_redirect_error_propagates_out_of_step(self):
        orch = _make_orchestrator_ready_for_content_analysis()
        with patch(
            "app.services.lp_service.LPService.execute",
            side_effect=LPUnsafeRedirectError("unsafe redirect target detected"),
        ):
            with pytest.raises(LPUnsafeRedirectError):
                orch._step_content_analysis()

    def test_other_lp_failures_remain_fail_soft(self):
        """回帰防止: LPUnsafeRedirectError以外のLP取得失敗は、従来通り
        非fatalとしてself.lp_result = {}にフォールバックすること（今回の
        変更で他のLP失敗の扱いまで変えていないことの確認）"""
        orch = _make_orchestrator_ready_for_content_analysis()
        with patch(
            "app.services.lp_service.LPService.execute",
            side_effect=ProcessingError("timeout etc."),
        ):
            orch._step_content_analysis()  # 例外を投げず正常終了すること
        assert orch.lp_result == {}


class TestRunDoesNotWrapUnsafeRedirectError:
    def test_run_reraises_lp_unsafe_redirect_error_without_wrapping(self):
        """
        run()の包括的なexcept Exceptionに巻き込まれて一般的なProcessingErrorへ
        包まれてしまうと、LPUnsafeRedirectError固有の型（ValueErrorを継承）が
        失われ、specs.py側で500にフォールバックしてしまう。run()から見て
        LPUnsafeRedirectErrorがそのままの型で送出されることを確認する。
        """
        orch = AnalysisOrchestrator(input_path="dummy.png", lp_input="https://93.184.216.34/lp")
        with patch.object(
            orch, "_step_ingest", side_effect=LPUnsafeRedirectError("unsafe redirect target detected")
        ):
            with pytest.raises(LPUnsafeRedirectError):
                orch.run()

    def test_run_still_wraps_other_exceptions_as_processing_error(self):
        """回帰防止: 今回の変更が他の例外のラップ方針まで変えていないこと"""
        orch = AnalysisOrchestrator(input_path="dummy.png")
        with patch.object(orch, "_step_ingest", side_effect=RuntimeError("something else broke")):
            with pytest.raises(ProcessingError):
                orch.run()
