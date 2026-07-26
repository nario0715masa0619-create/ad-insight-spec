import csv
import io
import json
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session
from typing import Dict, Any

from app.db.session import get_db
from app.repositories import VerificationRepository
from app.schemas.verification import (
    VerificationCaseCreate,
    PresentationEvaluationUpdate,
    VerificationCaseSummary,
    VerificationCaseDetail,
    SuggestionEvaluationCreate,
    SuggestionEvaluationUpdate,
    SuggestionEvaluationResponse,
    FollowupUpsert,
    FollowupResponse,
)

from app.utils.error_handler import create_error_response
from app.utils.logging import request_id_var, trace_id_var, get_logger

logger = get_logger(__name__)

# ===== ルーター定義 =====
# CampaignPilotの提案がMeta Ads Managerだけでは出にくい新規の原因特定・改善案を
# 生んでいるかを記録するための検証機能。ad_insight_spec本体（/api/v1/specs）とは
# 完全に独立しており、既存の分析APIロジックには一切手を入れない。

router = APIRouter(
    prefix="/api/v1/verification",
    tags=["Verification"],
    responses={404: {"description": "Not found"}},
)


# ===== VerificationCase =====

@router.post("/cases", response_model=VerificationCaseDetail, tags=["Verification"])
async def create_case(payload: VerificationCaseCreate, db: Session = Depends(get_db)) -> VerificationCaseDetail:
    """案件を作成し、事前ヒアリング内容を保存する"""
    try:
        repo = VerificationRepository(db)
        record = repo.create_case(
            case_name=payload.case_name,
            asset_id=payload.asset_id,
            asset_version=payload.asset_version,
            pre_hearing_notes=payload.pre_hearing_notes,
        )
        logger.info(
            "Verification case created",
            extra={"case_id": record.id, "request_id": request_id_var.get(), "trace_id": trace_id_var.get()},
        )
        return VerificationCaseDetail(**_case_to_detail_dict(record, suggestions=[]))
    except Exception as e:
        logger.error(f"Create verification case error: {str(e)}")
        error_response, status_code = create_error_response(
            error_message="Failed to create verification case",
            error_code="VERIFICATION_CREATE_ERROR",
            status_code=500,
        )
        raise HTTPException(status_code=status_code, detail=error_response)


@router.get("/cases", response_model=Dict[str, Any], tags=["Verification"])
async def list_cases(
    skip: int = Query(0, ge=0, description="スキップ件数"),
    limit: int = Query(10, ge=1, le=100, description="取得件数上限"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """検証案件の一覧取得（ページング対応）"""
    try:
        repo = VerificationRepository(db)
        records, total_count = repo.list_cases(skip=skip, limit=limit)
        counts = repo.count_suggestions_by_case([r.id for r in records])

        items = [
            VerificationCaseSummary(
                id=r.id,
                case_name=r.case_name,
                asset_id=r.asset_id,
                asset_version=r.asset_version,
                created_at=r.created_at,
                updated_at=r.updated_at,
                suggestion_count=counts.get(r.id, 0),
            )
            for r in records
        ]
        return {
            "items": [i.model_dump(mode="json") for i in items],
            "total": total_count,
            "skip": skip,
            "limit": limit,
        }
    except Exception as e:
        logger.error(f"List verification cases error: {str(e)}")
        error_response, status_code = create_error_response(
            error_message="Failed to fetch verification cases",
            error_code="VERIFICATION_FETCH_ERROR",
            status_code=500,
        )
        raise HTTPException(status_code=status_code, detail=error_response)


@router.get("/cases/{case_id}", response_model=VerificationCaseDetail, tags=["Verification"])
async def get_case(case_id: int, db: Session = Depends(get_db)) -> VerificationCaseDetail:
    """案件の個別参照（事前ヒアリング内容、提示後評価、提案評価とフォローアップを含む）"""
    try:
        repo = VerificationRepository(db)
        record = repo.get_case(case_id)
        if not record:
            raise HTTPException(status_code=404, detail="Verification case not found")

        suggestions = repo.list_suggestion_evaluations(case_id)
        return VerificationCaseDetail(**_case_to_detail_dict(record, suggestions, repo))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get verification case error: {str(e)}")
        error_response, status_code = create_error_response(
            error_message="Failed to fetch verification case",
            error_code="VERIFICATION_FETCH_ERROR",
            status_code=500,
        )
        raise HTTPException(status_code=status_code, detail=error_response)


@router.patch("/cases/{case_id}/presentation-evaluation", response_model=VerificationCaseDetail, tags=["Verification"])
async def update_presentation_evaluation(
    case_id: int, payload: PresentationEvaluationUpdate, db: Session = Depends(get_db)
) -> VerificationCaseDetail:
    """CampaignPilot提示後の評価を保存する"""
    try:
        repo = VerificationRepository(db)
        record = repo.update_presentation_evaluation(case_id, payload.presentation_evaluation)
        if not record:
            raise HTTPException(status_code=404, detail="Verification case not found")

        suggestions = repo.list_suggestion_evaluations(case_id)
        return VerificationCaseDetail(**_case_to_detail_dict(record, suggestions, repo))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update presentation evaluation error: {str(e)}")
        error_response, status_code = create_error_response(
            error_message="Failed to update presentation evaluation",
            error_code="VERIFICATION_UPDATE_ERROR",
            status_code=500,
        )
        raise HTTPException(status_code=status_code, detail=error_response)


# ===== SuggestionEvaluation =====

@router.post("/cases/{case_id}/suggestions", response_model=SuggestionEvaluationResponse, tags=["Verification"])
async def add_suggestion_evaluation(
    case_id: int, payload: SuggestionEvaluationCreate, db: Session = Depends(get_db)
) -> SuggestionEvaluationResponse:
    """
    提案に対する評価を追加する。
    「既に気づいていた/言われて初めて気づいた/妥当性に疑問/判断不能」と
    「自分でも出していた/自分では先に出せなかった/一般論/実行しにくい/不要」を記録する。
    """
    try:
        repo = VerificationRepository(db)
        record = repo.add_suggestion_evaluation(
            case_id=case_id,
            suggestion_key=payload.suggestion_key,
            suggestion_text=payload.suggestion_text,
            awareness_rating=payload.awareness_rating,
            originality_rating=payload.originality_rating,
        )
        if not record:
            raise HTTPException(status_code=404, detail="Verification case not found")
        return SuggestionEvaluationResponse(**_suggestion_to_dict(record, followups=[]))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Add suggestion evaluation error: {str(e)}")
        error_response, status_code = create_error_response(
            error_message="Failed to add suggestion evaluation",
            error_code="VERIFICATION_CREATE_ERROR",
            status_code=500,
        )
        raise HTTPException(status_code=status_code, detail=error_response)


@router.patch(
    "/cases/{case_id}/suggestions/{suggestion_id}",
    response_model=SuggestionEvaluationResponse,
    tags=["Verification"],
)
async def update_suggestion_evaluation(
    case_id: int, suggestion_id: int, payload: SuggestionEvaluationUpdate, db: Session = Depends(get_db)
) -> SuggestionEvaluationResponse:
    """提案評価の修正"""
    try:
        repo = VerificationRepository(db)
        existing = repo.get_suggestion_evaluation(suggestion_id)
        if not existing or existing.case_id != case_id:
            raise HTTPException(status_code=404, detail="Suggestion evaluation not found")

        record = repo.update_suggestion_evaluation(
            suggestion_id,
            awareness_rating=payload.awareness_rating,
            originality_rating=payload.originality_rating,
        )
        followups = repo.list_followups(suggestion_id)
        return SuggestionEvaluationResponse(**_suggestion_to_dict(record, followups))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update suggestion evaluation error: {str(e)}")
        error_response, status_code = create_error_response(
            error_message="Failed to update suggestion evaluation",
            error_code="VERIFICATION_UPDATE_ERROR",
            status_code=500,
        )
        raise HTTPException(status_code=status_code, detail=error_response)


# ===== Followup =====

@router.put(
    "/suggestions/{suggestion_id}/followups/{checkpoint}",
    response_model=FollowupResponse,
    tags=["Verification"],
)
async def upsert_followup(
    suggestion_id: int, checkpoint: str, payload: FollowupUpsert, db: Session = Depends(get_db)
) -> FollowupResponse:
    """2週間後(week_2)・4週間後(week_4)の実行有無と成果変化を記録する（upsert）"""
    if checkpoint not in ("week_2", "week_4"):
        error_response, status_code = create_error_response(
            error_message="checkpoint must be 'week_2' or 'week_4'",
            error_code="VALIDATION_ERROR",
            status_code=400,
        )
        raise HTTPException(status_code=status_code, detail=error_response)

    try:
        repo = VerificationRepository(db)
        record = repo.upsert_followup(
            suggestion_evaluation_id=suggestion_id,
            checkpoint=checkpoint,
            executed=payload.executed,
            result_change=payload.result_change,
        )
        if not record:
            raise HTTPException(status_code=404, detail="Suggestion evaluation not found")
        return FollowupResponse.model_validate(record)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upsert followup error: {str(e)}")
        error_response, status_code = create_error_response(
            error_message="Failed to save followup",
            error_code="VERIFICATION_UPDATE_ERROR",
            status_code=500,
        )
        raise HTTPException(status_code=status_code, detail=error_response)


# ===== CSV export =====

_EXPORT_CSV_COLUMNS = [
    "case_id",
    "case_name",
    "asset_id",
    "asset_version",
    "case_created_at",
    "pre_hearing_notes",
    "presentation_evaluation",
    "suggestion_id",
    "suggestion_key",
    "suggestion_text",
    "awareness_rating",
    "originality_rating",
    "week_2_executed",
    "week_2_result_change",
    "week_4_executed",
    "week_4_result_change",
]


@router.get("/export.csv", tags=["Verification"])
async def export_csv(db: Session = Depends(get_db)) -> Response:
    """検証データ全件をCSVで出力する（案件 x 提案を1行に平坦化。JSON項目は文字列化して格納）"""
    try:
        repo = VerificationRepository(db)
        rows = repo.list_export_rows()

        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=_EXPORT_CSV_COLUMNS)
        writer.writeheader()
        for row in rows:
            csv_row = dict(row)
            for json_field in ("pre_hearing_notes", "presentation_evaluation"):
                value = csv_row.get(json_field)
                csv_row[json_field] = json.dumps(value, ensure_ascii=False) if value else ""
            writer.writerow(csv_row)

        csv_content = "﻿" + buffer.getvalue()  # Excelでの文字化け防止のためBOM付与
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=campaignpilot_verification.csv"},
        )
    except Exception as e:
        logger.error(f"Export verification CSV error: {str(e)}")
        error_response, status_code = create_error_response(
            error_message="Failed to export verification data",
            error_code="VERIFICATION_EXPORT_ERROR",
            status_code=500,
        )
        raise HTTPException(status_code=status_code, detail=error_response)


# ===== 内部ヘルパー =====

def _suggestion_to_dict(record, followups) -> Dict[str, Any]:
    return {
        "id": record.id,
        "case_id": record.case_id,
        "suggestion_key": record.suggestion_key,
        "suggestion_text": record.suggestion_text,
        "awareness_rating": record.awareness_rating,
        "originality_rating": record.originality_rating,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "followups": [
            {
                "checkpoint": f.checkpoint,
                "executed": f.executed,
                "result_change": f.result_change,
                "recorded_at": f.recorded_at,
            }
            for f in followups
        ],
    }


def _case_to_detail_dict(case, suggestions, repo: "VerificationRepository | None" = None) -> Dict[str, Any]:
    suggestion_dicts = []
    for s in suggestions:
        followups = repo.list_followups(s.id) if repo else []
        suggestion_dicts.append(_suggestion_to_dict(s, followups))

    return {
        "id": case.id,
        "case_name": case.case_name,
        "asset_id": case.asset_id,
        "asset_version": case.asset_version,
        "pre_hearing_notes": case.pre_hearing_notes,
        "presentation_evaluation": case.presentation_evaluation,
        "created_at": case.created_at,
        "updated_at": case.updated_at,
        "suggestion_evaluations": suggestion_dicts,
    }
