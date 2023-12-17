from pydantic_settings import BaseSettings
from sqlalchemy import create_engine, Table, Column, Integer, String, Text, DateTime, MetaData
from pgvector.sqlalchemy import Vector

class Settings(BaseSettings):
    db_user:str
    db_password:str
    db_name:str
    db_host:str
    db_port:int

def get_db_engine():
    settings = Settings()
    engine = create_engine((
        "postgresql+psycopg2://"
        f"{settings.db_user}:{settings.db_password}@"
        f"{settings.db_host}:{settings.db_port}"
        ))
    return engine

def create_database():
    meta = MetaData()
    Table(
        "memory", meta,
        Column("id", Integer, primary_key=True),
        Column("audio_file", String(255)),
        Column("markdown_file", String(255)),
        Column("text", Text),
        Column("start_time", DateTime),
        Column("embeddings", Vector(512)),
        )
    meta.create_all(get_db_engine())
