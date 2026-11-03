import json
import io
import pandas as pd
from datetime import datetime, timedelta
from fastapi import FastAPI, UploadFile, File, Form, Depends, Request, HTTPException, Query, Response
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from .database import engine, Base, get_db
from .models import RegistroFrutal, CatalogoCultivo, RegistroCasaMalla, BitacoraManejo, Infraestructura, RegistroAgua
from .drive_service import upload_file_to_drive

# Crea las tablas si no existen
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Gestión de Granja Verdio")
templates = Jinja2Templates(directory="templates")

# ==========================================
#               VISTAS WEB
# ==========================================

@app.get("/", response_class=HTMLResponse)
def ver_inicio(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

@app.get("/formulario-frutales", response_class=HTMLResponse)
def ver_formulario_frutales(request: Request):
    return templates.TemplateResponse(request=request, name="formulario.html")

@app.get("/registros", response_class=HTMLResponse)
def ver_registros(request: Request, db: Session = Depends(get_db)):
    registros = db.query(RegistroFrutal).order_by(RegistroFrutal.id.desc()).all()
    return templates.TemplateResponse(
        request=request, 
        name="registros.html", 
        context={"registros": registros}
    )

@app.get("/casa-malla", response_class=HTMLResponse)
def ver_casa_malla(request: Request, db: Session = Depends(get_db)):
    # Modificación: Extraer cultivos para el menú desplegable
    cultivos = db.query(CatalogoCultivo).order_by(CatalogoCultivo.especie_variedad.asc()).all()
    return templates.TemplateResponse(request=request, name="casa_malla.html", context={"cultivos": cultivos})

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
    return templates.TemplateResponse(request=request, name="tablero_casa_malla.html", context={"siembras": datos_tablero})

@app.get("/infraestructura", response_class=HTMLResponse)
def ver_infraestructura(request: Request):
    return templates.TemplateResponse(request=request, name="infraestructura.html")


# ==========================================
#           MÓDULO DE FRUTALES
# ==========================================

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
    drive_url = ""
    if archivo and archivo.filename:
        try:
            drive_url = upload_file_to_drive(archivo.file, archivo.filename, archivo.content_type)
        except Exception as e:
            print(f"Error al subir a Google Drive: {e}")
    if not drive_url:
        drive_url = "Sin imagen disponible"

    nuevo_registro = RegistroFrutal(
        especie_variedad=especie_variedad, lote_sector=lote_sector, fecha_siembra=fecha_siembra,
        edad_meses=edad_meses, tipo_riego=tipo_riego, control_plagas=control_plagas,
        manejo_general=manejo_general, etapa_fenologica=etapa_fenologica,
        estado_fitosanitario=estado_fitosanitario