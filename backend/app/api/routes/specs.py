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


# ===== エンドポイント =====

@router.post("/analyze", response_model=Dict[str, Any], tags=["Analysis"])
async def analyze(
    input_file: UploadFile = File(...),
    lp_file: Optional[UploadFile] = None,
    kpi_file: Optional[UploadFile] = None,
    mode: str = Form("file_plus_lp_plus_manual_kpi"),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    ファイルをアップロードして分析を実行
    
    **入力**:
    - `input_file`: 素材ファイル（image/video/text）[必須]
    - `lp_file`: LP ファイル（HTML） [オプション]
    - `kpi_file`: KPI ファイル（JSON） [オプション]
    - `mode`: 入力モード [デフォルト: file_plus_lp_plus_manual_kpi]
    
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
                "filename": input_file.filename,
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
            
            # === Orchestrator で分析実行 ===
            orchestrator = AnalysisOrchestrator(
                input_path=str(input_path),
                lp_input=str(lp_path) if lp_path else None,
                kpi_path=str(kpi_path) if kpi_path else None,
                mode=mode
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
            
            # DB に保存
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
            
            return spec_data_jsonable
        
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
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    分析結果一覧取得（フィルタリング・ページング対応）
    
    **クエリパラメータ**:
    - `skip`: スキップ件数（ページング）
    - `limit`: 取得件数上限（1～100）
    - `asset_id`: asset_id でフィルタ
    - `format`: format でフィルタ
    
    **出力**:
    - `items`: レコード一覧
    - `total`: 全体件数
    - `skip`: スキップ件数
    - `limit`: 取得件数
    """
    try:
        logger.info(
            "Fetching specs list",
            extra={"skip": skip, "limit": limit, "request_id": request_id_var.get(), "trace_id": trace_id_var.get()}
        )
        
        repo = AdInsightRepository(db)
        records, total_count = repo.list_active(
            skip=skip,
            limit=limit,
            format_filter=format,
            asset_id_filter=asset_id
        )
        
        return {
            "items": [rec.spec_data for rec in records],
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
        
        return record.spec_data
    
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
