from sqlalchemy import text

@app.get("/registros", response_class=HTMLResponse)
def ver_registros(request: Request, db: Session = Depends(get_db)):
    # 1. Leer los 22 árboles desde la tabla inyectada catalogo_frutales
    arboles_sql = db.execute(text("SELECT * FROM catalogo_frutales ORDER BY id ASC")).fetchall()
    
    registros = []
    for row in arboles_sql:
        item = dict(row._mapping)
        
        # 2. Buscar el último evento registrado en bitacora_frutales para este árbol
        ultimo_evento = db.execute(
            text("SELECT * FROM bitacora_frutales WHERE arbol_id = :aid ORDER BY fecha DESC LIMIT 1"),
            {"aid": item["id"]}
        ).fetchone()
        
        evento = dict(ultimo_evento._mapping) if ultimo_evento else {}
        
        # 3. Adaptar las columnas para que registros.html las muestre sin errores
        item["etapa_fenologica"] = evento.get("tipo_actividad") or "Sin actividad"
        item["estado_fitosanitario"] = "Óptimo / Sano"
        item["imagen_drive_url"] = evento.get("enlace_foto") or "Sin imagen disponible"
        item["ultimo_riego"] = None
        
        registros.append(item)

    return templates.TemplateResponse(
        request=request, 
        name="registros.html", 
        context={"registros": registros}
    )
