from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import datetime
import tempfile
import shutil
import re
from pathlib import Path

from app.db.session import get_db
from app.repositories import AdInsightRepository
from app.models import AdInsight
from app.schemas.ad_insight import AdInsightSpec
from app.services.analysis_orchestrator import AnalysisOrchestrator
from app.services.asset_evaluation_adapter import resolve_spec_data

from app.utils.error_handler import create_error_response, ErrorResponse
from app.utils.logging import request_id_var, trace_id_var, get_logger

logger = get_logger(__name__)

# ===== ルーター定義 =====

router = APIRouter(
    prefix="/api/v1/specs",
    tags=["Specs"],
    responses={404: {"description": "Not found"}}
)


# ===== Pydantic レスポンスモデル =====

class AdInsightResponse(dict):
    """
    AdInsight レスポンス型
    
    JSON spec_data をそのまま返す
    """
    pass


class ListResponse(dict):
    """
    一覧レスポンス型
    """
    pass


# ===== 前回分析との差分（decision_support_diff）計算 =====
# axes 構造導入前の旧データとの比較や、直前バージョンが存在しない場合は
# fail-soft で None を返す（詳細画面はこの場合、差分セクションを表示しないだけで済む）。

_RANK_ORDER = {"D": 0, "C": 1, "B": 2, "A": 3}


def _build_decision_support_diff(
    current_decision_support: Optional[Dict[str, Any]],
    previous_record: Optional[AdInsight],
) -> Optional[Dict[str, Any]]:
    if not previous_record or not current_decision_support:
        return None
    if not isinstance(current_decision_support, dict) or "axes" not in current_decision_support:
        return None

    previous_decision_support = (
        previous_record.spec_data.get("diagnostics", {}) or {}
    ).get("decision_support")
    if not isinstance(previous_decision_support, dict) or "axes" not in previous_decision_support:
        return None

    previous_axes_by_id = {a.get("axis"): a for a in previous_decision_support.get("axes", [])}
    axis_deltas = []
    for axis in current_decision_support.get("axes", []):
        axis_id = axis.get("axis")
        previous_axis = previous_axes_by_id.get(axis_id)
        if not previous_axis:
            continue
        current_score = axis.get("score")
        previous_score = previous_axis.get("score")
        if current_score is None or previous_score is None:
            continue
        axis_deltas.append({
            "axis": axis_id,
            "axis_label": axis.get("axis_label", axis_id),
            "previous_score": previous_score,
            "current_score": current_score,
            "delta": current_score - previous_score,
        })

    previous_rank = previous_decision_support.get("overall_rank")
    current_rank = current_decision_support.get("overall_rank")
    rank_delta = None
    if previous_rank in _RANK_ORDER and current_rank in _RANK_ORDER:
        rank_delta = _RANK_ORDER[current_rank] - _RANK_ORDER[previous_rank]

    return {
        "previous_version": previous_record.version,
        "previous_overall_rank": previous_rank,
        "overall_rank_delta": rank_delta,
        "previous_headline": (previous_decision_support.get("summary") or {}).get("headline"),
        "axis_deltas": axis_deltas,
    }


# ===== エンドポイント =====

@router.post("/analyze", response_model=Dict[str, Any], tags=["Analysis"])
async def analyze(
    input_file: UploadFile = File(...),
    lp_file: Optional[UploadFile] = None,
    kpi_file: Optional[UploadFile] = None,
    mode: str = Form("file_plus_lp_plus_manual_kpi"),
    asset_name: Optional[str] = Form(None),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    ファイルをアップロードして分析を実行

    **入力**:
    - `input_file`: 素材ファイル（image/video/text）[必須]
    - `lp_file`: LP ファイル（HTML） [オプション]
    - `kpi_file`: KPI ファイル（JSON） [オプション]
    - `mode`: 入力モード [デフォルト: file_plus_lp_plus_manual_kpi]
    - `asset_name`: 広告名/キャンペーン名 [オプション、未指定時はアップロードファイル名にフォールバック]
    
    **出力**:
    - `ad_insight_spec v0.2` JSON オブジェクト
    
    **エラー**:
    - 400: 入力ファイル形式エラー
    - 500: 分析エラー
    """
    try:
        logger.info(
            "Analysis started",
            extra={
                # "filename" は logging.LogRecord の予約属性名と衝突し、
                # ハンドラ処理時に "Attempt to overwrite 'filename' in
                # LogRecord" で落ちるため使わない（実機で確認済み）。
                "uploaded_filename": input_file.filename,
                "mode": mode,
                "request_id": request_id_var.get(),
                "trace_id": trace_id_var.get()
            }
        )
        
        # === ファイル一時保存 ===
        temp_dir = tempfile.mkdtemp()
        input_path = None
        lp_path = None
        kpi_path = None
        
        try:
            # input_file 保存
            input_path = Path(temp_dir) / input_file.filename
            with open(input_path, "wb") as f:
                content = await input_file.read()
                f.write(content)
            
            # lp_file 保存（オプション）
            if lp_file:
                lp_path = Path(temp_dir) / lp_file.filename
                with open(lp_path, "wb") as f:
                    content = await lp_file.read()
                    f.write(content)
            
            # kpi_file 保存（オプション）
            if kpi_file:
                kpi_path = Path(temp_dir) / kpi_file.filename
                with open(kpi_path, "wb") as f:
                    content = await kpi_file.read()
                    f.write(content)
            
            # asset_name 未指定時は、アップロードファイル名（拡張子除く）にフォールバックする
            resolved_asset_name = asset_name or Path(input_file.filename).stem

            # === Orchestrator で分析実行 ===
            orchestrator = AnalysisOrchestrator(
                input_path=str(input_path),
                lp_input=str(lp_path) if lp_path else None,
                kpi_path=str(kpi_path) if kpi_path else None,
                mode=mode,
                asset_name=resolved_asset_name,
            )

            spec_dict = orchestrator.run()
            
            # Pydantic 検証
            spec = AdInsightSpec(**spec_dict)
            
            # === DB 保存 ===
            repo = AdInsightRepository(db)
            asset_id = spec.asset_meta.asset_id
            
            import json
            if hasattr(spec, "model_dump"):
                spec_data_jsonable = spec.model_dump(mode="json")
            else:
                spec_data_jsonable = json.loads(spec.json())
            
            # DB に保存（spec_data のみ。asset_data/evaluation_dataのdual-writeは
            # まだ実施しない＝DB保存挙動はP1のスコープ外で変更していない）
            db_record = repo.create(
                asset_id=asset_id,
                format=spec.creative_core.format,
                spec_data=spec_data_jsonable
            )

            logger.info(
                "Analysis completed successfully",
                extra={
                    "request_id": request_id_var.get(),
                    "trace_id": trace_id_var.get()
                }
            )

            # 前回バージョンとの decision_support 差分（新形式同士の場合のみ、fail-soft）
            previous_record = repo.get_previous_version(asset_id, db_record.version)
            current_decision_support = (spec_data_jsonable.get("diagnostics", {}) or {}).get("decision_support")
            decision_support_diff = _build_decision_support_diff(current_decision_support, previous_record)
            if decision_support_diff:
                spec_data_jsonable.setdefault("diagnostics", {})["decision_support_diff"] = decision_support_diff

            # asset_data/evaluation_data (v0) はDBには保存しないが、生成ロジック
            # (ConverterService._build_asset_evaluation_v0) の結果をAPIレスポンスには
            # 含める。AdInsightSpec は未知フィールドを無視するため、spec_data_jsonable
            # 側（spec経由）には含まれない。元の spec_dict から直接取り出す。
            # decision_support_diff の注入より後で取り出すのは、レスポンス内の
            # evaluation_data.diagnostics と 直下の diagnostics（legacy）とで
            # decision_support_diff の有無が食い違わないようにするため
            # （PR #73 レビュー指摘: evaluation_data.diagnostics だけ古い内容の
            # まま返っていた）。
            asset_data = spec_dict.get("asset_data")
            evaluation_data = spec_dict.get("evaluation_data")
            if evaluation_data and decision_support_diff:
                evaluation_data.setdefault("diagnostics", {})["decision_support_diff"] = decision_support_diff

            # UI 側で「この場で作成した版」を selected_version として保持できるよう、
            # DB 確定後の version をレスポンスに追加する（スキーマ本体には存在しない値なので追加のみ・破壊的変更ではない）
            return {
                **spec_data_jsonable,
                "version": db_record.version,
                "created_at": db_record.created_at.isoformat(),
                "asset_data": asset_data,
                "evaluation_data": evaluation_data,
            }
        
        finally:
            # 一時ファイル削除
            shutil.rmtree(temp_dir, ignore_errors=True)
            
    except ValueError as e:
        logger.error(f"Validation error: {str(e)}")
        error_response, status_code = create_error_response(
            error_message=str(e),
            error_code="VALIDATION_ERROR",
            status_code=400
        )
        raise HTTPException(status_code=status_code, detail=error_response)
    
    except Exception as e:
        logger.error(f"Analysis error: {str(e)}")
        exc_str = str(e)
        input_shortage_match = re.search(r"(\w+) is required in (\w+) mode", exc_str)
        if input_shortage_match:
            field_label_map = {
                "landing_page": "LP情報（ランディングページ）",
                "performance": "KPI情報（インプレッション数・クリック数などの実績データ）",
            }
            field_key = input_shortage_match.group(1)
            mode_name = input_shortage_match.group(2)
            field_label = field_label_map.get(field_key, field_key)
            error_response, status_code = create_error_response(
                error_message=(
                    f"分析に必要な情報が不足しています。選択したモード「{mode_name}」では"
                    f"{field_label}の入力が必須です。不足している情報を追加して再実行してください。"
                ),
                error_code="INSUFFICIENT_INPUT",
                status_code=422,
                details={"exception": exc_str}
            )
        else:
            error_response, status_code = create_error_response(
                error_message="Analysis failed",
                error_code="ANALYSIS_ERROR",
                status_code=500,
                details={"exception": exc_str}
            )
        raise HTTPException(status_code=status_code, detail=error_response)


@router.get("/", response_model=Dict[str, Any], tags=["List"])
async def list_specs(
    skip: int = Query(0, ge=0, description="スキップ件数"),
    limit: int = Query(10, ge=1, le=100, description="取得件数上限"),
    asset_id: Optional[str] = Query(None, description="asset_id フィルタ"),
    format: Optional[str] = Query(None, description="format フィルタ"),
    include_all_versions: bool = Query(
        False, description="true の場合、asset_id ごとの全バージョンを含めて返す（デフォルトは最新版のみ）"
    ),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    分析結果一覧取得（フィルタリング・ページング対応）

    デフォルトでは asset_id ごとの最新バージョンのみを返す（主フローの「保存済み結果」向け）。
    履歴が必要な場合は `include_all_versions=true` を指定する。

    **クエリパラメータ**:
    - `skip`: スキップ件数（ページング）
    - `limit`: 取得件数上限（1～100）
    - `asset_id`: asset_id でフィルタ
    - `format`: format でフィルタ
    - `include_all_versions`: true で全バージョンを含める（デフォルト: false、最新版のみ）

    **出力**:
    - `items`: レコード一覧
    - `total`: 全体件数
    - `skip`: スキップ件数
    - `limit`: 取得件数
    """
    try:
        logger.info(
            "Fetching specs list",
            extra={
                "skip": skip,
                "limit": limit,
                "include_all_versions": include_all_versions,
                "request_id": request_id_var.get(),
                "trace_id": trace_id_var.get(),
            }
        )

        repo = AdInsightRepository(db)
        list_fn = repo.list_active if include_all_versions else repo.list_latest_per_asset
        records, total_count = list_fn(
            skip=skip,
            limit=limit,
            format_filter=format,
            asset_id_filter=asset_id
        )

        # UI 側が一覧カードの版・分析日時をそのまま使えるよう、
        # 各 item に version / created_at を追加する（スキーマ本体には存在しない値なので追加のみ・破壊的変更ではない）
        # resolve_spec_data: asset_data/evaluation_dataは現状常にNULLのため、実質的には
        # rec.spec_data をそのまま返す（無変換）。将来dual-writeが始まった際の読み出し
        # 抽象化のための配線（docs/plans/asset_evaluation_split_phase2_tasks.md参照）。
        return {
            "items": [
                {
                    **resolve_spec_data(rec.spec_data, rec.asset_data, rec.evaluation_data),
                    "version": rec.version,
                    "created_at": rec.created_at.isoformat(),
                }
                for rec in records
            ],
            "total": total_count,
            "skip": skip,
            "limit": limit
        }

    except Exception as e:
        logger.error(f"List error: {str(e)}")
        error_response, status_code = create_error_response(
            error_message="Failed to fetch specs",
            error_code="FETCH_ERROR",
            status_code=500
        )
        raise HTTPException(status_code=status_code, detail=error_response)


@router.get("/{asset_id}", response_model=Dict[str, Any], tags=["Get"])
async def get_spec(
    asset_id: str,
    version: Optional[int] = Query(None, description="バージョン指定（未指定で最新）"),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    分析結果取得（asset_id 指定）
    
    **パラメータ**:
    - `asset_id`: 素材 ID
    - `version`: バージョン指定（オプション、未指定で最新版）
    
    **出力**:
    - `ad_insight_spec v0.2` JSON オブジェクト
    
    **エラー**:
    - 404: レコードなし
    """
    try:
        logger.info(
            f"Fetching spec: {asset_id}",
            extra={"asset_id": asset_id, "version": version, "request_id": request_id_var.get(), "trace_id": trace_id_var.get()}
        )
        
        repo = AdInsightRepository(db)
        
        # バージョン指定がある場合
        if version is not None:
            record = db.query(AdInsight).filter(
                AdInsight.asset_id == asset_id,
                AdInsight.version == version,
                AdInsight.is_deleted == False
            ).first()
        else:
            # バージョン指定がない場合は最新版
            record = repo.get_latest_by_asset_id(asset_id)
        
        if not record:
            raise HTTPException(status_code=404, detail="Record not found")

        # resolve_spec_data: asset_data/evaluation_dataは現状常にNULLのため、実質的には
        # record.spec_data をそのまま返す（無変換）。将来dual-writeが始まった際の読み出し
        # 抽象化のための配線（docs/plans/asset_evaluation_split_phase2_tasks.md参照）。
        resolved_spec_data = resolve_spec_data(record.spec_data, record.asset_data, record.evaluation_data)
        result = {**resolved_spec_data, "version": record.version, "created_at": record.created_at.isoformat()}

        # 前回バージョンとの decision_support 差分（新形式同士の場合のみ、fail-soft）。
        # record.spec_data はSQLAlchemyが追跡するライブオブジェクトなので、ネストした
        # diagnostics dict を直接 mutate せず、コピーしてから追加する。
        previous_record = repo.get_previous_version(asset_id, record.version)
        diagnostics = resolved_spec_data.get("diagnostics", {}) or {}
        decision_support_diff = _build_decision_support_diff(diagnostics.get("decision_support"), previous_record)
        if decision_support_diff:
            result["diagnostics"] = {**diagnostics, "decision_support_diff": decision_support_diff}

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get spec error: {str(e)}")
        error_response, status_code = create_error_response(
            error_message="Failed to fetch spec",
            error_code="FETCH_ERROR",
            status_code=500
        )
        raise HTTPException(status_code=status_code, detail=error_response)


@router.delete("/{asset_id}", response_model=Dict[str, str], tags=["Delete"])
async def delete_spec(
    asset_id: str,
    db: Session = Depends(get_db)
) -> Dict[str, str]:
    """
    分析結果削除（論理削除）
    
    **パラメータ**:
    - `asset_id`: 素材 ID
    
    **出力**:
    - `{"message": "Deleted successfully"}`
    
    **エラー**:
    - 404: レコードなし
    """
    try:
        logger.info(
            f"Deleting spec: {asset_id}",
            extra={"asset_id": asset_id, "request_id": request_id_var.get(), "trace_id": trace_id_var.get()}
        )
        
        repo = AdInsightRepository(db)
        deleted_count = repo.delete_logical_by_asset_id(asset_id)
        
        if deleted_count == 0:
            raise HTTPException(status_code=404, detail="Record not found")
        
        return {"message": f"Deleted {deleted_count} record(s) successfully"}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete spec error: {str(e)}")
        error_response, status_code = create_error_response(
            error_message="Failed to delete spec",
            error_code="DELETE_ERROR",
            status_code=500
        )
        raise HTTPException(status_code=status_code, detail=error_response)
