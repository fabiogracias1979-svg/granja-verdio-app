import json
import io
import pandas as pd
import qrcode
from datetime import datetime, timedelta
from fastapi import FastAPI, UploadFile, File, Form, Depends, Request, HTTPException, Query, Response, status
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import List, Optional
from sqlalchemy import text
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

class RegistroOfflineItem(BaseModel):
    arbol_id: int
    fecha: str
    tipo_actividad: str
    descripcion: str

class LoteOffline(BaseModel):
    registros: List[RegistroOfflineItem]

class EdicionFrutal(BaseModel):
    especie_variedad: str
    lote_sector: str
    coordenadas: Optional[str] = ""
    fecha_siembra: Optional[str] = ""

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
    operadores = db.query(Operador).filter(Operador.activo == True).all()
    return templates.TemplateResponse(
        request=request, 
        name="formulario.html",
        context={"operadores": operadores}
    )

@app.get("/registros", response_class=HTMLResponse)
def ver_registros(request: Request, db: Session = Depends(get_db)):
    arboles_sql = db.execute(text("SELECT * FROM catalogo_frutales ORDER BY id ASC")).fetchall()
    
    registros = []
    for row in arboles_sql:
        item = dict(row._mapping)
        
        # Última foto real registrada en bitacora_frutales
        ultima_foto = db.execute(
            text("""
                SELECT enlace_foto FROM bitacora_frutales 
                WHERE arbol_id = :aid AND enlace_foto LIKE 'http%' 
                ORDER BY fecha DESC, id DESC LIMIT 1
            """),
            {"aid": item["id"]}
        ).fetchone()
        
        # Último evento fenológico o de estado del árbol (incluye Muerto / Resiembra)
        evento_feno = db.execute(
            text("""
                SELECT * FROM bitacora_frutales 
                WHERE arbol_id = :aid 
                  AND LOWER(tipo_actividad) NOT LIKE '%riego%' 
                  AND LOWER(tipo_actividad) NOT LIKE '%humedad%'
                  AND LOWER(tipo_actividad) NOT LIKE '%foto%'
                ORDER BY fecha DESC, id DESC LIMIT 1
            """),
            {"aid": item["id"]}
        ).fetchone()
        feno_dict = dict(evento_feno._mapping) if evento_feno else {}
        
        # Último riego registrado en bitacora_frutales
        ultimo_riego_bitacora = db.execute(
            text("""
                SELECT * FROM bitacora_frutales 
                WHERE arbol_id = :aid AND LOWER(tipo_actividad) LIKE '%riego%' 
                ORDER BY fecha DESC, id DESC LIMIT 1
            """),
            {"aid": item["id"]}
        ).fetchone()
        
        # Último chequeo de humedad registrado
        ultimo_chequeo = db.execute(
            text("""
                SELECT * FROM bitacora_frutales 
                WHERE arbol_id = :aid AND LOWER(tipo_actividad) LIKE '%humedad%' 
                ORDER BY fecha DESC, id DESC LIMIT 1
            """),
            {"aid": item["id"]}
        ).fetchone()

        # Historial completo cronológico para consultar en el modal
        historial_sql = db.execute(
            text("""
                SELECT id, fecha, tipo_actividad, descripcion, enlace_foto 
                FROM bitacora_frutales 
                WHERE arbol_id = :aid 
                ORDER BY fecha DESC, id DESC
            """),
            {"aid": item["id"]}
        ).fetchall()
        
        historial_lista = []
        for h in historial_sql:
            hd = dict(h._mapping)
            historial_lista.append({
                "fecha": str(hd.get("fecha") or "")[:10],
                "tipo": hd.get("tipo_actividad") or "Evento",
                "descripcion": hd.get("descripcion") or "",
                "foto": hd.get("enlace_foto") if str(hd.get("enlace_foto") or "").startswith("http") else ""
            })
        
        etapa_actual = feno_dict.get("tipo_actividad") or "Crecimiento Vegetativo"
        item["etapa_fenologica"] = etapa_actual
        item["es_muerto"] = "muerto" in etapa_actual.lower()
        item["imagen_drive_url"] = ultima_foto._mapping["enlace_foto"] if ultima_foto else "Sin imagen disponible"
        item["historial_json"] = json.dumps(historial_lista, ensure_ascii=False)
        
        if ultimo_riego_bitacora:
            r_dict = dict(ultimo_riego_bitacora._mapping)
            item["ultimo_riego"] = {
                "detalle": r_dict.get("descripcion") or "Riego aplicado",
                "fecha": str(r_dict.get("fecha") or "")[:10]
            }
        else:
            item["ultimo_riego"] = None

        if ultimo_chequeo:
            c_dict = dict(ultimo_chequeo._mapping)
            item["ultima_humedad"] = f"{c_dict.get('descripcion')} ({str(c_dict.get('fecha') or '')[:10]})"
        else:
            item["ultima_humedad"] = None
            
        registros.append(item)

    return templates.TemplateResponse(
        request=request, 
        name="registros.html", 
        context={"registros": registros}
    )

@app.put("/api/catalogo-frutales/{arbol_id}")
def editar_frutal_catalogo(arbol_id: int, datos: EdicionFrutal, db: Session = Depends(get_db)):
    existe = db.execute(text("SELECT id FROM catalogo_frutales WHERE id = :aid"), {"aid": arbol_id}).fetchone()
    if not existe:
        raise HTTPException(status_code=404, detail="Árbol no encontrado en el catálogo")

    db.execute(
        text("""
            UPDATE catalogo_frutales
            SET especie_variedad = :especie,
                lote_sector = :sector,
                coordenadas = :coords,
                fecha_siembra = :fecha
            WHERE id = :aid
        """),
        {
            "especie": datos.especie_variedad.strip(),
            "sector": datos.lote_sector.strip(),
            "coords": (datos.coordenadas or "").strip(),
            "fecha": (datos.fecha_siembra or "").strip(),
            "aid": arbol_id
        }
    )
    db.commit()
    return {"status": "success", "mensaje": f"Árbol #{arbol_id} actualizado correctamente"}

@app.post("/api/sincronizar-offline")
def sincronizar_offline(lote: LoteOffline, db: Session = Depends(get_db)):
    insertados = 0
    for item in lote.registros:
        db.execute(
            text("""
                INSERT INTO bitacora_frutales (arbol_id, fecha, tipo_actividad, descripcion, enlace_foto)
                VALUES (:arbol_id, :fecha, :tipo_actividad, :descripcion, :enlace_foto)
            """),
            {
                "arbol_id": item.arbol_id,
                "fecha": item.fecha,
                "tipo_actividad": item.tipo_actividad,
                "descripcion": item.descripcion,
                "enlace_foto": "Registro de campo offline"
            }
        )
        if "resiembra" in item.tipo_actividad.lower() and "muerto" not in item.tipo_actividad.lower():
            db.execute(
                text("UPDATE catalogo_frutales SET fecha_siembra = :fecha WHERE id = :aid"),
                {"fecha": item.fecha, "aid": item.arbol_id}
            )
        insertados += 1
    db.commit()
    return {"status": "success", "sincronizados": insertados}

@app.post("/api/bitacora-frutal/foto")
async def subir_foto_bitacora_frutal(
    arbol_id: int = Form(...),
    fecha_foto: str = Form(None),
    nota_foto: str = Form("Actualización fotográfica de campo"),
    url_externa: str = Form(""),
    archivo: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    drive_url = ""
    url_limpia = (url_externa or "").strip()

    if url_limpia.startswith("http"):
        drive_url = url_limpia
    elif archivo and archivo.filename:
        try:
            res = upload_file_to_drive(archivo.file, archivo.filename, archivo.content_type)
            drive_url = normalizar_url_drive(res)
        except Exception as e:
            raise HTTPException(
                status_code=500, 
                detail=f"Credenciales de Google Drive vencidas o faltantes ({str(e)}). Usa la opción de pegar el enlace directo de Drive abajo."
            )
    else:
        raise HTTPException(status_code=400, detail="Debes seleccionar una imagen o pegar un enlace válido de Google Drive.")

    fecha_registro = fecha_foto.strip() if (fecha_foto and fecha_foto.strip()) else datetime.now().strftime("%Y-%m-%d")
    db.execute(
        text("""
            INSERT INTO bitacora_frutales (arbol_id, fecha, tipo_actividad, descripcion, enlace_foto)
            VALUES (:arbol_id, :fecha, :tipo_actividad, :descripcion, :enlace_foto)
        """),
        {
            "arbol_id": arbol_id,
            "fecha": fecha_registro,
            "tipo_actividad": "Seguimiento Fotográfico",
            "descripcion": nota_foto,
            "enlace_foto": drive_url
        }
    )
    db.commit()

    return JSONResponse(content={
        "status": "success",
        "mensaje": "Fotografía vinculada correctamente al árbol",
        "drive_url": drive_url
    })

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
    operador_id: int = Form(...),
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
        operador_id=operador_id,
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
    arboles_sql = db.execute(text("SELECT * FROM catalogo_frutales ORDER BY id ASC")).fetchall()
    features = []
    for row in arboles_sql:
        r = dict(row._mapping)
        coord_str = str(r.get("coordenadas") or "")
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
                "id": r.get("id"),
                "especie_variedad": r.get("especie_variedad") or "N/A",
                "lote_sector": r.get("lote_sector") or "N/A",
                "fecha_siembra": str(r.get("fecha_siembra") or ""),
                "registrado_por": r.get("registrado_por") or "N/A"
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

@app.get("/exportar/excel")
@app.get("/export/excel")
def export_excel(db: Session = Depends(get_db)):
    arboles_sql = db.execute(text("SELECT * FROM catalogo_frutales ORDER BY id ASC")).fetchall()
    
    data = []
    for row in arboles_sql:
        r = dict(row._mapping)
        data.append({
            "ID": r.get("id"),
            "Registrado Por": r.get("registrado_por") or "",
            "Especie / Variedad": r.get("especie_variedad") or "",
            "Lote / Sector": r.get("lote_sector") or "",
            "Fecha Siembra": str(r.get("fecha_siembra") or ""),
            "Coordenadas": r.get("coordenadas") or ""
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
    arbol = db.execute(text("SELECT * FROM catalogo_frutales WHERE id = :fid"), {"fid": frutal_id}).fetchone()
    if not arbol:
        raise HTTPException(status_code=404, detail="Frutal no encontrado")

    base_url = str(request.base_url).rstrip("/")
    destino_url = f"{base_url}/escanear/{frutal_id}"

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
    primer_frutal = db.execute(text("SELECT id FROM catalogo_frutales ORDER BY id ASC LIMIT 1")).fetchone()
    if primer_frutal:
        return RedirectResponse(url=f"/placa/frutal/{primer_frutal._mapping['id']}", status_code=status.HTTP_303_SEE_OTHER)
    return HTMLResponse("<h3>Aún no hay frutales registrados en el sistema.</h3>", status_code=404)

@app.get("/placa/frutal/{frutal_id}", response_class=HTMLResponse)
def ver_placa_imprimible(frutal_id: int, request: Request, db: Session = Depends(get_db)):
    arbol = db.execute(text("SELECT * FROM catalogo_frutales WHERE id = :fid"), {"fid": frutal_id}).fetchone()
    if not arbol:
        raise HTTPException(status_code=404, detail="Frutal no encontrado")
        
    return templates.TemplateResponse(
        request=request,
        name="placa_qr.html",
        context={"frutal": dict(arbol._mapping)}
    )

# ==========================================
#        MÓDULO DE ESCANEO MÓVIL Y CAMPO
# ==========================================

@app.get("/escanear/{frutal_id}", response_class=HTMLResponse)
def vista_escanear_movil(frutal_id: int, request: Request, db: Session = Depends(get_db)):
    arbol = db.execute(text("SELECT * FROM catalogo_frutales WHERE id = :fid"), {"fid": frutal_id}).fetchone()
    if not arbol:
        raise HTTPException(status_code=404, detail="Frutal no encontrado")
    
    operadores = db.query(Operador).filter(Operador.activo == True).all()
    riegos = db.query(RiegoCampo).filter(RiegoCampo.frutal_id == frutal_id).order_by(RiegoCampo.fecha_aplicacion.desc()).limit(5).all()

    return templates.TemplateResponse(
        request=request,
        name="escaner_movil.html",
        context={
            "frutal": dict(arbol._mapping),
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
        fecha_trasplante_estimada=fecha_trasplante_est,
        fecha_cosecha_estimada=fecha_cosecha_est,
        observaciones=observaciones,
        estado="Semillero"
    )
    db.add(nuevo_registro)
    db.commit()
    return {
        "status": "success",
        "mensaje": "Siembra registrada con éxito.",
        "fechas_calculadas": {
            "trasplante_esperado": fecha_trasplante_est.strftime("%Y-%m-%d"),
            "cosecha_esperada": fecha_cosecha_est.strftime("%Y-%m-%d")
        }
    }

@app.post("/api/bitacora-manejo/")
def registrar_bitacora(
    casa_malla_id: int = Form(...),
    fecha_aplicacion: str = Form(...),
    tipo_insumo_labor: str = Form(...),
    dosis_cantidad: str = Form(""),
    motivo: str = Form(""),
    observaciones: str = Form(""),
    db: Session = Depends(get_db)
):
    registro_cama = db.query(RegistroCasaMalla).filter(RegistroCasaMalla.id == casa_malla_id).first()
    if not registro_cama:
        raise HTTPException(status_code=404, detail="El registro del bancal no existe.")
    fecha_dt = datetime.strptime(fecha_aplicacion, "%Y-%m-%d")

    nueva_bitacora = BitacoraManejo(
        casa_malla_id=casa_malla_id,
        fecha_aplicacion=fecha_dt,
        tipo_insumo_labor=tipo_insumo_labor,
        dosis_cantidad=dosis_cantidad,
        motivo=motivo,
        observaciones=observaciones
    )
    db.add(nueva_bitacora)
    db.commit()
    return {"status": "success", "mensaje": "Manejo registrado correctamente en la bitácora."}

# ==========================================
#  MÓDULO DE INFRAESTRUCTURA Y RECURSOS
# ==========================================

@app.post("/api/infraestructura/")
async def registrar_infraestructura(
    nombre_obra: str = Form(...),
    categoria: str = Form(...),
    estado: str = Form("Operativa"),
    capacidad_instalada: str = Form(""),
    materiales_clave: str = Form(""),
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
            
    nueva_obra = Infraestructura(
        nombre_obra=nombre_obra,
        categoria=categoria,
        estado=estado,
        capacidad_instalada=capacidad_instalada,
        materiales_clave=materiales_clave,
        coordenadas=coordenadas,
        imagen_drive_url=drive_url
    )
    
    db.add(nueva_obra)
    db.commit()
    db.refresh(nueva_obra)
    
    return JSONResponse(content={"status": "success", "mensaje": f"{nombre_obra} registrada exitosamente", "id": nueva_obra.id})

@app.post("/api/registro-agua/")
def registrar_agua(
    infraestructura_id: int = Form(...),
    fecha_registro: str = Form(...),
    tipo_movimiento: str = Form(...),
    volumen_litros: int = Form(0),
    observaciones: str = Form(""),
    db: Session = Depends(get_db)
):
    obra = db.query(Infraestructura).filter(Infraestructura.id == infraestructura_id).first()
    if not obra:
        raise HTTPException(status_code=404, detail="La infraestructura especificada no existe.")
        
    fecha_dt = datetime.strptime(fecha_registro, "%Y-%m-%d")
    
    nuevo_movimiento = RegistroAgua(
        infraestructura_id=infraestructura_id,
        fecha_registro=fecha_dt,
        tipo_movimiento=tipo_movimiento,
        volumen_litros=volumen_litros,
        observaciones=observaciones
    )
    
    db.add(nuevo_movimiento)
    db.commit()
    
    return {"status": "success", "mensaje": "Movimiento de agua registrado correctamente."}

# ==========================================
#      MÓDULO DE CLIMA Y PLUVIOMETRÍA
# ==========================================

@app.get("/clima", response_class=HTMLResponse)
def ver_clima(request: Request, db: Session = Depends(get_db)):
    registros = db.query(RegistroClima).order_by(RegistroClima.fecha_medicion.desc()).all()
    return templates.TemplateResponse(
        request=request, 
        name="clima.html", 
        context={"registros": registros}
    )

@app.post("/api/registro-clima/")
def registrar_clima(
    fecha_medicion: str = Form(...),
    precipitacion_mm: float = Form(None),
    temperatura_min: float = Form(None),
    temperatura_max: float = Form(None),
    humedad_relativa: float = Form(None),
    eventos_extremos: str = Form(""),
    observaciones: str = Form(""),
    db: Session = Depends(get_db)
):
    fecha_dt = datetime.strptime(fecha_medicion, "%Y-%m-%d")
    
    nuevo_registro = RegistroClima(
        fecha_medicion=fecha_dt,
        precipitacion_mm=precipitacion_mm,
        temperatura_min=temperatura_min,
        temperatura_max=temperatura_max,
        humedad_relativa=humedad_relativa,
        eventos_extremos=eventos_extremos,
        observaciones=observaciones
    )
    
    db.add(nuevo_registro)
    db.commit()
    db.refresh(nuevo_registro)
    
    return {"status": "success", "mensaje": "Datos climáticos registrados correctamente."}

# ==========================================
#   CONFIGURACIÓN DINÁMICA: OPERADORES E INSUMOS
# ==========================================

@app.get("/configuracion", response_class=HTMLResponse)
@app.get("/configuracion/", response_class=HTMLResponse)
def vista_configuracion(request: Request, db: Session = Depends(get_db)):
    operadores = db.query(Operador).order_by(Operador.nombre.asc()).all()
    insumos = db.query(InsumoOrganico).order_by(InsumoOrganico.nombre.asc()).all()
    return templates.TemplateResponse(
        request=request,
        name="configuracion.html",
        context={
            "operadores": operadores,
            "insumos": insumos
        }
    )

@app.post("/api/configuracion/operadores")
def crear_operador(
    nombre: str = Form(...),
    rol: str = Form("Técnico de Campo"),
    db: Session = Depends(get_db)
):
    nombre_limpio = nombre.strip()
    existe = db.query(Operador).filter(Operador.nombre.ilike(nombre_limpio)).first()
    if not existe:
        nuevo_op = Operador(nombre=nombre_limpio, rol=rol, activo=True)
        db.add(nuevo_op)
        db.commit()
    return RedirectResponse(url="/configuracion", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/api/configuracion/operadores/{operador_id}/toggle")
def toggle_operador(operador_id: int, db: Session = Depends(get_db)):
    op = db.query(Operador).filter(Operador.id == operador_id).first()
    if op:
        op.activo = not op.activo
        db.commit()
    return RedirectResponse(url="/configuracion", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/api/configuracion/insumos")
def crear_insumo(
    nombre: str = Form(...),
    categoria: str = Form(...),
    dias_carencia: int = Form(0),
    dosis_recomendada: str = Form(None),
    db: Session = Depends(get_db)
):
    nombre_limpio = nombre.strip()
    existe = db.query(InsumoOrganico).filter(InsumoOrganico.nombre.ilike(nombre_limpio)).first()
    if not existe:
        nuevo_ins = InsumoOrganico(
            nombre=nombre_limpio,
            categoria=categoria,
            dias_carencia=dias_carencia,
            dosis_recomendada=dosis_recomendada,
            activo=True
        )
        db.add(nuevo_ins)
        db.commit()
    return RedirectResponse(url="/configuracion", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/api/configuracion/insumos/{insumo_id}/toggle")
def toggle_insumo(insumo_id: int, db: Session = Depends(get_db)):
    ins = db.query(InsumoOrganico).filter(InsumoOrganico.id == insumo_id).first()
    if ins:
        ins.activo = not ins.activo
        db.commit()
    return RedirectResponse(url="/configuracion", status_code=status.HTTP_303_SEE_OTHER)

# ==========================================
#   ZONA DE PELIGRO: REINICIO DE BASE DE DATOS
# ==========================================

@app.get("/limpiar-base-de-datos-total")
def limpiar_bd():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    return {"status": "Éxito", "mensaje": "Base de datos reseteada a CERO. Lista para El Paisnal."}
