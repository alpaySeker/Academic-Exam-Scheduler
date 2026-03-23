import hashlib
from sqlalchemy.orm import Session
from core.db import SessionLocal
from .models import User

def _hash_password(raw: str) -> str:
    if raw is None:
        raw = ""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def ensure_bootstrap_user(session: Session):
    
    import hashlib
    def hp(s): return hashlib.sha256((s or "").encode("utf-8")).hexdigest()


    target_users = [
        ("admin@local", "admin"),                 
        ("admin@kocaeli.edu.tr", "admin123"),     
    ]


    for email, pwd in target_users:    
        u = session.query(User).filter(User.email == email).first()
        if not u:
            u = User(email=email, name=email.split("@")[0], password_hash=hp(pwd), role="admin", department_id=None)
            session.add(u)
        else:
            u.role = "admin"
            u.department_id = None
            u.password_hash = hp(pwd)
    session.commit()

def verify(session: Session, email: str, password: str, selected_dept_id: int | None):
    
    if session is None:
        session = SessionLocal()
    ensure_bootstrap_user(session)

    user = session.query(User).filter(User.email == (email or "").strip()).first()
    if not user:
        return None
    if user.password_hash != _hash_password(password or ""):
        return None


    if (user.role or "").lower() == "coordinator":
        if not user.department_id or not selected_dept_id or user.department_id != int(selected_dept_id):
            return None  

    return user
