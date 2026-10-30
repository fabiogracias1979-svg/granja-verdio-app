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

# Crea las tablas en la base de datos automáticamente si no existen
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Gestión de Frutales - Granja Verdio")
templates = Jinja2Templates(directory="templates")

# Vista del Formulario Principal
@app.get("/", response_class=HTMLResponse)
def ver_formulario(request: Request):
    return templates.TemplateResponse(request=request, name="formulario.html")

# Vista de Registros Guardados
@app.get("/registros", response_class=HTMLResponse)
def ver_registros(request: Request, db: Session = Depends(get_db)):
    registros = db.query(RegistroFrutal).order_by(RegistroFrutal.id.desc()).all()
    return templates.TemplateResponse(
        request=request, 
        name="registros.html", 
        context={"registros": registros}
    )

# Endpoint para guardar un nuevo registro y subir imagen a Drive
@app.post("/guardar")
async def guardar_registro(
    cultivo: str = Form(...),
    lote: str = Form(...),
    latitud: float = Form(...),
    longitud: float = Form(...),
    estado_fitosanitario: str = Form(...),
    observaciones: str = Form(""),
    foto: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    drive_link = ""
    # Subida de imagen a Google Drive si se adjuntó archivo
    if foto and foto.filename:
        try:
            drive_link = upload_file_to_drive(foto.file, foto.filename, foto.content_type)
        except Exception as e:
            print(f"Error al subir a Google Drive: {e}")
            drive_link = ""

    # Creación del registro en PostgreSQL (Neon)
    nuevo_registro = RegistroFrutal(
        cultivo=cultivo,
        lote=lote,
        latitud=latitud,
        longitud=longitud,
        estado_fitosanitario=estado_fitosanitario,
        observaciones=observaciones,
        drive_link=drive_link
    )
    db.add(nuevo_registro)
    db.commit()
    db.refresh(nuevo_registro)

    return JSONResponse(content={
        "status": "success",
        "mensaje": "Registro guardado correctamente",
        "id": nuevo_registro.id,
        "drive_link": drive_link
    })

# Exportación directa en formato GeoJSON para ArcGIS Pro y QGIS
@app.get("/export/geojson")
def export_geojson(db: Session = Depends(get_db)):
    registros = db.query(RegistroFrutal).all()
    
    features = []
    for r in registros:
        try:
            lat = float(r.latitud)
            lon = float(r.longitud)
        except (ValueError, TypeError):
            continue

        feature = {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [lon, lat]  # Estándar GeoJSON: [Longitud, Latitud]
            },
            "properties": {
                "id": r.id,
                "cultivo": getattr(r, "cultivo", "N/A"),
                "lote": getattr(r, "lote", "N/A"),
                "estado_fitosanitario": getattr(r, "estado_fitosanitario", "N/A"),
                "observaciones": getattr(r, "observaciones", ""),
                "drive_link": getattr(r, "drive_link", ""),
                "fecha_registro": str(getattr(r, "fecha", ""))
            }
        }
        features.append(feature)

    geojson_data = {
        "type": "FeatureCollection",
        "name": "Granja_Verdio_Monitoreo",
        "crs": {
            "type": "name",
            "properties": {
                "name": "urn:ogc:def:crs:OGC:1.3:CRS84"
            }
        },
        "features": features
    }

    json_str = json.dumps(geojson_data, ensure_ascii=False, indent=2)
    return Response(
        content=json_str,
        media_type="application/geo+json",
        headers={"Content-Disposition": "attachment; filename=granja_verdio_datos.geojson"}
    )