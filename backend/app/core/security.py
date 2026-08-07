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
