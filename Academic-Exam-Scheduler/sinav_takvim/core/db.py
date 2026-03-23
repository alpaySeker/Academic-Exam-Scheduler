
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

def _default_db_path():
    
    root = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
    appdir = os.path.join(root, "sinav_takvim")
    os.makedirs(appdir, exist_ok=True)
    return os.path.join(appdir, "app.db")

DB_PATH = _default_db_path()
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(SQLALCHEMY_DATABASE_URL, future=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
