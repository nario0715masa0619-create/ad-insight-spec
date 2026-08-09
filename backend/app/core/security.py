"""
招待制モニターベータ用の最小限の認証プリミティブ。

新規の外部ライブラリ依存（passlib/bcrypt/PyJWT等）を追加せず、標準ライブラリの
hashlib.pbkdf2_hmac / secrets のみで実装する。3〜5社規模の招待制ベータという
スコープでは、パスワードはランダム生成してメール等で個別に伝える運用を想定して
おり（セルフサインアップは存在しない）、OAuth/JWTのような複雑さは過剰。
"""
import hashlib
import hmac
import secrets

_PBKDF2_ALGORITHM = "sha256"
_PBKDF2_ITERATIONS = 260_000
_SALT_BYTES = 16


def hash_password(password: str) -> str:
    """パスワードをソルト付きPBKDF2でハッシュ化する。

    保存形式: "pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>"
    （iterationsを埋め込むことで、将来コスト係数を上げても既存ハッシュの
    検証を壊さずに済む）
    """
    salt = secrets.token_hex(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        _PBKDF2_ALGORITHM, password.encode("utf-8"), salt.encode("utf-8"), _PBKDF2_ITERATIONS
    ).hex()
    return f"pbkdf2_sha256${_PBKDF2_ITERATIONS}${salt}${digest}"


def verify_password(password: str, password_hash: str) -> bool:
    """平文パスワードが保存済みハッシュと一致するか検証する（タイミング攻撃耐性あり）"""
    try:
        algorithm, iterations_str, salt, expected_digest = password_hash.split("$", 3)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    try:
        iterations = int(iterations_str)
    except ValueError:
        return False
    actual_digest = hashlib.pbkdf2_hmac(
        _PBKDF2_ALGORITHM, password.encode("utf-8"), salt.encode("utf-8"), iterations
    ).hex()
    return hmac.compare_digest(actual_digest, expected_digest)


def generate_session_token() -> str:
    """ランダムな不透明セッショントークンを生成する"""
    return secrets.token_urlsafe(32)


def hash_session_token(raw_token: str) -> str:
    """
    セッショントークンをDBに保存する前にハッシュ化する。

    パスワードと違い、セッショントークン自体がsecrets.token_urlsafe(32)由来の
    高エントロピーなランダム値であり、オフライン総当たりの対象にする必要が
    ないため、PBKDF2のような低速ハッシュではなく単純なSHA-256で十分
    （ソルトも不要）。目的は「DBが漏洩しても、そこに書かれた値をそのまま
    Authorizationヘッダーに貼り付けるだけでは有効なセッションとして通用しない
    ようにする」ことであり、パスワード用のhash_password/verify_passwordとは
    要求が異なる。
    """
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


# ログイン失敗時のタイミング差から「メールアドレスが登録されているかどうか」が
# 推測できてしまうのを防ぐための固定ダミーハッシュ。存在しないメールアドレスで
# ログインが試みられた場合でも、このハッシュに対して verify_password() を実行し、
# 実在ユーザーへの検証と同じ計算コスト（PBKDF2 260,000回）を払わせる
# （backend/app/api/routes/auth.py::login 参照）。
# パスワード自体に意味は無く、実在するどのアカウントとも一致しない。
DUMMY_PASSWORD_HASH = hash_password(secrets.token_urlsafe(32))
