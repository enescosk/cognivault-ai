from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db
from app.core.rate_limit import limiter
from app.models import User
from app.schemas.auth import AuthResponse, LoginRequest, RegisterRequest, UserResponse
from app.services.auth_service import authenticate_user, register_customer


router = APIRouter(prefix="/auth", tags=["auth"])


# Auth endpoint'leri brute-force saldırısına özellikle açık. Global 200/dk
# default'unun üstüne çok daha sıkı limit koyuyoruz: login 10/dk, register 5/dk.
@router.post("/login", response_model=AuthResponse)
@limiter.limit("10/minute")
def login(request: Request, payload: LoginRequest, db: Session = Depends(get_db)) -> AuthResponse:
    return authenticate_user(db, payload.email, payload.password)


@router.post("/register", response_model=AuthResponse)
@limiter.limit("5/minute")
def register(request: Request, payload: RegisterRequest, db: Session = Depends(get_db)) -> AuthResponse:
    return register_customer(db, payload.full_name, payload.email, payload.password, payload.locale)


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse.model_validate(current_user)
