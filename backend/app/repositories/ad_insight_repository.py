from sqlalchemy.orm import Session
from sqlalchemy import desc, and_, func
from typing import List, Optional, Dict, Any
from datetime import datetime
from app.models import AdInsight


class AdInsightRepository:
    """
    AdInsight の DB アクセス層
    
    Repository パターンを用いて、DB 操作を統一インターフェース化。
    エンドポイント層からは直接 DB にアクセスせず、このクラスを経由する。
    """
    
    def __init__(self, db: Session):
        """
        Args:
            db: SQLAlchemy Session インスタンス
        """
        self.db = db
    
    # ===== CREATE =====
    
    def create(
        self,
        asset_id: str,
        format: str,
        spec_data: Dict[str, Any],
        version: Optional[int] = None
    ) -> AdInsight:
        """
        新しい AdInsight レコードを作成
        
        Args:
            asset_id: 素材 ID
            format: フォーマット（video_static など）
            spec_data: ad_insight_spec v0.2 全体（dict）
            version: 指定がない場合は自動インクリメントされる
        
        Returns:
            作成されたレコード
        
        Raises:
            Exception: 同一 (asset_id, version) が既に存在する場合
        """
        if version is None:
            max_version = self.db.query(func.max(AdInsight.version)).filter(
                AdInsight.asset_id == asset_id
            ).scalar()
            version = (max_version or 0) + 1
        # 同一バージョンが既に存在するかチェック
        existing = self.db.query(AdInsight).filter(
            and_(
                AdInsight.asset_id == asset_id,
                AdInsight.version == version,
                AdInsight.is_deleted == False
            )
        ).first()
        
        if existing:
            raise ValueError(f"AdInsight with asset_id={asset_id}, version={version} already exists")
        
        # 新規レコード作成
        db_record = AdInsight(
            asset_id=asset_id,
            version=version,
            format=format,
            spec_data=spec_data,
            is_deleted=False
        )
        self.db.add(db_record)
        self.db.commit()
        self.db.refresh(db_record)
        return db_record
    
    # ===== READ =====
    
    def get_by_id(self, id: int) -> Optional[AdInsight]:
        """
        ID でレコード取得
        
        Args:
            id: レコード ID
        
        Returns:
            レコード、または None
        """
        return self.db.query(AdInsight).filter(
            AdInsight.id == id,
            AdInsight.is_deleted == False
        ).first()
    
    def get_latest_by_asset_id(self, asset_id: str) -> Optional[AdInsight]:
        """
        asset_id の最新バージョンレコードを取得
        
        Args:
            asset_id: 素材 ID
        
        Returns:
            最新バージョンレコード、または None
        """
        return self.db.query(AdInsight).filter(
            AdInsight.asset_id == asset_id,
            AdInsight.is_deleted == False
        ).order_by(desc(AdInsight.version)).first()
    
    def get_all_versions_by_asset_id(self, asset_id: str) -> List[AdInsight]:
        """
        asset_id のすべてのバージョンレコードを取得
        
        Args:
            asset_id: 素材 ID
        
        Returns:
            バージョン降順のレコード一覧
        """
        return self.db.query(AdInsight).filter(
            AdInsight.asset_id == asset_id,
            AdInsight.is_deleted == False
        ).order_by(desc(AdInsight.version)).all()
    
    def list_active(
        self,
        skip: int = 0,
        limit: int = 10,
        format_filter: Optional[str] = None,
        asset_id_filter: Optional[str] = None
    ) -> tuple[List[AdInsight], int]:
        """
        有効なレコードの一覧取得（ページング + フィルタリング対応、全バージョン込み）

        Args:
            skip: スキップ件数（ページング）
            limit: 取得件数上限
            format_filter: フォーマットでフィルタ（オプション）
            asset_id_filter: asset_id でフィルタ（オプション）

        Returns:
            (レコード一覧, 全体件数)
        """
        query = self.db.query(AdInsight).filter(AdInsight.is_deleted == False)

        # フィルタ適用
        if format_filter:
            query = query.filter(AdInsight.format == format_filter)
        if asset_id_filter:
            query = query.filter(AdInsight.asset_id.like(f"%{asset_id_filter}%"))

        # 全体件数
        total_count = query.count()

        # ページング
        records = query.order_by(desc(AdInsight.created_at)).offset(skip).limit(limit).all()

        return records, total_count

    def list_latest_per_asset(
        self,
        skip: int = 0,
        limit: int = 10,
        format_filter: Optional[str] = None,
        asset_id_filter: Optional[str] = None
    ) -> tuple[List[AdInsight], int]:
        """
        asset_id ごとの最新バージョンのみの一覧取得（ページング + フィルタリング対応）

        一覧APIのデフォルト挙動用。同一 asset_id の旧バージョンは含めない。

        Args:
            skip: スキップ件数（ページング）
            limit: 取得件数上限
            format_filter: フォーマットでフィルタ（オプション）
            asset_id_filter: asset_id でフィルタ（オプション）

        Returns:
            (レコード一覧, 全体件数（asset_id のユニーク数）)
        """
        latest_version_subq = (
            self.db.query(
                AdInsight.asset_id.label("asset_id"),
                func.max(AdInsight.version).label("max_version"),
            )
            .filter(AdInsight.is_deleted == False)
            .group_by(AdInsight.asset_id)
            .subquery()
        )

        query = self.db.query(AdInsight).join(
            latest_version_subq,
            and_(
                AdInsight.asset_id == latest_version_subq.c.asset_id,
                AdInsight.version == latest_version_subq.c.max_version,
            ),
        ).filter(AdInsight.is_deleted == False)

        # フィルタ適用
        if format_filter:
            query = query.filter(AdInsight.format == format_filter)
        if asset_id_filter:
            query = query.filter(AdInsight.asset_id.like(f"%{asset_id_filter}%"))

        # 全体件数（asset_id のユニーク数）
        total_count = query.count()

        # ページング
        records = query.order_by(desc(AdInsight.created_at)).offset(skip).limit(limit).all()

        return records, total_count
    
    # ===== UPDATE =====
    
    def update_spec_data(
        self,
        id: int,
        new_spec_data: Dict[str, Any]
    ) -> Optional[AdInsight]:
        """
        spec_data を更新
        
        Args:
            id: レコード ID
            new_spec_data: 新しい spec_data（dict）
        
        Returns:
            更新されたレコード、または None
        """
        db_record = self.get_by_id(id)
        if not db_record:
            return None
        
        db_record.spec_data = new_spec_data
        db_record.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(db_record)
        return db_record
    
    # ===== DELETE (Logical) =====
    
    def delete_logical(self, id: int) -> bool:
        """
        論理削除（is_deleted = True に設定）
        
        Args:
            id: レコード ID
        
        Returns:
            削除成功時 True、レコードなし時 False
        """
        db_record = self.db.query(AdInsight).filter(AdInsight.id == id).first()
        if not db_record:
            return False
        
        db_record.is_deleted = True
        db_record.deleted_at = datetime.utcnow()
        self.db.commit()
        return True
    
    def delete_logical_by_asset_id(self, asset_id: str) -> int:
        """
        asset_id の全バージョンを論理削除
        
        Args:
            asset_id: 素材 ID
        
        Returns:
            削除したレコード数
        """
        now = datetime.utcnow()
        deleted_count = self.db.query(AdInsight).filter(
            AdInsight.asset_id == asset_id,
            AdInsight.is_deleted == False
        ).update(
            {AdInsight.is_deleted: True, AdInsight.deleted_at: now},
            synchronize_session=False
        )
        self.db.commit()
        return deleted_count
