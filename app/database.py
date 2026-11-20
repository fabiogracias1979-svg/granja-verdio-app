import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# 1. Leer la variable de entorno de Render, o usar SQLite local como respaldo
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./granja.db")

# 2. Render entrega la URL como "postgres://", pero SQLAlchemy requiere "postgresql://"
if SQLALCHEMY_DATABASE_URL.startswith("postgres://"):
    SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace("postgres://", "postgresql://", 1)

# 3. Configuración del motor de base de datos
if "sqlite" in SQLALCHEMY_DATABASE_URL:
    # Configuración para base de datos local
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL, 
        connect_args={"check_same_thread": False}
    )
else:
    # Configuración optimizada para PostgreSQL en la nube (Render)
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        pool_pre_ping=True,  # Verifica si la conexión sigue activa
        pool_recycle=300,    # Recicla conexiones cada 5 minutos para evitar caídas
        pool_timeout=30
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Función para inyectar la sesión en las rutas de FastAPI
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
