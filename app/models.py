from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Float, Boolean
from datetime import datetime
from .database import Base

class RegistroFrutal(Base):
    __tablename__ = "registros_frutales"

    id = Column(Integer, primary_key=True, index=True)
    especie_variedad = Column(String(100), nullable=False)
    lote_sector = Column(String(100), nullable=False)
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
    especie_variedad = Column(String(100), nullable=False)
    dias_a_trasplante = Column(Integer, nullable=False)
    dias_a_cosecha = Column(Integer, nullable=False)


# 2. Registro operativo de cada cama/bancal
class RegistroCasaMalla(Base):
    __tablename__ = "registros_casa_malla"

    id = Column(Integer, primary_key=True, index=True)
    identificador_cama = Column(String(50), nullable=False)
    cultivo_id = Column(Integer, ForeignKey("catalogo_cultivos.id"))
    fecha_semillero = Column(DateTime, nullable=False)
    fecha_trasplante_estimada = Column(DateTime, nullable=True)
    fecha_trasplante_real = Column(DateTime, nullable=True)
    fecha_cosecha_estimada = Column(DateTime, nullable=True)
    estado = Column(String(50), default="Semillero")
    observaciones = Column(Text, nullable=True)


# 3. Bitácora de manejo e insumos para la Casa Malla
class BitacoraManejo(Base):
    __tablename__ = "bitacora_manejo"

    id = Column(Integer, primary_key=True, index=True)
    casa_malla_id = Column(Integer, ForeignKey("registros_casa_malla.id"))
    fecha_aplicacion = Column(DateTime, nullable=False)
    tipo_insumo_labor = Column(String(100), nullable=False)
    dosis_cantidad = Column(String(100), nullable=True)
    motivo = Column(String(100), nullable=True)
    observaciones = Column(Text, nullable=True)


# ==========================================
#      MÓDULO DE INFRAESTRUCTURA Y RECURSOS
# ==========================================

class Infraestructura(Base):
    __tablename__ = "infraestructura"

    id = Column(Integer, primary_key=True, index=True)
    nombre_obra = Column(String(100), nullable=False)
    categoria = Column(String(100), nullable=False)
    estado = Column(String(50), default="Operativa")
    capacidad_instalada = Column(String(100), nullable=True)
    materiales_clave = Column(Text, nullable=True)
    coordenadas = Column(String(100), nullable=True)
    imagen_drive_url = Column(String(500), nullable=True)
    fecha_registro = Column(DateTime, default=datetime.utcnow)


class RegistroAgua(Base):
    __tablename__ = "registro_agua"

    id = Column(Integer, primary_key=True, index=True)
    infraestructura_id = Column(Integer, ForeignKey("infraestructura.id"))
    fecha_registro = Column(DateTime, nullable=False)
    tipo_movimiento = Column(String(50), nullable=False)
    volumen_litros = Column(Integer, nullable=True)
    observaciones = Column(Text, nullable=True)


# ==========================================
#      MÓDULO DE CLIMA Y PLUVIOMETRÍA
# ==========================================

class RegistroClima(Base):
    __tablename__ = "registro_clima"

    id = Column(Integer, primary_key=True, index=True)
    fecha_medicion = Column(DateTime, nullable=False)
    precipitacion_mm = Column(Float, nullable=True)
    temperatura_min = Column(Float, nullable=True)
    temperatura_max = Column(Float, nullable=True)
    humedad_relativa = Column(Float, nullable=True)
    eventos_extremos = Column(String(100), nullable=True)
    observaciones = Column(Text, nullable=True)


# ==========================================
#   CONFIGURACIÓN DINÁMICA: OPERADORES E INSUMOS
# ==========================================

class Operador(Base):
    __tablename__ = "catalogo_operadores"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), unique=True, nullable=False)
    rol = Column(String(60), default="Técnico de Campo")
    activo = Column(Boolean, default=True)


class InsumoOrganico(Base):
    __tablename__ = "catalogo_insumos"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(120), unique=True, nullable=False)
    categoria = Column(String(50), nullable=False)
    dias_carencia = Column(Integer, default=0)
    dosis_recomendada = Column(String(100), nullable=True)
    activo = Column(Boolean, default=True)