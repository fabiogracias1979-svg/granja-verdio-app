from sqlalchemy import Column, Integer, String, Text, DateTime
from datetime import datetime
from .database import Base

class RegistroFrutal(Base):
    __tablename__ = "registros_frutales"

    id = Column(Integer, primary_key=True, index=True)
    especie_variedad = Column(String(100), nullable=False)
    lote_sector = Column(String(100), nullable=False)
    
    # Campos agronómicos
    fecha_siembra = Column(String(50), nullable=True)
    edad_meses = Column(Integer, nullable=True)
    tipo_riego = Column(String(100), nullable=True)
    control_plagas = Column(Text, nullable=True)
    manejo_general = Column(Text, nullable=True)
    
    etapa_fenologica = Column(String(100), nullable=True)
    estado_fitosanitario = Column(String(100), nullable=True)
    coordenadas = Column(String(100), nullable=True)
    observaciones = Column(Text, nullable=True)
    fecha_registro = Column(DateTime, default=datetime.utcnow)
    imagen_drive_url = Column(String(500), nullable=False)