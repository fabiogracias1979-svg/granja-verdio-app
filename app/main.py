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

# Crea las tablas si no existen
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Gestión de Frutales - Granja Verdio")
templates = Jinja2Templates(directory="templates")

# Formulario web
@app.get("/", response_class=HTMLResponse)
def ver_formulario(request: Request):
    return templates.TemplateResponse(request=request, name="formulario.html")

# Catálogo web
@app.get("/registros", response_class=HTMLResponse)
def ver_registros(request: Request, db: Session = Depends(get_db)):
    registros = db.query(RegistroFrutal).order_by(RegistroFrutal.id.desc()).all()
    return templates.TemplateResponse(
        request=request, 
        name="registros.html", 
        context={"registros": registros}
    )

# Endpoint que recibe el formulario
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
    observaciones: str = Form(""),
    archivo: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    # Intentar subir la foto a Drive
    drive_url = ""
    if archivo and archivo.filename:
        try:
            drive_url = upload_file_to_drive(archivo.file, archivo.filename, archivo.content_type)
        except Exception as e:
            print(f"Error al subir a Google Drive: {e}")
            drive_url = ""

    # Como imagen_drive_url es nullable=False en models.py, asignamos un valor por defecto si falla Drive
    if not drive_url:
        drive_url = "Sin imagen disponible"

    # Mapeo exacto a las columnas del modelo RegistroFrutal
    nuevo_registro = RegistroFrutal(
        especie_variedad=especie_variedad,
        lote_sector=lote_sector,
        fecha_siembra=fecha_siembra,
        edad_meses=edad_meses,
        tipo_riego=tipo_riego,
        control_plagas=control_plagas,
        manejo_general=manejo_general,
        etapa_fenologica=etapa_fenologica,
        estado_fitosanitario=estado_fitosanitario,
        coordenadas=coordenadas,
        observaciones=observaciones,
        imagen_drive_url=drive_url
    )
    
    db.add(nuevo_registro)
    db.commit()
    db.refresh(nuevo_registro)

    return JSONResponse(content={
        "status": "success",
        "mensaje": "Expediente guardado exitosamente",
        "id": nuevo_registro.id,
        "drive_url": drive_url
    })

# Exportación directa GeoJSON para QGIS y ArcGIS Pro
@app.get("/export/geojson")
def export_geojson(db: Session = Depends(get_db)):
    registros = db.query(RegistroFrutal).all()
    features = []

    for r in registros:
        coord_str = getattr(r, "coordenadas", "")
        if not coord_str or "," not in coord_str:
            continue

        try:
            partes = coord_str.split(",")
            lat = float(partes[0].strip())
            lon = float(partes[1].strip())
        except (ValueError, IndexError):
            continue

        feature = {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [lon, lat]  # GeoJSON estándar: [Longitud, Latitud]
            },
            "properties": {
                "id": r.id,
                "especie_variedad": getattr(r, "especie_variedad", "N/A"),
                "lote_sector": getattr(r, "lote_sector", "N/A"),
                "fecha_siembra": str(getattr(r, "fecha_siembra", "")),
                "edad_meses": getattr(r, "edad_meses", None),
                "tipo_riego": getattr(r, "tipo_riego", "N/A"),
                "etapa_fenologica": getattr(r, "etapa_fenologica", "N/A"),
                "estado_fitosanitario": getattr(r, "estado_fitosanitario", "N/A"),
                "control_plagas": getattr(r, "control_plagas", ""),
                "manejo_general": getattr(r, "manejo_general", ""),
                "observaciones": getattr(r, "observaciones", ""),
                "fecha_registro": str(getattr(r, "fecha_registro", "")),
                "imagen_url": getattr(r, "imagen_drive_url", "")
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