from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
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

# 1. Catálogo de especies para la Casa Malla
class CatalogoCultivo(Base):
    __tablename__ = "catalogo_cultivos"

    id = Column(Integer, primary_key=True, index=True)
    especie_variedad = Column(String(100), nullable=False) # Ej: "Tomate Poncho"
    dias_a_trasplante = Column(Integer, nullable=False)    # Ej: 25 (días en semillero)
    dias_a_cosecha = Column(Integer, nullable=False)       # Ej: 80 (días a 1ra cosecha)

# 2. Registro operativo de cada cama/bancal
class RegistroCasaMalla(Base):
    __tablename__ = "registros_casa_malla"

    id = Column(Integer, primary_key=True, index=True)
    identificador_cama = Column(String(50), nullable=False) # Ej: "Cama 1" o "Bancal A"
    cultivo_id = Column(Integer, ForeignKey("catalogo_cultivos.id"))
    
    # Fechas Clave
    fecha_semillero = Column(DateTime, nullable=False)
    
    # Planificación vs Realidad
    fecha_trasplante_estimada = Column(DateTime, nullable=True) # Calculada automáticamente
    fecha_trasplante_real = Column(DateTime, nullable=True)     # Registrada en campo
    
    fecha_cosecha_estimada = Column(DateTime, nullable=True)    # Calculada automáticamente
    
    estado = Column(String(50), default="Semillero") # Semillero, Trasplantado, En Cosecha, Finalizado
    observaciones = Column(Text, nullable=True)