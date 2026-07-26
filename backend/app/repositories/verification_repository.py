from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from typing import List, Optional, Dict, Any
from datetime import datetime

from app.models import VerificationCase, VerificationSuggestionEvaluation, VerificationFollowup


class VerificationRepository:
    """
    CampaignPilot 検証機能の DB アクセス層。

    AdInsightRepository と同じく、エンドポイント層は直接 DB にアクセスせず
    このクラスを経由する。
    """

    def __init__(self, db: Session):
        self.db = db

    # ===== VerificationCase =====

    def create_case(
        self,
        case_name: str,
        asset_id: Optional[str],
        asset_version: Optional[int],
        pre_hearing_notes: Optional[Dict[str, Any]],
    ) -> VerificationCase:
        record = VerificationCase(
            case_name=case_name,
            asset_id=asset_id,
            asset_version=asset_version,
            pre_hearing_notes=pre_hearing_notes,
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def get_case(self, case_id: int) -> Optional[VerificationCase]:
        return self.db.query(VerificationCase).filter(VerificationCase.id == case_id).first()

    def list_cases(self, skip: int = 0, limit: int = 10) -> tuple[List[VerificationCase], int]:
        query = self.db.query(VerificationCase)
        total_count = query.count()
        records = query.order_by(desc(VerificationCase.created_at)).offset(skip).limit(limit).all()
        return records, total_count

    def count_suggestions_by_case(self, case_ids: List[int]) -> Dict[int, int]:
        """一覧表示用: case_id ごとの提案評価件数をまとめて取得"""
        if not case_ids:
            return {}
        rows = (
            self.db.query(
                VerificationSuggestionEvaluation.case_id,
                func.count(VerificationSuggestionEvaluation.id),
            )
            .filter(VerificationSuggestionEvaluation.case_id.in_(case_ids))
            .group_by(VerificationSuggestionEvaluation.case_id)
            .all()
        )
        return {case_id: count for case_id, count in rows}

    def update_presentation_evaluation(
        self, case_id: int, presentation_evaluation: Dict[str, Any]
    ) -> Optional[VerificationCase]:
        record = self.get_case(case_id)
        if not record:
            return None
        record.presentation_evaluation = presentation_evaluation
        record.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(record)
        return record

    # ===== VerificationSuggestionEvaluation =====

    def add_suggestion_evaluation(
        self,
        case_id: int,
        suggestion_key: str,
        suggestion_text: Optional[str],
        awareness_rating: str,
        originality_rating: str,
    ) -> Optional[VerificationSuggestionEvaluation]:
        if not self.get_case(case_id):
            return None
        record = VerificationSuggestionEvaluation(
            case_id=case_id,
            suggestion_key=suggestion_key,
            suggestion_text=suggestion_text,
            awareness_rating=awareness_rating,
            originality_rating=originality_rating,
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def get_suggestion_evaluation(self, suggestion_id: int) -> Optional[VerificationSuggestionEvaluation]:
        return (
            self.db.query(VerificationSuggestionEvaluation)
            .filter(VerificationSuggestionEvaluation.id == suggestion_id)
            .first()
        )

    def update_suggestion_evaluation(
        self,
        suggestion_id: int,
        awareness_rating: Optional[str] = None,
        originality_rating: Optional[str] = None,
    ) -> Optional[VerificationSuggestionEvaluation]:
        record = self.get_suggestion_evaluation(suggestion_id)
        if not record:
            return None
        if awareness_rating is not None:
            record.awareness_rating = awareness_rating
        if originality_rating is not None:
            record.originality_rating = originality_rating
        record.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(record)
        return record

    def list_suggestion_evaluations(self, case_id: int) -> List[VerificationSuggestionEvaluation]:
        return (
            self.db.query(VerificationSuggestionEvaluation)
            .filter(VerificationSuggestionEvaluation.case_id == case_id)
            .order_by(VerificationSuggestionEvaluation.created_at)
            .all()
        )

    # ===== VerificationFollowup =====

    def upsert_followup(
        self,
        suggestion_evaluation_id: int,
        checkpoint: str,
        executed: Optional[bool],
        result_change: Optional[str],
    ) -> Optional[VerificationFollowup]:
        if not self.get_suggestion_evaluation(suggestion_evaluation_id):
            return None

        record = (
            self.db.query(VerificationFollowup)
            .filter(
                VerificationFollowup.suggestion_evaluation_id == suggestion_evaluation_id,
                VerificationFollowup.checkpoint == checkpoint,
            )
            .first()
        )
        if record:
            record.executed = executed
            record.result_change = result_change
            record.recorded_at = datetime.utcnow()
        else:
            record = VerificationFollowup(
                suggestion_evaluation_id=suggestion_evaluation_id,
                checkpoint=checkpoint,
                executed=executed,
                result_change=result_change,
            )
            self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def list_followups(self, suggestion_evaluation_id: int) -> List[VerificationFollowup]:
        return (
            self.db.query(VerificationFollowup)
            .filter(VerificationFollowup.suggestion_evaluation_id == suggestion_evaluation_id)
            .order_by(VerificationFollowup.checkpoint)
            .all()
        )

    def list_followups_by_case(self, case_id: int) -> Dict[int, List[VerificationFollowup]]:
        """CSVエクスポート用: case内の全提案のフォローアップを suggestion_evaluation_id ごとにまとめて取得"""
        rows = (
            self.db.query(VerificationFollowup)
            .join(
                VerificationSuggestionEvaluation,
                VerificationFollowup.suggestion_evaluation_id == VerificationSuggestionEvaluation.id,
            )
            .filter(VerificationSuggestionEvaluation.case_id == case_id)
            .all()
        )
        grouped: Dict[int, List[VerificationFollowup]] = {}
        for row in rows:
            grouped.setdefault(row.suggestion_evaluation_id, []).append(row)
        return grouped

    # ===== CSV export =====

    def list_export_rows(self) -> List[Dict[str, Any]]:
        """
        全案件を「案件 x 提案」単位で1行に平坦化したリストを返す（CSV出力用）。
        提案評価が1件も無い案件は、案件情報のみの1行として出力する。
        week_2/week_4 のフォローアップは同じ行に横展開する。
        """
        cases = self.db.query(VerificationCase).order_by(VerificationCase.id).all()
        rows: List[Dict[str, Any]] = []

        for case in cases:
            suggestions = self.list_suggestion_evaluations(case.id)
            followups_by_suggestion = self.list_followups_by_case(case.id)

            if not suggestions:
                rows.append(self._build_export_row(case, None, {}))
                continue

            for suggestion in suggestions:
                followups = {
                    f.checkpoint: f for f in followups_by_suggestion.get(suggestion.id, [])
                }
                rows.append(self._build_export_row(case, suggestion, followups))

        return rows

    @staticmethod
    def _build_export_row(
        case: VerificationCase,
        suggestion: Optional[VerificationSuggestionEvaluation],
        followups: Dict[str, VerificationFollowup],
    ) -> Dict[str, Any]:
        week_2 = followups.get("week_2")
        week_4 = followups.get("week_4")
        return {
            "case_id": case.id,
            "case_name": case.case_name,
            "asset_id": case.asset_id or "",
            "asset_version": case.asset_version if case.asset_version is not None else "",
            "case_created_at": case.created_at.isoformat() if case.created_at else "",
            "pre_hearing_notes": case.pre_hearing_notes or {},
            "presentation_evaluation": case.presentation_evaluation or {},
            "suggestion_id": suggestion.id if suggestion else "",
            "suggestion_key": suggestion.suggestion_key if suggestion else "",
            "suggestion_text": suggestion.suggestion_text if suggestion else "",
            "awareness_rating": suggestion.awareness_rating if suggestion else "",
            "originality_rating": suggestion.originality_rating if suggestion else "",
            "week_2_executed": week_2.executed if week_2 else "",
            "week_2_result_change": week_2.result_change if week_2 else "",
            "week_4_executed": week_4.executed if week_4 else "",
            "week_4_result_change": week_4.result_change if week_4 else "",
        }
