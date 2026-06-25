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
