import json
import io
import pandas as pd
import qrcode
from datetime import datetime, timedelta
from fastapi import FastAPI, UploadFile, File, Form, Depends, Request, HTTPException, Query, Response, status
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from .database import engine, Base, get_db
from .models import (
    RegistroFrutal, CatalogoCultivo, RegistroCasaMalla,
    BitacoraManejo, Infraestructura, RegistroAgua,
    RegistroClima, Operador, InsumoOrganico, RiegoCampo
)
from .drive_service import upload_file_to_drive

# Crea las tablas si no existen
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Gestión de Granja Verdio")
templates = Jinja2Templates(directory="templates")

def normalizar_url_drive(resultado):
    if not resultado:
        return "Sin imagen disponible"
    if isinstance(resultado, (tuple, list)):
        for elemento in resultado:
            if isinstance(elemento, str) and elemento.startswith("http"):
                return elemento
        return str(resultado[0])
    return str(resultado)

# ==========================================
#               VISTAS WEB
# ==========================================

@app.get("/", response_class=HTMLResponse)
def ver_inicio(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

@app.get("/formulario-frutales", response_class=HTMLResponse)
def ver_formulario_frutales(request: Request, db: Session = Depends(get_db)):
    # NUEVO: Enviamos la lista de operadores activos al formulario
    operadores = db.query(Operador).filter(Operador.activo == True).all()
    return templates.TemplateResponse(
        request=request, 
        name="formulario.html",
        context={"operadores": operadores}
    )

@app.get("/registros", response_class=HTMLResponse)
def ver_registros(request: Request, db: Session = Depends(get_db)):
    registros = db.query(RegistroFrutal).order_by(RegistroFrutal.id.desc()).all()
    for r in registros:
        ultimo = db.query(RiegoCampo).filter(RiegoCampo.frutal_id == r.id).order_by(RiegoCampo.fecha_aplicacion.desc()).first()
        r.ultimo_riego = ultimo

    return templates.TemplateResponse(
        request=request, 
        name="registros.html", 
        context={"registros": registros}
    )

@app.get("/casa-malla", response_class=HTMLResponse)
def ver_casa_malla(request: Request, db: Session = Depends(get_db)):
    cultivos = db.query(CatalogoCultivo).order_by(CatalogoCultivo.especie_variedad.asc()).all()
    return templates.TemplateResponse(
        request=request, 
        name="casa_malla.html", 
        context={"cultivos": cultivos}
    )

@app.get("/tablero-casa-malla", response_class=HTMLResponse)
def ver_tablero_casa_malla(request: Request, db: Session = Depends(get_db)):
    siembras = db.query(RegistroCasaMalla).order_by(RegistroCasaMalla.id.desc()).all()
    datos_tablero = []
    for s in siembras:
        cultivo = db.query(CatalogoCultivo).filter(CatalogoCultivo.id == s.cultivo_id).first()
        datos_tablero.append({
            "id": s.id,
            "cama": s.identificador_cama,
            "cultivo": cultivo.especie_variedad if cultivo else "Desconocido",
            "estado": s.estado,
            "trasplante": s.fecha_trasplante_estimada.strftime("%d/%m/%Y") if s.fecha_trasplante_estimada else "N/A",
            "cosecha": s.fecha_cosecha_estimada.strftime("%d/%m/%Y") if s.fecha_cosecha_estimada else "N/A"
        })
    return templates.TemplateResponse(
        request=request, 
        name="tablero_casa_malla.html", 
        context={"siembras": datos_tablero}
    )

@app.get("/infraestructura", response_class=HTMLResponse)
def ver_infraestructura(request: Request):
    return templates.TemplateResponse(request=request, name="infraestructura.html")


# ==========================================
#           MÓDULO DE FRUTALES
# ==========================================

@app.post("/api/registro-frutal/")
async def registrar_frutal(
    operador_id: int = Form(...), # NUEVO: Recibe quién está registrando
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
    drive_url = ""
    if archivo and archivo.filename:
        try:
            res = upload_file_to_drive(archivo.file, archivo.filename, archivo.content_type)
            drive_url = normalizar_url_drive(res)
        except Exception as e:
            print(f"Error al subir a Google Drive: {e}")
            drive_url = "Sin imagen disponible"
    else:
        drive_url = "Sin imagen disponible"

    nuevo_registro = RegistroFrutal(
        operador_id=operador_id, # NUEVO: Lo guarda en la base de datos
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

@app.get("/exportar/geojson")
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
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {
                "id": r.id,
                "especie_variedad": getattr(r, "especie_variedad", "N/A"),
                "lote_sector": getattr(r, "lote_sector", "N/A"),
                "fecha_siembra": str(getattr(r, "fecha_siembra", "")),
                "edad_meses": getattr(r, "edad_meses", None),
                "tipo_riego": getattr(r, "tipo_riego", "N/A"),
                "etapa_fenologica": getattr(r, "etapa_fen
