from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Float
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


# 3. Bitácora de manejo e insumos para la Casa Malla
class BitacoraManejo(Base):
    __tablename__ = "bitacora_manejo"

    id = Column(Integer, primary_key=True, index=True)
    casa_malla_id = Column(Integer, ForeignKey("registros_casa_malla.id"))
    
    fecha_aplicacion = Column(DateTime, nullable=False)
    tipo_insumo_labor = Column(String(100), nullable=False) # Ej: Bocashi, Biol, Poda, Deshierbe
    dosis_cantidad = Column(String(100), nullable=True)     # Ej: 2 Litros/Cama, 5 kg
    motivo = Column(String(100), nullable=True)             # Ej: Nutrición, Control preventivo
    observaciones = Column(Text, nullable=True)


# ==========================================
#      MÓDULO DE INFRAESTRUCTURA Y RECURSOS
# ==========================================

# 4. Inventario de Obras Físicas
class Infraestructura(Base):
    __tablename__ = "infraestructura"

    id = Column(Integer, primary_key=True, index=True)
    nombre_obra = Column(String(100), nullable=False)       # Ej: Torre de Tinaco, Baño Seco
    categoria = Column(String(100), nullable=False)         # Ej: Hidráulica, Saneamiento, Vivienda
    estado = Column(String(50), default="Operativa")        # Ej: En construcción, Operativa, Mantenimiento
    capacidad_instalada = Column(String(100), nullable=True)# Ej: 2500 Litros, 2 personas
    materiales_clave = Column(Text, nullable=True)          # Ej: Madera curada, lámina zinc, biodigestor
    coordenadas = Column(String(100), nullable=True)        # Para exportar a QGIS/ArcGIS
    imagen_drive_url = Column(String(500), nullable=True)   # Foto de la obra
    fecha_registro = Column(DateTime, default=datetime.utcnow)

# 5. Bitácora de Gestión del Recurso Hídrico
class RegistroAgua(Base):
    __tablename__ = "registro_agua"

    id = Column(Integer, primary_key=True, index=True)
    infraestructura_id = Column(Integer, ForeignKey("infraestructura.id")) # Se vincula a la Torre de Tinaco, pozo, etc.
    
    fecha_registro = Column(DateTime, nullable=False)
    tipo_movimiento = Column(String(50), nullable=False)    # Ej: Recarga (Lluvia), Recarga (Pozo), Consumo (Riego Bancales)
    volumen_litros = Column(Integer, nullable=True)         # Cantidad de agua que entra o sale
    observaciones = Column(Text, nullable=True)

# ==========================================
#      MÓDULO DE CLIMA Y PLUVIOMETRÍA
# ==========================================

class RegistroClima(Base):
    __tablename__ = "registro_clima"

    id = Column(Integer, primary_key=True, index=True)
    fecha_medicion = Column(DateTime, nullable=False)
    precipitacion_mm = Column(Float, nullable=True)       # Milímetros de lluvia (Pluviómetro)
    temperatura_min = Column(Float, nullable=True)        # °C
    temperatura_max = Column(Float, nullable=True)        # °C
    humedad_relativa = Column(Float, nullable=True)       # Porcentaje
    eventos_extremos = Column(String(100), nullable=True) # Ej: Tormenta, Ola de calor, Granizo
    observaciones = Column(Text, nullable=True)