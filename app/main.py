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

# Función auxiliar para extraer el enlace si Drive devuelve una tupla
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
def ver_formulario_frutales(request: Request):
    return templates.TemplateResponse(request=request, name="formulario.html")

@app.get("/registros", response_class=HTMLResponse)
def ver_registros(request: Request, db: Session = Depends(get_db)):
    registros = db.query(RegistroFrutal).order_by(RegistroFrutal.id.desc()).all()
    
    # NUEVO: Buscar el último riego de cada árbol para mostrarlo en la tabla
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

# Exportación GeoJSON
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
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
        "features": features
    }
    return Response(
        content=json.dumps(geojson_data, ensure_ascii=False, indent=2),
        media_type="application/geo+json",
        headers={"Content-Disposition": "attachment; filename=granja_verdio_datos.geojson"}
    )

# Exportación Excel
@app.get("/exportar/excel")
@app.get("/export/excel")
def export_excel(db: Session = Depends(get_db)):
    registros = db.query(RegistroFrutal).all()
    
    data = []
    for r in registros:
        data.append({
            "ID": r.id,
            "Especie / Variedad": getattr(r, "especie_variedad", ""),
            "Lote / Sector": getattr(r, "lote_sector", ""),
            "Fecha Siembra": getattr(r, "fecha_siembra", ""),
            "Edad (Meses)": getattr(r, "edad_meses", ""),
            "Riego": getattr(r, "tipo_riego", ""),
            "Fenología": getattr(r, "etapa_fenologica", ""),
            "Condición Fitosanitaria": getattr(r, "estado_fitosanitario", ""),
            "Control Plagas": getattr(r, "control_plagas", ""),
            "Manejo General": getattr(r, "manejo_general", ""),
            "Coordenadas": getattr(r, "coordenadas", ""),
            "Observaciones": getattr(r, "observaciones", ""),
            "URL Imagen Drive": getattr(r, "imagen_drive_url", "")
        })

    df = pd.DataFrame(data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Frutales')
    output.seek(0)

    headers = {
        'Content-Disposition': 'attachment; filename="granja_verdio_frutales.xlsx"'
    }
    return StreamingResponse(
        output,
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers=headers
    )

# ==========================================
#        MÓDULO DE CÓDIGOS QR Y PLACAS
# ==========================================

@app.get("/qr/frutal/{frutal_id}")
def generar_qr_frutal(frutal_id: int, request: Request, db: Session = Depends(get_db)):
    frutal = db.query(RegistroFrutal).filter(RegistroFrutal.id == frutal_id).first()
    if not frutal:
        raise HTTPException(status_code=404, detail="Frutal no encontrado")

    base_url = str(request.base_url).rstrip("/")
    destino_url = f"{base_url}/escanear/{frutal.id}"

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=3,
    )
    qr.add_data(destino_url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="#1e5235", back_color="white")

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)

    return StreamingResponse(buffer, media_type="image/png")

@app.get("/placa/frutal", response_class=HTMLResponse)
@app.get("/placa/frutal/", response_class=HTMLResponse)
def redirigir_placa_por_defecto(db: Session = Depends(get_db)):
    primer_frutal = db.query(RegistroFrutal).order_by(RegistroFrutal.id.asc()).first()
    if primer_frutal:
        return RedirectResponse(url=f"/placa/frutal/{primer_frutal.id}", status_code=status.HTTP_303_SEE_OTHER)
    return HTMLResponse("<h3>Aún no hay frutales registrados en el sistema.</h3>", status_code=404)

@app.get("/placa/frutal/{frutal_id}", response_class=HTMLResponse)
def ver_placa_imprimible(frutal_id: int, request: Request, db: Session = Depends(get_db)):
    frutal = db.query(RegistroFrutal).filter(RegistroFrutal.id == frutal_id).first()
    if not frutal:
        raise HTTPException(status_code=404, detail="Frutal no encontrado")
        
    return templates.TemplateResponse(
        request=request,
        name="placa_qr.html",
        context={"frutal": frutal}
    )

# ==========================================
#        MÓDULO DE ESCANEO MÓVIL Y CAMPO
# ==========================================

@app.get("/escanear/{frutal_id}", response_class=HTMLResponse)
def vista_escanear_movil(frutal_id: int, request: Request, db: Session = Depends(get_db)):
    frutal = db.query(RegistroFrutal).filter(RegistroFrutal.id == frutal_id).first()
    if not frutal:
        raise HTTPException(status_code=404, detail="Frutal no encontrado")
    
    operadores = db.query(Operador).filter(Operador.activo == True).all()
    riegos = db.query(RiegoCampo).filter(RiegoCampo.frutal_id == frutal_id).order_by(RiegoCampo.fecha_aplicacion.desc()).limit(5).all()

    return templates.TemplateResponse(
        request=request,
        name="escaner_movil.html",
        context={
            "frutal": frutal,
            "operadores": operadores,
            "riegos": riegos
        }
    )

@app.post("/api/riego-campo/")
def registrar_riego_campo(
    frutal_id: int = Form(None),
    operador_id: int = Form(...),
    volumen_litros: float = Form(...),
    observaciones: str = Form(""),
    db: Session = Depends(get_db)
):
    nuevo_riego = RiegoCampo(
        fecha_aplicacion=datetime.utcnow(),
        volumen_litros=volumen_litros,
        frutal_id=frutal_id,
        operador_id=operador_id,
        observaciones=observaciones
    )
    db.add(nuevo_riego)
    db.commit()
    
    return RedirectResponse(url=f"/escanear/{frutal_id}", status_code=status.HTTP_303_SEE_OTHER)


# ==========================================
#        MÓDULO DE CASA MALLA
# ==========================================

@app.post("/api/catalogo-cultivo/")
def agregar_cultivo_catalogo(
    especie_variedad: str = Form(...),
    dias_a_trasplante: int = Form(...),
    dias_a_cosecha: int = Form(...),
    db: Session = Depends(get_db)
):
    nuevo_cultivo = CatalogoCultivo(
        especie_variedad=especie_variedad,
        dias_a_trasplante=dias_a_trasplante,
        dias_a_cosecha=dias_a_cosecha
    )
    db.add(nuevo_cultivo)
    db.commit()
    return {"status": "success", "mensaje": "Cultivo agregado al catálogo"}

@app.post("/api/registro-casa-malla/")
def registrar_casa_malla(
    identificador_cama: str = Form(...),
    cultivo_id: int = Form(...),
    fecha_semillero: str = Form(...),
    observaciones: str = Form(""),
    db: Session = Depends(get_db)
):
    cultivo = db.query(CatalogoCultivo).filter(CatalogoCultivo.id == cultivo_id).first()
    if not cultivo:
        raise HTTPException(status_code=404, detail="Cultivo no encontrado en el catálogo")
    fecha_semillero_dt = datetime.strptime(fecha_semillero, "%Y-%m-%d")
    fecha_trasplante_est = fecha_semillero_dt + timedelta(days=cultivo.dias_a_trasplante)
    fecha_cosecha_est = fecha_trasplante_est + timedelta(days=cultivo.dias_a_cosecha)

    nuevo_registro = RegistroCasaMalla(
        identificador_cama=identificador_cama,
        cultivo_id=cultivo_id,
        fecha_semillero=fecha_semillero_dt,
        fecha_trasplante_estimada=fecha_trasplante
