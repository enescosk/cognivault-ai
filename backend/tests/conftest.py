import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.session import SessionLocal
from app.main import app
from app.api.dependencies import get_db
from app.models import Role, RoleName, User
from app.core.security import hash_password

SQLITE_URL = "sqlite:///./test.db"

engine = create_engine(SQLITE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="session", autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    # Seed roles
    for role_name in RoleName:
        if not db.query(Role).filter_by(name=role_name).first():
            db.add(Role(name=role_name, description=role_name.value))
    db.commit()

    # Seed users
    customer_role = db.query(Role).filter_by(name=RoleName.CUSTOMER).first()
    admin_role = db.query(Role).filter_by(name=RoleName.ADMIN).first()
    operator_role = db.query(Role).filter_by(name=RoleName.OPERATOR).first()

    users = [
        User(full_name="Test Customer", email="customer@test.com",
             hashed_password=hash_password("password123"), locale="en",
             role_id=customer_role.id, is_active=True),
        User(full_name="Test Customer2", email="customer2@test.com",
             hashed_password=hash_password("password123"), locale="en",
             role_id=customer_role.id, is_active=True),
        User(full_name="Test Admin", email="admin@test.com",
             hashed_password=hash_password("password123"), locale="en",
             role_id=admin_role.id, is_active=True),
        User(full_name="Test Operator", email="operator@test.com",
             hashed_password=hash_password("password123"), locale="en",
             role_id=operator_role.id, is_active=True),
    ]
    for u in users:
        if not db.query(User).filter_by(email=u.email).first():
            db.add(u)
    db.commit()
    db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def customer_token(client):
    res = client.post("/api/auth/login", json={"email": "customer@test.com", "password": "password123"})
    return res.json()["access_token"]


@pytest.fixture
def admin_token(client):
    res = client.post("/api/auth/login", json={"email": "admin@test.com", "password": "password123"})
    return res.json()["access_token"]


@pytest.fixture
def operator_token(client):
    res = client.post("/api/auth/login", json={"email": "operator@test.com", "password": "password123"})
    return res.json()["access_token"]
