from fastapi import APIRouter, Depends, HTTPException, Request, status
from pwdlib import PasswordHash
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db
from app.core.limiting import limiter
from app.core.security import create_access_token
from app.models import CareerPreference, User
from app.schemas.auth import LoginRequest, TokenResponse, UserCreate, UserRead
from app.schemas.profile import CareerPreferenceRead
from app.services.preferences import default_preferences

router = APIRouter(prefix="/auth", tags=["authentication"])
password_hash = PasswordHash.recommended()


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("5/minute")
def register(
    payload: UserCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    user = User(
        email=str(payload.email).lower(),
        full_name=payload.full_name.strip(),
        hashed_password=password_hash.hash(payload.password),
    )
    db.add(user)
    try:
        db.flush()
        db.add_all(default_preferences(user.id))
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        ) from exc
    db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
def login(
    payload: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> TokenResponse:
    user = (
        db.query(User)
        .filter(User.email == str(payload.email).lower())
        .one_or_none()
    )
    if user is None or not password_hash.verify(
        payload.password, user.hashed_password
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return TokenResponse(access_token=create_access_token(str(user.id)))


@router.get("/me", response_model=UserRead)
def read_current_user(
    current_user: User = Depends(get_current_user),
) -> User:
    return current_user


@router.get("/preferences", response_model=list[CareerPreferenceRead])
def read_career_preferences(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[CareerPreference]:
    return (
        db.query(CareerPreference)
        .filter(CareerPreference.user_id == current_user.id)
        .order_by(CareerPreference.track)
        .all()
    )
