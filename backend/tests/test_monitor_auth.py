"""
招待制モニターベータのログイン/ログアウト/自分情報取得(/api/v1/auth/*)のテスト。

specs.router や verification.router と同様、auth.router だけをマウントした
最小のFastAPIアプリ + インメモリSQLiteで検証する。
"""
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.models import MonitorCompany, MonitorUser, MonitorSession
from app.api.routes import auth as auth_module
from app.core.security import hash_password, hash_session_token, DUMMY_PASSWORD_HASH

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def db_session():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(db_session):
    app = FastAPI()
    app.include_router(auth_module.router)

    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    return TestClient(app)


@pytest.fixture
def active_company(db_session):
    company = MonitorCompany(name="Acme Inc", slug="acme", monthly_credit_limit=10, is_active=True)
    db_session.add(company)
    db_session.commit()
    db_session.refresh(company)
    return company


@pytest.fixture
def active_user(db_session, active_company):
    user = MonitorUser(
        company_id=active_company.id,
        email="invited@acme.example",
        password_hash=hash_password("correct-horse"),
        is_active=True,
        is_admin=False,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


class TestLogin:
    def test_login_success_returns_session_token_and_usage(self, client, active_user):
        """招待済みユーザーは正しい資格情報でログインでき、利用状況も一緒に返る"""
        response = client.post(
            "/api/v1/auth/login", json={"email": active_user.email, "password": "correct-horse"}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["session_token"]
        assert body["email"] == active_user.email
        assert body["company"]["slug"] == "acme"
        assert body["usage"] == {"used": 0, "limit": 10, "remaining": 10, "limit_reached": False}

    def test_login_fails_for_unknown_email(self, client):
        """招待されていない(登録されていない)メールアドレスはログインできない"""
        response = client.post(
            "/api/v1/auth/login", json={"email": "nobody@example.com", "password": "whatever"}
        )
        assert response.status_code == 401
        # bareなFastAPI()にrouterだけをマウントしているため、main.pyのカスタム
        # StarletteHTTPExceptionハンドラ（detailをトップレベルへ展開する）を経由せず、
        # FastAPIのデフォルト挙動どおり detail の下にエラー情報が入る
        # （test_analyze_endpoint.pyのMetaAdsCsvErrorテストと同じ事情）。
        assert response.json()["detail"]["error_code"] == "INVALID_CREDENTIALS"

    def test_unknown_email_still_pays_password_verification_cost(self, client):
        """タイミング差によるメール列挙対策（レビュー指摘#1）:
        存在しないメールアドレスでログインを試みた場合でも、実在ユーザーの
        検証と同じ経路(verify_password)を、同じダミーハッシュに対して必ず
        通ることを確認する。厳密な時間計測ではなく、呼び出し経路そのものを
        検証することで安定したテストにする。"""
        with patch.object(auth_module, "verify_password", wraps=auth_module.verify_password) as spy:
            response = client.post(
                "/api/v1/auth/login", json={"email": "nobody@example.com", "password": "whatever"}
            )
        assert response.status_code == 401
        spy.assert_called_once_with("whatever", DUMMY_PASSWORD_HASH)

    def test_known_email_verifies_against_its_own_hash_not_dummy(self, client, active_user):
        """実在ユーザーの場合は、当然ながら本人のpassword_hashに対して検証されること
        （ダミーハッシュにすり替わっていないことの確認）。"""
        with patch.object(auth_module, "verify_password", wraps=auth_module.verify_password) as spy:
            client.post(
                "/api/v1/auth/login", json={"email": active_user.email, "password": "wrong-password"}
            )
        spy.assert_called_once_with("wrong-password", active_user.password_hash)

    def test_login_fails_for_wrong_password(self, client, active_user):
        response = client.post(
            "/api/v1/auth/login", json={"email": active_user.email, "password": "wrong-password"}
        )
        assert response.status_code == 401
        # bareなFastAPI()にrouterだけをマウントしているため、main.pyのカスタム
        # StarletteHTTPExceptionハンドラ（detailをトップレベルへ展開する）を経由せず、
        # FastAPIのデフォルト挙動どおり detail の下にエラー情報が入る
        # （test_analyze_endpoint.pyのMetaAdsCsvErrorテストと同じ事情）。
        assert response.json()["detail"]["error_code"] == "INVALID_CREDENTIALS"

    def test_login_fails_for_deactivated_user(self, client, db_session, active_user):
        active_user.is_active = False
        db_session.commit()

        response = client.post(
            "/api/v1/auth/login", json={"email": active_user.email, "password": "correct-horse"}
        )
        assert response.status_code == 401
        # 停止理由を外部に漏らさず、資格情報エラーと同一のコード/メッセージにする
        # bareなFastAPI()にrouterだけをマウントしているため、main.pyのカスタム
        # StarletteHTTPExceptionハンドラ（detailをトップレベルへ展開する）を経由せず、
        # FastAPIのデフォルト挙動どおり detail の下にエラー情報が入る
        # （test_analyze_endpoint.pyのMetaAdsCsvErrorテストと同じ事情）。
        assert response.json()["detail"]["error_code"] == "INVALID_CREDENTIALS"

    def test_login_fails_for_deactivated_company(self, client, db_session, active_company, active_user):
        active_company.is_active = False
        db_session.commit()

        response = client.post(
            "/api/v1/auth/login", json={"email": active_user.email, "password": "correct-horse"}
        )
        assert response.status_code == 401
        # bareなFastAPI()にrouterだけをマウントしているため、main.pyのカスタム
        # StarletteHTTPExceptionハンドラ（detailをトップレベルへ展開する）を経由せず、
        # FastAPIのデフォルト挙動どおり detail の下にエラー情報が入る
        # （test_analyze_endpoint.pyのMetaAdsCsvErrorテストと同じ事情）。
        assert response.json()["detail"]["error_code"] == "INVALID_CREDENTIALS"


class TestMeAndLogout:
    def test_me_requires_valid_session(self, client):
        """未ログイン(トークン無し)では /me は401"""
        response = client.get("/api/v1/auth/me")
        assert response.status_code == 401

    def test_me_returns_current_user_with_valid_session(self, client, active_user):
        login_response = client.post(
            "/api/v1/auth/login", json={"email": active_user.email, "password": "correct-horse"}
        )
        token = login_response.json()["session_token"]

        response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        assert response.json()["email"] == active_user.email

    def test_logout_invalidates_session(self, client, active_user):
        login_response = client.post(
            "/api/v1/auth/login", json={"email": active_user.email, "password": "correct-horse"}
        )
        token = login_response.json()["session_token"]

        logout_response = client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {token}"})
        assert logout_response.status_code == 200

        me_response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me_response.status_code == 401

    def test_logout_without_token_is_idempotent(self, client):
        response = client.post("/api/v1/auth/logout")
        assert response.status_code == 200

    def test_raw_session_token_is_never_stored_in_the_database(self, client, db_session, active_user):
        """レビュー指摘#2対応: monitor_sessions には生トークンではなくハッシュのみが
        保存されること。生トークンでDBを検索しても行がヒットしないこと、
        ハッシュ化した値でなら見つかることの両方を確認する。"""
        login_response = client.post(
            "/api/v1/auth/login", json={"email": active_user.email, "password": "correct-horse"}
        )
        raw_token = login_response.json()["session_token"]

        stored = db_session.query(MonitorSession).filter(MonitorSession.user_id == active_user.id).one()
        assert stored.token_hash != raw_token
        assert stored.token_hash == hash_session_token(raw_token)

        # 生トークンそのものをDBから検索しても何もヒットしない
        assert (
            db_session.query(MonitorSession).filter(MonitorSession.token_hash == raw_token).first() is None
        )

    def test_deactivating_user_immediately_invalidates_existing_session(self, client, db_session, active_user):
        """ログイン済みでも、後から停止(is_active=False)されれば次のリクエストから
        即座に使えなくなること（get_current_userが毎回最新のis_activeを見るため）"""
        login_response = client.post(
            "/api/v1/auth/login", json={"email": active_user.email, "password": "correct-horse"}
        )
        token = login_response.json()["session_token"]

        active_user.is_active = False
        db_session.commit()

        response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401
