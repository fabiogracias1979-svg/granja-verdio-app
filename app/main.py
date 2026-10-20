import json
import io
import pandas as pd
from fastapi import FastAPI, UploadFile, File, Form, Depends, Request, HTTPException, Query
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from .database import engine, Base, get_db
from .models import RegistroFrutal
from .drive_service import upload_file_to_drive

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Gestión de Frutales - Granja Verdio")
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
def ver_formulario(request: Request):
    return templates.TemplateResponse(request=request, name="formulario.html")

@app.get("/registros", response_class=HTMLResponse)
def ver_registros(request: Request):
    return templates.TemplateResponse(request=request, name="registros.html")

@app.post("/api/registro-frutal/")
def crear_registro_frutal(
    especie_variedad: str = Form(...),
    lote_sector: str = Form(...),
    etapa_fenologica: str = Form(None),
    estado_fitosanitario: str = Form(None),
    coordenadas: str = Form(None),
    observaciones: str = Form(None),
    archivo: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    try:
        file_id, web_link = upload_file_to_drive(
            file_obj=archivo.file,
            filename=archivo.filename,
            mime_type=archivo.content_type
        )

        nuevo = RegistroFrutal(
            especie_variedad=especie_variedad.strip(),
            lote_sector=lote_sector.strip(),
            etapa_fenologica=etapa_fenologica,
            estado_fitosanitario=estado_fitosanitario,
            coordenadas=coordenadas.strip() if coordenadas else None,
            observaciones=observaciones.strip() if observaciones else None,
            imagen_drive_url=web_link
        )
        db.add(nuevo)
        db.commit()
        db.refresh(nuevo)

        return {"status": "success", "id": nuevo.id, "drive_url": web_link}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/registros")
def listar_registros(
    filtro_estado: str = Query(None),
    db: Session = Depends(get_db)
):
    query = db.query(RegistroFrutal)
    if filtro_estado and filtro_estado != "Todos":
        query = query.filter(RegistroFrutal.estado_fitosanitario == filtro_estado)
    
    registros = query.order_by(RegistroFrutal.fecha_registro.desc()).all()
    
    return [
        {
            "id": r.id,
            "especie_variedad": r.especie_variedad,
            "lote_sector": r.lote_sector,
            "etapa_fenologica": r.etapa_fenologica or "N/D",
            "estado_fitosanitario": r.estado_fitosanitario or "N/D",
            "coordenadas": r.coordenadas or "",
            "observaciones": r.observaciones or "",
            "fecha": r.fecha_registro.strftime("%Y-%m-%d %H:%M") if r.fecha_registro else "",
            "imagen_drive_url": r.imagen_drive_url
        }
        for r in registros
    ]

@app.get("/exportar/geojson")
def exportar_geojson(db: Session = Depends(get_db)):
    registros = db.query(RegistroFrutal).all()
    features = []
    
    for r in registros:
        geometry = None
        if r.coordenadas and "," in r.coordenadas:
            try:
                parts = r.coordenadas.split(",")
                lat = float(parts[0].strip())
                lon = float(parts[1].strip())
                geometry = {"type": "Point", "coordinates": [lon, lat]}
            except Exception:
                geometry = None

        if geometry:
            features.append({
                "type": "Feature",
                "geometry": geometry,
                "properties": {
                    "id": r.id,
                    "especie_variedad": r.especie_variedad,
                    "lote_sector": r.lote_sector,
                    "etapa_fenologica": r.etapa_fenologica,
                    "estado_fitosanitario": r.estado_fitosanitario,
                    "observaciones": r.observaciones,
                    "fecha": r.fecha_registro.strftime("%Y-%m-%d %H:%M") if r.fecha_registro else "",
                    "drive_url": r.imagen_drive_url
                }
            })

    geojson_data = {
        "type": "FeatureCollection",
        "name": "monitoreo_frutales",
        "crs": {
            "type": "name",
            "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}
        },
        "features": features
    }

    return JSONResponse(
        content=geojson_data,
        headers={"Content-Disposition": "attachment; filename=frutales_granja_verdio.geojson"}
    )

@app.get("/exportar/excel")
def exportar_excel(db: Session = Depends(get_db)):
    registros = db.query(RegistroFrutal).all()
    filas = []
    for r in registros:
        lat, lon = "", ""
        if r.coordenadas and "," in r.coordenadas:
            try:
                partes = r.coordenadas.split(",")
                lat, lon = partes[0].strip(), partes[1].strip()
            except Exception:
                pass
        
        filas.append({
            "ID": r.id,
            "Especie / Variedad": r.especie_variedad,
            "Lote / Sector": r.lote_sector,
            "Etapa Fenológica": r.etapa_fenologica,
            "Estado Fitosanitario": r.estado_fitosanitario,
            "Latitud": lat,
            "Longitud": lon,
            "Observaciones": r.observaciones,
            "Fecha": r.fecha_registro.strftime("%Y-%m-%d %H:%M") if r.fecha_registro else "",
            "URL Foto Google Drive": r.imagen_drive_url
        })
    
    df = pd.DataFrame(filas)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Monitoreo_Frutales')
    output.seek(0)

    headers = {'Content-Disposition': 'attachment; filename="reporte_frutales.xlsx"'}
    return StreamingResponse(
        output,
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers=headers
    )
