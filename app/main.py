import json
import io
import pandas as pd
from fastapi import FastAPI, UploadFile, File, Form, Depends, Request, HTTPException, Query, Response
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from .database import engine, Base, get_db
from .models import RegistroFrutal
from .drive_service import upload_file_to_drive

# Crea las tablas en PostgreSQL si aún no existen
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Gestión de Frutales - Granja Verdio")
templates = Jinja2Templates(directory="templates")

# Vista del formulario principal
@app.get("/", response_class=HTMLResponse)
def ver_formulario(request: Request):
    return templates.TemplateResponse(request=request, name="formulario.html")

# Vista de catálogo de registros
@app.get("/registros", response_class=HTMLResponse)
def ver_registros(request: Request, db: Session = Depends(get_db)):
    registros = db.query(RegistroFrutal).order_by(RegistroFrutal.id.desc()).all()
    return templates.TemplateResponse(
        request=request, 
        name="registros.html", 
        context={"registros": registros}
    )

# Ruta exacta que llama tu formulario HTML
@app.post("/api/registro-frutal/")
async def registrar_frutal(
    especie_variedad: str = Form(...),
    lote_sector: str = Form(...),
    fecha_siembra: str = Form(None),
    edad_meses: int = Form(None),
    etapa_fenologica: str = Form(None),
    tipo_riego: str = Form(None),
    estado_fitosanitario: str = Form(None),
    control_plagas: str = Form(""),
    manejo_general: str = Form(""),
    coordenadas: str = Form(""),
    archivo: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    # Separar coordenadas latitud y longitud
    latitud = None
    longitud = None
    if coordenadas and "," in coordenadas:
        partes = coordenadas.split(",")
        try:
            latitud = float(partes[0].strip())
            longitud = float(partes[1].strip())
        except (ValueError, IndexError):
            latitud = None
            longitud = None

    # Subir imagen a Google Drive
    drive_url = ""
    if archivo and archivo.filename:
        try:
            drive_url = upload_file_to_drive(archivo.file, archivo.filename, archivo.content_type)
        except Exception as e:
            print(f"Error al subir a Google Drive: {e}")
            drive_url = ""

    # Crear y guardar en la base de datos Neon (PostgreSQL)
    nuevo_registro = RegistroFrutal(
        especie_variedad=especie_variedad,
        lote_sector=lote_sector,
        fecha_siembra=fecha_siembra,
        edad_meses=edad_meses,
        etapa_fenologica=etapa_fenologica,
        tipo_riego=tipo_riego,
        estado_fitosanitario=estado_fitosanitario,
        control_plagas=control_plagas,
        manejo_general=manejo_general,
        coordenadas=coordenadas,
        latitud=latitud,
        longitud=longitud,
        drive_url=drive_url
    )
    
    db.add(nuevo_registro)
    db.commit()
    db.refresh(nuevo_registro)

    return JSONResponse(content={
        "status": "success",
        "mensaje": "Expediente guardado",
        "id": nuevo_registro.id,
        "drive_url": drive_url
    })

# Descarga directa GeoJSON para QGIS y ArcGIS Pro
@app.get("/export/geojson")
def export_geojson(db: Session = Depends(get_db)):
    registros = db.query(RegistroFrutal).all()
    features = []

    for r in registros:
        # Extrae latitud y longitud numéricas
        lat = getattr(r, "latitud", None)
        lon = getattr(r, "longitud", None)

        if lat is None or lon is None:
            coord_str = getattr(r, "coordenadas", "")
            if coord_str and "," in coord_str:
                try:
                    parts = coord_str.split(",")
                    lat = float(parts[0].strip())
                    lon = float(parts[1].strip())
                except (ValueError, IndexError):
                    continue
            else:
                continue

        feature = {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [float(lon), float(lat)]
            },
            "properties": {
                "id": r.id,
                "especie_variedad": getattr(r, "especie_variedad", "N/A"),
                "lote_sector": getattr(r, "lote_sector", "N/A"),
                "etapa_fenologica": getattr(r, "etapa_fenologica", "N/A"),
                "estado_fitosanitario": getattr(r, "estado_fitosanitario", "N/A"),
                "tipo_riego": getattr(r, "tipo_riego", "N/A"),
                "control_plagas": getattr(r, "control_plagas", ""),
                "manejo_general": getattr(r, "manejo_general", ""),
                "drive_url": getattr(r, "drive_url", "")
            }
        }
        features.append(feature)

    geojson_data = {
        "type": "FeatureCollection",
        "name": "Granja_Verdio_Frutales",
        "crs": {
            "type": "name",
            "properties": {
                "name": "urn:ogc:def:crs:OGC:1.3:CRS84"
            }
        },
        "features": features
    }

    return Response(
        content=json.dumps(geojson_data, ensure_ascii=False, indent=2),
        media_type="application/geo+json",
        headers={"Content-Disposition": "attachment; filename=granja_verdio_datos.geojson"}
    )