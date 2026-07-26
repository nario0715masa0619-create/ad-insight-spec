import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models import VerificationCase, VerificationSuggestionEvaluation, VerificationFollowup  # noqa: F401
from app.repositories.verification_repository import VerificationRepository

# SQLite インメモリ DB（test_repositories.py と同じパターン）
engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db_session():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


def test_create_case_stores_pre_hearing_notes(db_session):
    repo = VerificationRepository(db_session)
    case = repo.create_case(
        case_name="株式会社サンプル",
        asset_id="asset_0001",
        asset_version=3,
        pre_hearing_notes={"industry": "EC", "current_issue": "CVR低下"},
    )
    assert case.id is not None
    assert case.asset_version == 3
    assert case.pre_hearing_notes == {"industry": "EC", "current_issue": "CVR低下"}

    fetched = repo.get_case(case.id)
    assert fetched.case_name == "株式会社サンプル"


def test_create_case_with_asset_id_requires_asset_version(db_session):
    """asset_idのみでasset_versionを渡さない場合、DBのCHECK制約で拒否される（防御的な安全網）"""
    from sqlalchemy.exc import IntegrityError

    repo = VerificationRepository(db_session)
    with pytest.raises(IntegrityError):
        repo.create_case(
            case_name="asset_version欠落案件",
            asset_id="asset_missing_version",
            asset_version=None,
            pre_hearing_notes=None,
        )
    db_session.rollback()


def test_update_presentation_evaluation(db_session):
    repo = VerificationRepository(db_session)
    case = repo.create_case(case_name="案件A", asset_id=None, asset_version=None, pre_hearing_notes=None)

    updated = repo.update_presentation_evaluation(case.id, {"usefulness": "high"})
    assert updated.presentation_evaluation == {"usefulness": "high"}

    assert repo.update_presentation_evaluation(999999, {"x": 1}) is None


def test_add_suggestion_evaluation_requires_existing_case(db_session):
    repo = VerificationRepository(db_session)
    assert repo.add_suggestion_evaluation(
        case_id=999999,
        suggestion_key="does not matter",
        suggestion_text=None,
        awareness_rating="already_knew",
        originality_rating="generic",
    ) is None

    case = repo.create_case(case_name="案件B", asset_id=None, asset_version=None, pre_hearing_notes=None)
    suggestion = repo.add_suggestion_evaluation(
        case_id=case.id,
        suggestion_key="LPのCTAを変更",
        suggestion_text="CTAボタンの文言を変更する提案",
        awareness_rating="realized_when_told",
        originality_rating="could_not_have_suggested_myself",
    )
    assert suggestion.id is not None
    assert suggestion.case_id == case.id

    evaluations = repo.list_suggestion_evaluations(case.id)
    assert len(evaluations) == 1
    assert evaluations[0].suggestion_key == "LPのCTAを変更"


def test_update_suggestion_evaluation_partial(db_session):
    repo = VerificationRepository(db_session)
    case = repo.create_case(case_name="案件C", asset_id=None, asset_version=None, pre_hearing_notes=None)
    suggestion = repo.add_suggestion_evaluation(
        case_id=case.id,
        suggestion_key="広告クリエイティブの差し替え",
        suggestion_text=None,
        awareness_rating="already_knew",
        originality_rating="generic",
    )

    updated = repo.update_suggestion_evaluation(suggestion.id, awareness_rating="cannot_judge")
    assert updated.awareness_rating == "cannot_judge"
    assert updated.originality_rating == "generic"  # 変更していない側は維持される


def test_upsert_followup_creates_then_updates(db_session):
    repo = VerificationRepository(db_session)
    case = repo.create_case(case_name="案件D", asset_id=None, asset_version=None, pre_hearing_notes=None)
    suggestion = repo.add_suggestion_evaluation(
        case_id=case.id,
        suggestion_key="ターゲティング見直し",
        suggestion_text=None,
        awareness_rating="already_knew",
        originality_rating="generic",
    )

    # 存在しない suggestion への upsert は None
    assert repo.upsert_followup(999999, "week_2", executed=True, result_change="x") is None

    created = repo.upsert_followup(suggestion.id, "week_2", executed=False, result_change="未実施")
    assert created.executed is False

    updated = repo.upsert_followup(suggestion.id, "week_2", executed=True, result_change="実施しCPA改善")
    assert updated.id == created.id  # 同じレコードが更新される（upsert）
    assert updated.executed is True
    assert updated.result_change == "実施しCPA改善"

    followups = repo.list_followups(suggestion.id)
    assert len(followups) == 1


def test_list_export_rows_flattens_case_suggestion_followups(db_session):
    repo = VerificationRepository(db_session)

    # 提案評価が1件も無い案件
    empty_case = repo.create_case(case_name="提案なし案件", asset_id=None, asset_version=None, pre_hearing_notes=None)

    # 提案評価とフォローアップがある案件
    case = repo.create_case(
        case_name="フル案件", asset_id="asset_0002", asset_version=5, pre_hearing_notes={"note": "hearing"}
    )
    suggestion = repo.add_suggestion_evaluation(
        case_id=case.id,
        suggestion_key="配信面の見直し",
        suggestion_text="Audience Networkを除外する提案",
        awareness_rating="realized_when_told",
        originality_rating="could_not_have_suggested_myself",
    )
    repo.upsert_followup(suggestion.id, "week_2", executed=True, result_change="CPA 10%改善")
    repo.upsert_followup(suggestion.id, "week_4", executed=True, result_change="CPA 15%改善")

    rows = repo.list_export_rows()
    assert len(rows) == 2

    empty_row = next(r for r in rows if r["case_id"] == empty_case.id)
    assert empty_row["suggestion_id"] == ""

    full_row = next(r for r in rows if r["case_id"] == case.id)
    assert full_row["asset_version"] == 5
    assert full_row["suggestion_key"] == "配信面の見直し"
    assert full_row["week_2_result_change"] == "CPA 10%改善"
    assert full_row["week_4_result_change"] == "CPA 15%改善"
