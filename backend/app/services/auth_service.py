"""User accounts, password hashing and JWT issuing/verification.

Only standard-library primitives are used here on purpose: the deployment image
stays small, and every step (PBKDF2 derivation, HS256 signing, timing-safe
comparison) is explicit and easy to explain in a review.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
import uuid
from pathlib import Path

from app.services import shared_cache

DB_PATH = Path(os.getenv("USER_DB_PATH", str(Path(__file__).resolve().parent.parent.parent / "auth.db")))

JWT_ALGORITHM = "HS256"
JWT_ISSUER = "ai-travel-planner"
JWT_TTL_SECONDS = int(os.getenv("JWT_TTL_SECONDS", str(7 * 24 * 3600)))
PBKDF2_ITERATIONS = int(os.getenv("PBKDF2_ITERATIONS", "120000"))
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128

ANONYMOUS_USER_ID = 1
LEGACY_USER_ID = 10
ANONYMOUS_EMAIL = "anonymous@local"

_SECRET_CACHE: bytes | None = None


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}


def _add_column_if_missing(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    if column in _column_names(conn, table):
        return
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def init_db() -> None:
    conn = _connect()
    try:
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL UNIQUE,
                    display_name TEXT NOT NULL DEFAULT '',
                    password_hash TEXT NOT NULL DEFAULT '',
                    role TEXT NOT NULL DEFAULT 'user',
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS auth_tokens (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    jti TEXT NOT NULL UNIQUE,
                    issued_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL,
                    revoked_at TEXT
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_auth_tokens_user ON auth_tokens(user_id, expires_at)")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS auth_login_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    subject TEXT NOT NULL,
                    attempted_at INTEGER NOT NULL,
                    succeeded INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_login_attempts_subject ON auth_login_attempts(subject, attempted_at)"
            )

            # Reserved accounts keep legacy single-user data reachable after migration.
            conn.execute(
                """
                INSERT OR IGNORE INTO users (id, email, display_name, password_hash, role, status)
                VALUES (?, ?, ?, '', 'system', 'active')
                """,
                (ANONYMOUS_USER_ID, ANONYMOUS_EMAIL, "公共演示账号"),
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO users (id, email, display_name, password_hash, role, status)
                VALUES (?, ?, ?, '', 'legacy', 'active')
                """,
                (LEGACY_USER_ID, "legacy@local", "历史数据"),
            )
    finally:
        conn.close()


def ensure_user_db() -> None:
    init_db()


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${_b64url_encode(salt)}${_b64url_encode(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, iterations, salt_b64, digest_b64 = stored.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        salt = _b64url_decode(salt_b64)
        expected = _b64url_decode(digest_b64)
        candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(candidate, expected)


def _secret_path() -> Path:
    override = os.getenv("JWT_SECRET_FILE")
    if override:
        return Path(override)
    return DB_PATH.parent / "jwt_secret.key"


def get_jwt_secret() -> bytes:
    global _SECRET_CACHE
    if _SECRET_CACHE is not None:
        return _SECRET_CACHE

    env_secret = os.getenv("JWT_SECRET", "").strip()
    if env_secret:
        _SECRET_CACHE = env_secret.encode("utf-8")
        return _SECRET_CACHE

    path = _secret_path()
    if path.exists():
        _SECRET_CACHE = path.read_bytes().strip()
        return _SECRET_CACHE

    secret = secrets.token_urlsafe(48).encode("ascii")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(secret)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    _SECRET_CACHE = secret
    return secret


def create_access_token(user_id: int, ttl_seconds: int | None = None) -> tuple[str, dict]:
    now = int(time.time())
    expires_at = now + (ttl_seconds or JWT_TTL_SECONDS)
    jti = uuid.uuid4().hex
    header = {"alg": JWT_ALGORITHM, "typ": "JWT"}
    payload = {
        "sub": str(user_id),
        "iss": JWT_ISSUER,
        "iat": now,
        "exp": expires_at,
        "jti": jti,
    }
    signing_input = f"{_b64url_encode(_json_bytes(header))}.{_b64url_encode(_json_bytes(payload))}"
    signature = hmac.new(get_jwt_secret(), signing_input.encode("ascii"), hashlib.sha256).digest()
    token = f"{signing_input}.{_b64url_encode(signature)}"

    conn = _connect()
    try:
        with conn:
            conn.execute(
                "INSERT INTO auth_tokens (user_id, jti, issued_at, expires_at) VALUES (?, ?, ?, ?)",
                (user_id, jti, now, expires_at),
            )
    finally:
        conn.close()

    return token, {"jti": jti, "expires_at": expires_at, "expires_in": expires_at - now}


def _json_bytes(value: dict) -> bytes:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def decode_access_token(token: str) -> dict:
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("token 格式不正确")
    header_b64, payload_b64, signature_b64 = parts
    signing_input = f"{header_b64}.{payload_b64}"

    expected = hmac.new(get_jwt_secret(), signing_input.encode("ascii"), hashlib.sha256).digest()
    try:
        provided = _b64url_decode(signature_b64)
    except Exception as exc:  # noqa: BLE001 - normalise any malformed base64
        raise ValueError("token 签名无法解析") from exc
    if not hmac.compare_digest(expected, provided):
        raise ValueError("token 签名校验失败")

    try:
        header = json.loads(_b64url_decode(header_b64))
        payload = json.loads(_b64url_decode(payload_b64))
    except Exception as exc:  # noqa: BLE001
        raise ValueError("token 内容无法解析") from exc

    if header.get("alg") != JWT_ALGORITHM:
        raise ValueError("token 算法不受支持")
    if payload.get("iss") != JWT_ISSUER:
        raise ValueError("token 签发方不匹配")
    if int(payload.get("exp") or 0) <= int(time.time()):
        raise ValueError("token 已过期")

    conn = _connect()
    try:
        row = conn.execute(
            "SELECT revoked_at FROM auth_tokens WHERE jti = ?",
            (payload.get("jti"),),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise ValueError("token 已失效")
    if row["revoked_at"]:
        raise ValueError("token 已被吊销")
    return payload


def revoke_token(token: str) -> None:
    try:
        payload = decode_access_token(token)
    except ValueError:
        return
    conn = _connect()
    try:
        with conn:
            conn.execute(
                "UPDATE auth_tokens SET revoked_at = datetime('now', 'localtime') WHERE jti = ?",
                (payload.get("jti"),),
            )
    finally:
        conn.close()


def register_user(email: str, password: str, display_name: str = "") -> dict:
    normalised_email = email.strip().lower()
    if "@" not in normalised_email or len(normalised_email) > 254:
        raise ValueError("邮箱格式不正确")
    if not (MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH):
        raise ValueError(f"密码长度需要在 {MIN_PASSWORD_LENGTH}-{MAX_PASSWORD_LENGTH} 位之间")

    conn = _connect()
    try:
        with conn:
            exists = conn.execute(
                "SELECT id FROM users WHERE email = ?",
                (normalised_email,),
            ).fetchone()
            if exists is not None:
                raise ValueError("该邮箱已注册")
            cursor = conn.execute(
                """
                INSERT INTO users (email, display_name, password_hash)
                VALUES (?, ?, ?)
                """,
                (normalised_email, display_name.strip()[:60], hash_password(password)),
            )
            user_id = int(cursor.lastrowid)
    finally:
        conn.close()

    return get_user_by_id(user_id) or {}


def authenticate_user(email: str, password: str) -> dict | None:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE email = ?",
            (email.strip().lower(),),
        ).fetchone()
    finally:
        conn.close()
    if row is None or not row["password_hash"]:
        # Burn comparable time so a missing account cannot be told apart by latency.
        hash_password(password)
        return None
    if row["status"] != "active":
        return None
    if not verify_password(password, row["password_hash"]):
        return None
    return _row_to_user(row)


def _row_to_user(row: sqlite3.Row) -> dict:
    return {
        "id": int(row["id"]),
        "email": row["email"],
        "display_name": row["display_name"] or "",
        "role": row["role"],
        "status": row["status"],
        "created_at": row["created_at"],
    }


def get_user_by_id(user_id: int) -> dict | None:
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (int(user_id),)).fetchone()
    finally:
        conn.close()
    return _row_to_user(row) if row else None


def get_user_by_email(email: str) -> dict | None:
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email.strip().lower(),)).fetchone()
    finally:
        conn.close()
    return _row_to_user(row) if row else None


def delete_user(user_id: int) -> bool:
    """Remove an account and revoke its tokens; data rows are handled by callers."""
    conn = _connect()
    try:
        with conn:
            conn.execute("UPDATE auth_tokens SET revoked_at = datetime('now', 'localtime') WHERE user_id = ?", (int(user_id),))
            cursor = conn.execute("DELETE FROM users WHERE id = ? AND id > ?", (int(user_id), LEGACY_USER_ID))
            return cursor.rowcount > 0
    finally:
        conn.close()


def record_login_attempt(subject: str, succeeded: bool) -> None:
    normalized = subject.strip().lower()[:254]
    if succeeded:
        shared_cache.reset_counter(f"rate:login_failure:{normalized}")
    else:
        shared_cache.hit(
            f"rate:login_failure:{normalized}",
            max(1, int(os.getenv("AUTH_LOGIN_MAX_ATTEMPTS", "10"))),
            max(1, int(os.getenv("AUTH_LOGIN_WINDOW_SECONDS", "900"))),
        )
    conn = _connect()
    try:
        with conn:
            conn.execute(
                "INSERT INTO auth_login_attempts (subject, attempted_at, succeeded) VALUES (?, ?, ?)",
                (normalized, int(time.time()), 1 if succeeded else 0),
            )
            # Keep the table small without a background job.
            conn.execute(
                "DELETE FROM auth_login_attempts WHERE attempted_at < ?",
                (int(time.time()) - 24 * 3600,),
            )
    finally:
        conn.close()


def login_failure_count(subject: str, window_seconds: int = 900) -> int:
    normalized = subject.strip().lower()[:254]
    conn = _connect()
    try:
        row = conn.execute(
            """
            SELECT COUNT(*) AS c FROM auth_login_attempts
            WHERE subject = ? AND succeeded = 0 AND attempted_at >= ?
            """,
            (normalized, int(time.time()) - window_seconds),
        ).fetchone()
    finally:
        conn.close()
    database_count = int(row["c"] or 0)
    shared_count = shared_cache.current_counter(f"rate:login_failure:{normalized}")
    return max(database_count, shared_count)


def clear_login_failures(subject: str) -> None:
    normalized = subject.strip().lower()[:254]
    shared_cache.reset_counter(f"rate:login_failure:{normalized}")
    conn = _connect()
    try:
        with conn:
            conn.execute(
                "DELETE FROM auth_login_attempts WHERE subject = ? AND succeeded = 0",
                (normalized,),
            )
    finally:
        conn.close()
