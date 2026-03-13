from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import io
import logging
import os
import re
import secrets
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

import qrcode
import requests
from fastapi import Body, Depends, FastAPI, Header, HTTPException, Query, status
from pydantic import BaseModel, Field
from qrcode.image.svg import SvgImage
from sqlalchemy import Boolean, DateTime, Integer, String, Text, create_engine, desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, declarative_base, mapped_column, sessionmaker


def _env(name: str, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if value is None:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _env_bool(name: str, default: bool = False) -> bool:
    raw = _env(name, "true" if default else "false").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError(f"Invalid boolean value for {name}: {raw}")


DATABASE_URL = _env(
    "KEYGEN_DATABASE_URL",
    "postgresql+psycopg2://synapse:change_me_postgres_password@postgres:5432/synapse",
)
BOOTSTRAP_MASTER_KEY = _env("KEYGEN_MASTER_KEY", "change_me_master_key")
TOKEN_HASH_SECRET = _env("KEYGEN_TOKEN_HASH_SECRET", BOOTSTRAP_MASTER_KEY)
MASTER_KEY_HEADER = _env("KEYGEN_MASTER_KEY_HEADER", "X-Master-Key")
SYNAPSE_ADMIN_BASE_URL = _env(
    "KEYGEN_SYNAPSE_ADMIN_BASE_URL",
    "http://synapse:8008",
).rstrip("/")
SYNAPSE_REG_SHARED_SECRET = _env(
    "KEYGEN_SYNAPSE_REGISTRATION_SHARED_SECRET",
    "change_me_registration_shared_secret",
)
DEFAULT_TTL_SECONDS = int(_env("KEYGEN_DEFAULT_TTL_SECONDS", "900"))
TOKEN_TTL_SECONDS = int(_env("KEYGEN_TOKEN_TTL_SECONDS", str(DEFAULT_TTL_SECONDS)))
MAX_TTL_SECONDS = int(_env("KEYGEN_MAX_TTL_SECONDS", "86400"))
CREATE_MIN_RESPONSE_SECONDS = float(_env("KEYGEN_CREATE_MIN_RESPONSE_SECONDS", "3"))
USER_PREFIX = _env("KEYGEN_USER_PREFIX", "user")
QR_PAYLOAD_PREFIX = _env("KEYGEN_QR_PAYLOAD_PREFIX", "secmess://invite?token=")
MATRIX_SERVER_NAME = _env("KEYGEN_MATRIX_SERVER_NAME", "secmess.cloudpub.ru")
EXPOSE_DOCS = _env_bool("KEYGEN_EXPOSE_DOCS", default=False)
DEFAULT_ADMIN_USER_ID = _env(
    "KEYGEN_DEFAULT_ADMIN_USER_ID",
    f"@admin:{MATRIX_SERVER_NAME}",
)
ROLE_SUPER_ADMINS = _env("KEYGEN_ROLE_SUPER_ADMINS", "")
ROLE_ADMINS = _env("KEYGEN_ROLE_ADMINS", DEFAULT_ADMIN_USER_ID)
ROLE_DEVELOPERS = _env("KEYGEN_ROLE_DEVELOPERS", "")

if DEFAULT_TTL_SECONDS <= 0:
    raise RuntimeError("KEYGEN_DEFAULT_TTL_SECONDS must be > 0")
if TOKEN_TTL_SECONDS <= 0:
    raise RuntimeError("KEYGEN_TOKEN_TTL_SECONDS must be > 0")
if MAX_TTL_SECONDS <= 0:
    raise RuntimeError("KEYGEN_MAX_TTL_SECONDS must be > 0")
if TOKEN_TTL_SECONDS > MAX_TTL_SECONDS:
    raise RuntimeError("KEYGEN_TOKEN_TTL_SECONDS must be <= KEYGEN_MAX_TTL_SECONDS")
if CREATE_MIN_RESPONSE_SECONDS < 0:
    raise RuntimeError("KEYGEN_CREATE_MIN_RESPONSE_SECONDS must be >= 0")
if not BOOTSTRAP_MASTER_KEY.strip():
    raise RuntimeError("KEYGEN_MASTER_KEY must be non-empty")
if not TOKEN_HASH_SECRET.strip():
    raise RuntimeError("KEYGEN_TOKEN_HASH_SECRET must be non-empty")

USERNAME_RE = re.compile(r"^[a-z0-9._=-]{3,64}$")
MASTER_KEY_FORMAT_RE = re.compile(r"^smk1\.([a-zA-Z0-9_-]{8,64})\.([A-Za-z0-9_-]{32,256})$")
HEADER_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9-]{1,62}$")

if not HEADER_NAME_RE.fullmatch(MASTER_KEY_HEADER):
    raise RuntimeError(
        "KEYGEN_MASTER_KEY_HEADER must contain only letters, numbers and dashes "
        "and start with a letter",
    )

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    future=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()
logger = logging.getLogger("secmess.keygen")


class InviteToken(Base):
    __tablename__ = "keygen_invite_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    ttl_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    used_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    used_by_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)


class MasterKeyRecord(Base):
    __tablename__ = "keygen_master_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    key_version: Mapped[str] = mapped_column(String(16), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    rotated_from_key_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AdminAuditEvent(Base):
    __tablename__ = "keygen_admin_audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    actor_role: Mapped[str] = mapped_column(String(32), nullable=False)
    action: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    master_key_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target: Mapped[str | None] = mapped_column(String(255), nullable=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )


class TokenCreateRequest(BaseModel):
    ttl_seconds: int | None = Field(default=None, ge=1)


class TokenCreateResponse(BaseModel):
    token_id: int
    token: str
    qr_payload: str
    expires_at: dt.datetime
    qr_png_base64: str
    qr_svg: str


class TokenRedeemRequest(BaseModel):
    token: str = Field(min_length=24, max_length=256)
    username: str | None = None
    display_name: str | None = Field(default=None, max_length=255)


class TokenRedeemResponse(BaseModel):
    user_id: str
    access_token: str
    home_server: str | None = None
    device_id: str | None = None


class UserRole(str, Enum):
    super_admin = "super-admin"
    admin = "admin"
    developer = "developer"
    user = "user"


class AuthMeResponse(BaseModel):
    user_id: str
    role: UserRole


class AuthenticatedActor(BaseModel):
    user_id: str
    role: UserRole
    access_token: str


class MasterKeyInfoResponse(BaseModel):
    key_id: str
    key_version: str
    created_by: str
    created_at: dt.datetime


class MasterKeyRotateRequest(BaseModel):
    new_master_key: str | None = Field(default=None, max_length=512)
    reason: str | None = Field(default=None, max_length=255)


class MasterKeyRotateResponse(BaseModel):
    master_key: str
    active_key_id: str
    previous_key_id: str
    rotated_at: dt.datetime


class AuditEventItem(BaseModel):
    id: int
    actor_user_id: str
    actor_role: str
    action: str
    status: str
    master_key_id: str | None
    target: str | None
    details: str | None
    created_at: dt.datetime


class AuditEventsResponse(BaseModel):
    events: list[AuditEventItem]


@dataclass(frozen=True)
class MasterKeyMaterial:
    version: str
    key_id: str
    secret: str
    raw_value: str


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def enforce_min_response_time(started_at: float, min_seconds: float) -> None:
    if min_seconds <= 0:
        return
    elapsed = time.monotonic() - started_at
    remaining = min_seconds - elapsed
    if remaining > 0:
        time.sleep(remaining)


def hash_token(token: str) -> str:
    return hmac.new(
        TOKEN_HASH_SECRET.encode("utf-8"),
        token.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()


def hash_master_key(master_key: str) -> str:
    return hashlib.sha256(master_key.encode("utf-8")).hexdigest()


def parse_user_ids(raw: str) -> set[str]:
    return {item.strip().lower() for item in raw.split(",") if item.strip()}


SUPER_ADMIN_USERS = parse_user_ids(ROLE_SUPER_ADMINS)
ADMIN_USERS = parse_user_ids(ROLE_ADMINS)
DEVELOPER_USERS = parse_user_ids(ROLE_DEVELOPERS)
CREATE_TOKEN_ROLES = {UserRole.admin, UserRole.super_admin, UserRole.developer}
ROTATE_MASTER_KEY_ROLES = {UserRole.super_admin, UserRole.developer}


def role_for_user_id(user_id: str) -> UserRole:
    normalized = user_id.strip().lower()
    if normalized in SUPER_ADMIN_USERS:
        return UserRole.super_admin
    if normalized in ADMIN_USERS:
        return UserRole.admin
    if normalized in DEVELOPER_USERS:
        return UserRole.developer
    return UserRole.user


def parse_bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer authorization token",
        )

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format",
        )
    return token.strip()


def sanitize_username(raw: str | None) -> str:
    if raw is None:
        generated = f"{USER_PREFIX}_{secrets.token_hex(4)}"
        return generated.lower()

    username = raw.strip().lower()
    if not USERNAME_RE.fullmatch(username):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid username format",
        )
    return username


def resolve_token_ttl_seconds(request_ttl: int | None) -> int:
    if request_ttl is None:
        return TOKEN_TTL_SECONDS
    if request_ttl > MAX_TTL_SECONDS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"ttl_seconds must be <= {MAX_TTL_SECONDS}",
        )
    return request_ttl


def parse_master_key_material(value: str, *, allow_legacy: bool) -> MasterKeyMaterial:
    raw_value = value.strip()
    if not raw_value:
        raise ValueError("Master key cannot be empty")

    matched = MASTER_KEY_FORMAT_RE.fullmatch(raw_value)
    if matched:
        key_id, secret = matched.groups()
        return MasterKeyMaterial(
            version="smk1",
            key_id=key_id,
            secret=secret,
            raw_value=raw_value,
        )

    if allow_legacy:
        digest = hashlib.sha256(raw_value.encode("utf-8")).hexdigest()[:12]
        return MasterKeyMaterial(
            version="legacy",
            key_id=f"legacy-{digest}",
            secret=raw_value,
            raw_value=raw_value,
        )

    raise ValueError("Invalid master key format. Expected: smk1.<key_id>.<secret>")


def generate_master_key() -> str:
    key_id = secrets.token_hex(8)
    secret = secrets.token_urlsafe(48)
    return f"smk1.{key_id}.{secret}"


def generate_qr_png_b64(payload: str) -> str:
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2,
    )
    qr.add_data(payload)
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def generate_qr_svg(payload: str) -> str:
    image = qrcode.make(payload, image_factory=SvgImage)
    buffer = io.BytesIO()
    image.save(buffer)
    return buffer.getvalue().decode("utf-8")


def generate_synapse_mac(
    nonce: str,
    username: str,
    password: str,
    admin: bool = False,
    user_type: str | None = None,
) -> str:
    mac = hmac.new(
        key=SYNAPSE_REG_SHARED_SECRET.encode("utf-8"),
        digestmod=hashlib.sha1,
    )
    mac.update(nonce.encode("utf-8"))
    mac.update(b"\x00")
    mac.update(username.encode("utf-8"))
    mac.update(b"\x00")
    mac.update(password.encode("utf-8"))
    mac.update(b"\x00")
    mac.update(b"admin" if admin else b"notadmin")
    if user_type:
        mac.update(b"\x00")
        mac.update(user_type.encode("utf-8"))
    return mac.hexdigest()


def synapse_create_user(username: str, display_name: str | None = None) -> dict[str, Any]:
    register_url = f"{SYNAPSE_ADMIN_BASE_URL}/_synapse/admin/v1/register"
    timeout = 15

    try:
        nonce_response = requests.get(register_url, timeout=timeout)
    except requests.RequestException as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Cannot request nonce from Synapse: {exc}",
        ) from exc

    if nonce_response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Synapse nonce request failed with status {nonce_response.status_code}",
        )

    try:
        nonce_payload = nonce_response.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Synapse nonce response is not valid JSON",
        ) from exc
    nonce = nonce_payload.get("nonce")
    if not nonce:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Synapse nonce response is missing 'nonce'",
        )

    password = secrets.token_urlsafe(32)
    mac = generate_synapse_mac(
        nonce=nonce,
        username=username,
        password=password,
        admin=False,
    )

    payload: dict[str, Any] = {
        "nonce": nonce,
        "username": username,
        "password": password,
        "admin": False,
        "mac": mac,
    }
    if display_name:
        payload["displayname"] = display_name

    try:
        register_response = requests.post(register_url, json=payload, timeout=timeout)
    except requests.RequestException as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Cannot create user in Synapse: {exc}",
        ) from exc

    if register_response.status_code not in (200, 201):
        message = register_response.text.strip()
        if len(message) > 512:
            message = f"{message[:512]}..."
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Synapse register failed [{register_response.status_code}]: {message}",
        )

    try:
        data = register_response.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Synapse register response is not valid JSON",
        ) from exc
    required = ("user_id", "access_token")
    if not all(key in data for key in required):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Synapse registration response is missing access data",
        )
    return data


def synapse_whoami(access_token: str) -> dict[str, Any]:
    whoami_url = f"{SYNAPSE_ADMIN_BASE_URL}/_matrix/client/v3/account/whoami"
    headers = {"Authorization": f"Bearer {access_token}"}
    timeout = 15

    try:
        response = requests.get(whoami_url, headers=headers, timeout=timeout)
    except requests.RequestException as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Cannot verify access token via Synapse whoami: {exc}",
        ) from exc

    if response.status_code in (401, 403):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Matrix access token",
        )

    if response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Synapse whoami failed with status {response.status_code}",
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Synapse whoami response is not valid JSON",
        ) from exc
    if not payload.get("user_id"):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Synapse whoami response is missing user_id",
        )

    return payload


def get_active_master_key_row(db: Session) -> MasterKeyRecord | None:
    return db.execute(
        select(MasterKeyRecord)
        .where(
            MasterKeyRecord.is_active.is_(True),
            MasterKeyRecord.revoked_at.is_(None),
        )
        .order_by(desc(MasterKeyRecord.id))
        .limit(1)
    ).scalar_one_or_none()


def ensure_master_key_seed(db: Session) -> None:
    material = parse_master_key_material(BOOTSTRAP_MASTER_KEY, allow_legacy=True)
    digest = hash_master_key(material.raw_value)
    active = get_active_master_key_row(db)

    if active is None:
        db.add(
            MasterKeyRecord(
                key_id=material.key_id,
                key_version=material.version,
                key_hash=digest,
                is_active=True,
                created_by="system:bootstrap",
                rotated_from_key_id=None,
            )
        )
        return

    if hmac.compare_digest(active.key_hash, digest):
        return

    logger.warning(
        "Active master key in DB differs from KEYGEN_MASTER_KEY env. "
        "DB active key will be used until explicit rotation."
    )


def append_admin_audit_event(
    db: Session,
    actor: AuthenticatedActor,
    action: str,
    status_text: str,
    *,
    master_key_id: str | None = None,
    target: str | None = None,
    details: str | None = None,
) -> None:
    db.add(
        AdminAuditEvent(
            actor_user_id=actor.user_id,
            actor_role=actor.role.value,
            action=action,
            status=status_text,
            master_key_id=master_key_id,
            target=target,
            details=details,
        )
    )


def get_authenticated_actor(
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> AuthenticatedActor:
    access_token = parse_bearer_token(authorization)
    whoami = synapse_whoami(access_token)
    user_id = str(whoami["user_id"])
    role = role_for_user_id(user_id)
    return AuthenticatedActor(
        user_id=user_id,
        role=role,
        access_token=access_token,
    )


def require_invite_creator_role(
    actor: AuthenticatedActor = Depends(get_authenticated_actor),
) -> AuthenticatedActor:
    if actor.role not in CREATE_TOKEN_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Insufficient role for invite creation. "
                "Required: admin, super-admin, or developer."
            ),
        )
    return actor


def require_master_key_rotator_role(
    actor: AuthenticatedActor = Depends(get_authenticated_actor),
) -> AuthenticatedActor:
    if actor.role not in ROTATE_MASTER_KEY_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient role for master key rotation. Required: super-admin or developer.",
        )
    return actor


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def require_master_key(
    provided_master_key: str | None = Header(default=None, alias=MASTER_KEY_HEADER),
    db: Session = Depends(get_db),
) -> MasterKeyRecord:
    if not provided_master_key or not provided_master_key.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Missing master key header: {MASTER_KEY_HEADER}",
        )

    candidate_hash = hash_master_key(provided_master_key.strip())
    active = get_active_master_key_row(db)
    if active is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Master key is not initialized",
        )

    if not hmac.compare_digest(candidate_hash, active.key_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid master key",
        )

    return active


app = FastAPI(
    title="SecMess Keygen API",
    version="0.4.0",
    docs_url="/docs" if EXPOSE_DOCS else None,
    redoc_url="/redoc" if EXPOSE_DOCS else None,
    openapi_url="/openapi.json" if EXPOSE_DOCS else None,
)


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        with db.begin():
            ensure_master_key_seed(db)


@app.get("/healthz")
def healthz(db: Session = Depends(get_db)) -> dict[str, str]:
    db.execute(select(1))
    return {"status": "ok"}


@app.get("/auth/me", response_model=AuthMeResponse)
def auth_me(actor: AuthenticatedActor = Depends(get_authenticated_actor)) -> AuthMeResponse:
    return AuthMeResponse(user_id=actor.user_id, role=actor.role)


@app.get("/admin/master-key", response_model=MasterKeyInfoResponse)
def get_master_key_info(
    _actor: AuthenticatedActor = Depends(require_invite_creator_role),
    _master_key: MasterKeyRecord = Depends(require_master_key),
    db: Session = Depends(get_db),
) -> MasterKeyInfoResponse:
    active = get_active_master_key_row(db)
    if active is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Master key is not initialized",
        )
    return MasterKeyInfoResponse(
        key_id=active.key_id,
        key_version=active.key_version,
        created_by=active.created_by,
        created_at=active.created_at,
    )


@app.post("/admin/master-key/rotate", response_model=MasterKeyRotateResponse)
def rotate_master_key(
    request: MasterKeyRotateRequest = Body(default_factory=MasterKeyRotateRequest),
    actor: AuthenticatedActor = Depends(require_master_key_rotator_role),
    active_master_key: MasterKeyRecord = Depends(require_master_key),
    db: Session = Depends(get_db),
) -> MasterKeyRotateResponse:
    raw_new_master_key = request.new_master_key.strip() if request.new_master_key else generate_master_key()
    try:
        material = parse_master_key_material(raw_new_master_key, allow_legacy=False)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    new_hash = hash_master_key(raw_new_master_key)
    if hmac.compare_digest(new_hash, active_master_key.key_hash):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="New master key must differ from the current active key",
        )

    rotated_at = now_utc()
    previous_key_id = active_master_key.key_id

    try:
        with db.begin():
            current_locked = db.execute(
                select(MasterKeyRecord)
                .where(MasterKeyRecord.id == active_master_key.id)
                .with_for_update()
            ).scalar_one_or_none()

            if (
                current_locked is None
                or not current_locked.is_active
                or current_locked.revoked_at is not None
            ):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Current master key is no longer active; retry with the latest key",
                )

            current_locked.is_active = False
            current_locked.revoked_at = rotated_at

            replacement = MasterKeyRecord(
                key_id=material.key_id,
                key_version=material.version,
                key_hash=new_hash,
                is_active=True,
                created_by=actor.user_id,
                rotated_from_key_id=current_locked.key_id,
                created_at=rotated_at,
            )
            db.add(replacement)
            db.flush()

            details = request.reason.strip() if request.reason else None
            append_admin_audit_event(
                db,
                actor,
                action="master_key.rotate",
                status_text="success",
                master_key_id=replacement.key_id,
                target=f"{current_locked.key_id}->{replacement.key_id}",
                details=details,
            )
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Master key rotation conflict (duplicate key id or value)",
        ) from exc

    return MasterKeyRotateResponse(
        master_key=raw_new_master_key,
        active_key_id=material.key_id,
        previous_key_id=previous_key_id,
        rotated_at=rotated_at,
    )


@app.get("/admin/audit/events", response_model=AuditEventsResponse)
def list_admin_audit_events(
    limit: int = Query(default=50, ge=1, le=500),
    _actor: AuthenticatedActor = Depends(require_invite_creator_role),
    _master_key: MasterKeyRecord = Depends(require_master_key),
    db: Session = Depends(get_db),
) -> AuditEventsResponse:
    rows = db.execute(
        select(AdminAuditEvent)
        .order_by(desc(AdminAuditEvent.id))
        .limit(limit)
    ).scalars().all()
    return AuditEventsResponse(
        events=[
            AuditEventItem(
                id=row.id,
                actor_user_id=row.actor_user_id,
                actor_role=row.actor_role,
                action=row.action,
                status=row.status,
                master_key_id=row.master_key_id,
                target=row.target,
                details=row.details,
                created_at=row.created_at,
            )
            for row in rows
        ]
    )


@app.post("/token/create", response_model=TokenCreateResponse)
def create_token(
    request: TokenCreateRequest = Body(default_factory=TokenCreateRequest),
    actor: AuthenticatedActor = Depends(require_invite_creator_role),
    master_key: MasterKeyRecord = Depends(require_master_key),
    db: Session = Depends(get_db),
) -> TokenCreateResponse:
    started_at = time.monotonic()
    try:
        ttl_seconds = resolve_token_ttl_seconds(request.ttl_seconds)
        created_at = now_utc()
        expires_at = created_at + dt.timedelta(seconds=ttl_seconds)

        token = secrets.token_urlsafe(32)
        token_digest = hash_token(token)

        row = InviteToken(
            token_hash=token_digest,
            created_by=actor.user_id,
            ttl_seconds=ttl_seconds,
            expires_at=expires_at,
        )
        db.add(row)
        db.flush()

        append_admin_audit_event(
            db,
            actor,
            action="token.create",
            status_text="success",
            master_key_id=master_key.key_id,
            target=f"token_id={row.id}",
            details=f"ttl_seconds={ttl_seconds}",
        )

        db.commit()
        db.refresh(row)

        qr_payload = f"{QR_PAYLOAD_PREFIX}{token}"
        return TokenCreateResponse(
            token_id=row.id,
            token=token,
            qr_payload=qr_payload,
            expires_at=expires_at,
            qr_png_base64=generate_qr_png_b64(qr_payload),
            qr_svg=generate_qr_svg(qr_payload),
        )
    finally:
        enforce_min_response_time(started_at, CREATE_MIN_RESPONSE_SECONDS)


@app.post("/token/redeem", response_model=TokenRedeemResponse)
def redeem_token(
    request: TokenRedeemRequest,
    db: Session = Depends(get_db),
) -> TokenRedeemResponse:
    token_digest = hash_token(request.token)
    username = sanitize_username(request.username)

    with db.begin():
        token_row = db.execute(
            select(InviteToken)
            .where(InviteToken.token_hash == token_digest)
            .with_for_update()
        ).scalar_one_or_none()

        if token_row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Token not found",
            )

        current_time = now_utc()
        if token_row.revoked_at is not None:
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="Token revoked",
            )
        if token_row.used_at is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Token already used",
            )
        if token_row.expires_at <= current_time:
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="Token expired",
            )

        registration_result = synapse_create_user(
            username=username,
            display_name=request.display_name,
        )
        token_row.used_at = current_time
        token_row.used_by_user_id = registration_result["user_id"]

    return TokenRedeemResponse(
        user_id=registration_result["user_id"],
        access_token=registration_result["access_token"],
        home_server=registration_result.get("home_server") or MATRIX_SERVER_NAME,
        device_id=registration_result.get("device_id"),
    )
