import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime

from app.db.base import Base
from app.models.ad_insight import AdInsight
from app.repositories.ad_insight_repository import AdInsightRepository

# SQLite インメモリ DB
engine = create_engine(
    "sqlite:///:memory:", connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="function")
def db_session():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)

def test_create_auto_increment_version(db_session):
    repo = AdInsightRepository(db_session)
    asset_id = "asset_unknown_a1b2c3d4"
    spec_data = {"key": "value"}
    
    # 1回目の登録 (version 1になるはず)
    record1 = repo.create(asset_id=asset_id, format="image_static", spec_data=spec_data)
    assert record1.version == 1
    
    # 2回目の登録 (version 2になるはず)
    record2 = repo.create(asset_id=asset_id, format="image_static", spec_data=spec_data)
    assert record2.version == 2

def test_create_leaves_asset_evaluation_data_columns_null(db_session):
    """
    Phase 1で追加したasset_data/evaluation_dataカラムは、dual-writeが未実装の
    現時点では常にNULLのままであること（create()のシグネチャ・挙動は無変更）。
    """
    repo = AdInsightRepository(db_session)
    record = repo.create(asset_id="asset_unknown_phase1_cols", format="image_static", spec_data={"key": "value"})
    assert record.asset_data is None
    assert record.evaluation_data is None


def test_create_auto_increment_version_with_deleted(db_session):
    repo = AdInsightRepository(db_session)
    asset_id = "asset_unknown_a1b2c3d4"
    spec_data = {"key": "value"}

    # 1回目の登録 (version 1)
    record1 = repo.create(asset_id=asset_id, format="image_static", spec_data=spec_data)

    # 削除する (is_deleted = True)
    repo.delete_logical(record1.id)

    # 削除済みでも2回目の登録は version 2になるはず
    record2 = repo.create(asset_id=asset_id, format="image_static", spec_data=spec_data)
    assert record2.version == 2


def test_list_latest_per_asset_returns_only_latest_version(db_session):
    repo = AdInsightRepository(db_session)
    asset_id = "asset_unknown_multi_version"

    repo.create(asset_id=asset_id, format="image_static", spec_data={"v": 1})
    repo.create(asset_id=asset_id, format="image_static", spec_data={"v": 2})
    repo.create(asset_id=asset_id, format="image_static", spec_data={"v": 3})

    # 別 asset_id (バージョン1件のみ)
    other_asset_id = "asset_unknown_single_version"
    repo.create(asset_id=other_asset_id, format="video_static", spec_data={"v": 1})

    records, total = repo.list_latest_per_asset(skip=0, limit=10)

    # asset_id ごとに1件（= 2件）だけ返り、multi_version は最新の v3 であること
    assert total == 2
    by_asset_id = {rec.asset_id: rec for rec in records}
    assert by_asset_id[asset_id].version == 3
    assert by_asset_id[asset_id].spec_data == {"v": 3}
    assert by_asset_id[other_asset_id].version == 1


def test_list_active_returns_all_versions(db_session):
    repo = AdInsightRepository(db_session)
    asset_id = "asset_unknown_history"

    repo.create(asset_id=asset_id, format="image_static", spec_data={"v": 1})
    repo.create(asset_id=asset_id, format="image_static", spec_data={"v": 2})

    records, total = repo.list_active(skip=0, limit=10)

    # include_all_versions=true 相当の従来挙動: 全バージョンを返す
    assert total == 2
    assert sorted(rec.version for rec in records) == [1, 2]


def test_list_latest_per_asset_excludes_deleted(db_session):
    repo = AdInsightRepository(db_session)
    asset_id = "asset_unknown_deleted_latest"

    record1 = repo.create(asset_id=asset_id, format="image_static", spec_data={"v": 1})
    record2 = repo.create(asset_id=asset_id, format="image_static", spec_data={"v": 2})

    # 最新版 (v2) だけ削除された場合、v1 が「最新の有効版」として返るべき
    repo.delete_logical(record2.id)

    records, total = repo.list_latest_per_asset(skip=0, limit=10)
    assert total == 1
    assert records[0].version == 1
