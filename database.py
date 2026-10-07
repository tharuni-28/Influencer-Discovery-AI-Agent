import os
import uuid
from sqlalchemy import create_engine, Column, String, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime

DATABASE_URL = "sqlite:///./influencers.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Influencer(Base):
    __tablename__ = "influencers"

    # Automatically generates a unique string ID
    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    handle = Column(String, nullable=False)
    platform = Column(String, nullable=False)
    followers = Column(String, nullable=True)
    
    # These match your main.py exact column names!
    niche = Column(String, nullable=True, default="Content Creator")
    url = Column(String, nullable=True, default="#")
    
    created_at = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()