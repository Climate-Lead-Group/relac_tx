"""
Datos de flujos de energía recopilados de internet.
Estos datos complementan los del archivo Matriz_Bilateral_Electricidad.xlsx
"""

# Diccionario de datos recopilados de internet
# Formato: (Año, País Salida, País Entrada): {"energia": GWh, "notas": str, "fuente": str}
DATOS_INTERNET = {
    # =========================================================================
    # ARGENTINA - BOLIVIA
    # La interconexión Juana Azurduy se completó en 2022 e inició operaciones en marzo 2023
    # =========================================================================
    (2021, "Argentina", "Bolivia"): {
        "energia": 0,
        "notas": "Sin interconexión operativa",
        "fuente": "https://www.mejorenergia.com.ar/noticias/2023/03/21/1106-por-primera-vez-bolivia-exporta-energia-electrica-al-norte-argentino"
    },
    (2021, "Bolivia", "Argentina"): {
        "energia": 0,
        "notas": "Sin interconexión operativa",
        "fuente": "https://www.mejorenergia.com.ar/noticias/2023/03/21/1106-por-primera-vez-bolivia-exporta-energia-electrica-al-norte-argentino"
    },
    (2022, "Argentina", "Bolivia"): {
        "energia": 0,
        "notas": "Interconexión en construcción",
        "fuente": "https://www.mejorenergia.com.ar/noticias/2023/03/21/1106-por-primera-vez-bolivia-exporta-energia-electrica-al-norte-argentino"
    },
    (2022, "Bolivia", "Argentina"): {
        "energia": 0,
        "notas": "Interconexión en construcción",
        "fuente": "https://www.mejorenergia.com.ar/noticias/2023/03/21/1106-por-primera-vez-bolivia-exporta-energia-electrica-al-norte-argentino"
    },
    (2023, "Argentina", "Bolivia"): {
        "energia": 0,
        "notas": "Flujo unidireccional Bolivia→Argentina",
        "fuente": "https://www.la-razon.com/economia/2025/02/28/en-2024-bolivia-exporto-energia-electrica-a-argentina-por-bs-1241-millones/"
    },
    (2023, "Bolivia", "Argentina"): {
        "energia": 70,
        "notas": "Estimado (inicio marzo 2023, ~60 MW)",
        "fuente": "https://www.mejorenergia.com.ar/noticias/2023/03/21/1106-por-primera-vez-bolivia-exporta-energia-electrica-al-norte-argentino"
    },
    (2024, "Argentina", "Bolivia"): {
        "energia": 0,
        "notas": "Flujo unidireccional Bolivia→Argentina",
        "fuente": "https://www.la-razon.com/economia/2025/02/28/en-2024-bolivia-exporto-energia-electrica-a-argentina-por-bs-1241-millones/"
    },
    (2024, "Bolivia", "Argentina"): {
        "energia": 188.6,
        "notas": "LISTO",
        "fuente": "https://www.la-razon.com/economia/2025/02/28/en-2024-bolivia-exporto-energia-electrica-a-argentina-por-bs-1241-millones/"
    },

    # =========================================================================
    # ARGENTINA - BRASIL
    # =========================================================================
    (2021, "Argentina", "Brasil"): {
        "energia": 3795,
        "notas": "Crisis hídrica Brasil",
        "fuente": "https://mase.lmneuquen.com/exportaciones/crecieron-las-exportaciones-energia-electrica-brasil-n857730"
    },
    (2021, "Brasil", "Argentina"): {
        "energia": 0,
        "notas": "Crisis hídrica Brasil",
        "fuente": "https://mase.lmneuquen.com/exportaciones/crecieron-las-exportaciones-energia-electrica-brasil-n857730"
    },
    (2022, "Argentina", "Brasil"): {
        "energia": 50,
        "notas": "Estimado - Intercambio estacional",
        "fuente": "https://www.infobae.com/economia/2022/11/24/nuevo-acuerdo-entre-argentina-y-brasil-para-el-intercambio-de-energia-electrica/"
    },
    (2022, "Brasil", "Argentina"): {
        "energia": 200,
        "notas": "Estimado - Intercambio estacional",
        "fuente": "https://www.infobae.com/economia/2022/11/24/nuevo-acuerdo-entre-argentina-y-brasil-para-el-intercambio-de-energia-electrica/"
    },
    (2023, "Argentina", "Brasil"): {
        "energia": 10.8,
        "notas": "Energía devuelta",
        "fuente": "https://www.infobae.com/economia/2023/11/15/por-que-bajo-en-forma-sustancial-la-importacion-de-energia-electrica-en-los-ultimos-12-meses/"
    },
    (2023, "Brasil", "Argentina"): {
        "energia": 150,
        "notas": "Estimado - Importación invernal",
        "fuente": "https://www.infobae.com/economia/2023/11/15/por-que-bajo-en-forma-sustancial-la-importacion-de-energia-electrica-en-los-ultimos-12-meses/"
    },
    (2024, "Argentina", "Brasil"): {
        "energia": 100,
        "notas": "Estimado",
        "fuente": "https://www.argentina.gob.ar/noticias/argentina-y-brasil-avanzan-en-la-integracion-energetica"
    },
    (2024, "Brasil", "Argentina"): {
        "energia": 50,
        "notas": "Estimado",
        "fuente": "https://www.argentina.gob.ar/noticias/argentina-y-brasil-avanzan-en-la-integracion-energetica"
    },

    # =========================================================================
    # ARGENTINA - CHILE
    # La línea InterAndes estuvo fuera de operación desde 2017, reactivada en 2022
    # =========================================================================
    (2021, "Argentina", "Chile"): {
        "energia": 0,
        "notas": "Línea InterAndes fuera de servicio",
        "fuente": "https://www.df.cl/empresas/energia/ahora-en-df-chile-y-argentina-reactivan-intercambio-de-energia-a"
    },
    (2021, "Chile", "Argentina"): {
        "energia": 0,
        "notas": "Línea InterAndes fuera de servicio",
        "fuente": "https://www.df.cl/empresas/energia/ahora-en-df-chile-y-argentina-reactivan-intercambio-de-energia-a"
    },
    (2022, "Argentina", "Chile"): {
        "energia": 30,
        "notas": "Estimado - Reactivación línea InterAndes",
        "fuente": "https://www.ambito.com/energia/energia/reactivan-intercambio-chile-y-argentina-n5582684"
    },
    (2022, "Chile", "Argentina"): {
        "energia": 20,
        "notas": "Estimado - Reactivación línea InterAndes",
        "fuente": "https://www.ambito.com/energia/energia/reactivan-intercambio-chile-y-argentina-n5582684"
    },
    (2023, "Argentina", "Chile"): {
        "energia": 46.36,
        "notas": "Intercambio neto hacia Argentina",
        "fuente": "https://www.coordinador.cl/wp-content/uploads/2024/04/CEN-ReporteArt72-15ano2023v2.pdf"
    },
    (2023, "Chile", "Argentina"): {
        "energia": 0,
        "notas": "Intercambio neto hacia Argentina",
        "fuente": "https://www.coordinador.cl/wp-content/uploads/2024/04/CEN-ReporteArt72-15ano2023v2.pdf"
    },
    (2024, "Argentina", "Chile"): {
        "energia": 50,
        "notas": "Estimado",
        "fuente": "https://energia.gob.cl/noticias/nacional/chile-y-argentina-acuerdan-intercambio-energetico"
    },
    (2024, "Chile", "Argentina"): {
        "energia": 30,
        "notas": "Estimado",
        "fuente": "https://energia.gob.cl/noticias/nacional/chile-y-argentina-acuerdan-intercambio-energetico"
    },

    # =========================================================================
    # ARGENTINA - URUGUAY (complemento a datos existentes)
    # =========================================================================
    (2023, "Argentina", "Uruguay"): {
        "energia": 0,
        "notas": "Uruguay exportador neto",
        "fuente": "https://adme.com.uy/db-docs/Docs_secciones/nid_526/Informe_Anual_2023.pdf"
    },
    (2023, "Uruguay", "Argentina"): {
        "energia": 213.6,
        "notas": "LISTO",
        "fuente": "https://adme.com.uy/db-docs/Docs_secciones/nid_526/Informe_Anual_2023.pdf"
    },
    (2024, "Argentina", "Uruguay"): {
        "energia": 0,
        "notas": "Uruguay exportador neto",
        "fuente": "https://enperspectiva.uy/en-perspectiva-programa/analisis-exante/energia-electrica-cuales-fueron-las-claves-de-este-mercado-en-2024-exante/"
    },
    (2024, "Uruguay", "Argentina"): {
        "energia": 1500,
        "notas": "Estimado (~2000 GWh total exportado)",
        "fuente": "https://enperspectiva.uy/en-perspectiva-programa/analisis-exante/energia-electrica-cuales-fueron-las-claves-de-este-mercado-en-2024-exante/"
    },

    # =========================================================================
    # BOLIVIA - CHILE (Sin interconexión activa)
    # =========================================================================
    (2021, "Bolivia", "Chile"): {
        "energia": 0,
        "notas": "Sin interconexión",
        "fuente": "https://energia.gob.cl/noticias/nacional/inicio-de-estudio-de-alternativas-de-interconexion-entre-chile-y-bolivia"
    },
    (2021, "Chile", "Bolivia"): {
        "energia": 0,
        "notas": "Sin interconexión",
        "fuente": "https://energia.gob.cl/noticias/nacional/inicio-de-estudio-de-alternativas-de-interconexion-entre-chile-y-bolivia"
    },
    (2022, "Bolivia", "Chile"): {
        "energia": 0,
        "notas": "Sin interconexión",
        "fuente": "https://energia.gob.cl/noticias/nacional/inicio-de-estudio-de-alternativas-de-interconexion-entre-chile-y-bolivia"
    },
    (2022, "Chile", "Bolivia"): {
        "energia": 0,
        "notas": "Sin interconexión",
        "fuente": "https://energia.gob.cl/noticias/nacional/inicio-de-estudio-de-alternativas-de-interconexion-entre-chile-y-bolivia"
    },
    (2023, "Bolivia", "Chile"): {
        "energia": 0,
        "notas": "Sin interconexión",
        "fuente": "https://energia.gob.cl/noticias/nacional/inicio-de-estudio-de-alternativas-de-interconexion-entre-chile-y-bolivia"
    },
    (2023, "Chile", "Bolivia"): {
        "energia": 0,
        "notas": "Sin interconexión",
        "fuente": "https://energia.gob.cl/noticias/nacional/inicio-de-estudio-de-alternativas-de-interconexion-entre-chile-y-bolivia"
    },
    (2024, "Bolivia", "Chile"): {
        "energia": 0,
        "notas": "Sin interconexión",
        "fuente": "https://energia.gob.cl/noticias/nacional/inicio-de-estudio-de-alternativas-de-interconexion-entre-chile-y-bolivia"
    },
    (2024, "Chile", "Bolivia"): {
        "energia": 0,
        "notas": "Sin interconexión",
        "fuente": "https://energia.gob.cl/noticias/nacional/inicio-de-estudio-de-alternativas-de-interconexion-entre-chile-y-bolivia"
    },

    # =========================================================================
    # BOLIVIA - PERU (Sin interconexión significativa)
    # =========================================================================
    (2021, "Bolivia", "Perú"): {
        "energia": 0,
        "notas": "Sin interconexión significativa",
        "fuente": "https://mediamonitor.com.bo/2024/11/18/integracion-energetica-oportunidades-y-retos-para-bolivia/"
    },
    (2021, "Perú", "Bolivia"): {
        "energia": 0,
        "notas": "Sin interconexión significativa",
        "fuente": "https://mediamonitor.com.bo/2024/11/18/integracion-energetica-oportunidades-y-retos-para-bolivia/"
    },
    (2022, "Bolivia", "Perú"): {
        "energia": 0,
        "notas": "Sin interconexión significativa",
        "fuente": "https://mediamonitor.com.bo/2024/11/18/integracion-energetica-oportunidades-y-retos-para-bolivia/"
    },
    (2022, "Perú", "Bolivia"): {
        "energia": 0,
        "notas": "Sin interconexión significativa",
        "fuente": "https://mediamonitor.com.bo/2024/11/18/integracion-energetica-oportunidades-y-retos-para-bolivia/"
    },
    (2023, "Bolivia", "Perú"): {
        "energia": 0,
        "notas": "Sin interconexión significativa",
        "fuente": "https://mediamonitor.com.bo/2024/11/18/integracion-energetica-oportunidades-y-retos-para-bolivia/"
    },
    (2023, "Perú", "Bolivia"): {
        "energia": 0,
        "notas": "Sin interconexión significativa",
        "fuente": "https://mediamonitor.com.bo/2024/11/18/integracion-energetica-oportunidades-y-retos-para-bolivia/"
    },
    (2024, "Bolivia", "Perú"): {
        "energia": 0,
        "notas": "Sin interconexión significativa",
        "fuente": "https://mediamonitor.com.bo/2024/11/18/integracion-energetica-oportunidades-y-retos-para-bolivia/"
    },
    (2024, "Perú", "Bolivia"): {
        "energia": 0,
        "notas": "Sin interconexión significativa",
        "fuente": "https://mediamonitor.com.bo/2024/11/18/integracion-energetica-oportunidades-y-retos-para-bolivia/"
    },

    # =========================================================================
    # BRASIL - PARAGUAY (Itaipú - cesión de energía)
    # =========================================================================
    (2021, "Paraguay", "Brasil"): {
        "energia": 35000,
        "notas": "Cesión Itaipú (estimado)",
        "fuente": "https://www.abc.com.py/economia/2023/12/11/paraguay-aun-cede-al-brasil-el-63-de-su-energia-en-la-central-itaipu/"
    },
    (2021, "Brasil", "Paraguay"): {
        "energia": 0,
        "notas": "Flujo unidireccional Paraguay→Brasil",
        "fuente": "https://www.abc.com.py/economia/2023/12/11/paraguay-aun-cede-al-brasil-el-63-de-su-energia-en-la-central-itaipu/"
    },
    (2022, "Paraguay", "Brasil"): {
        "energia": 30000,
        "notas": "Cesión Itaipú (estimado)",
        "fuente": "https://www.abc.com.py/economia/2023/12/11/paraguay-aun-cede-al-brasil-el-63-de-su-energia-en-la-central-itaipu/"
    },
    (2022, "Brasil", "Paraguay"): {
        "energia": 0,
        "notas": "Flujo unidireccional Paraguay→Brasil",
        "fuente": "https://www.abc.com.py/economia/2023/12/11/paraguay-aun-cede-al-brasil-el-63-de-su-energia-en-la-central-itaipu/"
    },
    (2023, "Paraguay", "Brasil"): {
        "energia": 25000,
        "notas": "Cesión Itaipú (estimado)",
        "fuente": "https://www.abc.com.py/economia/2023/12/11/paraguay-aun-cede-al-brasil-el-63-de-su-energia-en-la-central-itaipu/"
    },
    (2023, "Brasil", "Paraguay"): {
        "energia": 0,
        "notas": "Flujo unidireccional Paraguay→Brasil",
        "fuente": "https://www.abc.com.py/economia/2023/12/11/paraguay-aun-cede-al-brasil-el-63-de-su-energia-en-la-central-itaipu/"
    },
    (2024, "Paraguay", "Brasil"): {
        "energia": 13161,
        "notas": "Cesión Itaipú",
        "fuente": "https://www.ip.gov.py/ip/2025/01/09/itaipu-suministro-20-383-gwh-de-energia-electrica-a-paraguay-en-el-2024/"
    },
    (2024, "Brasil", "Paraguay"): {
        "energia": 0,
        "notas": "Flujo unidireccional Paraguay→Brasil",
        "fuente": "https://www.ip.gov.py/ip/2025/01/09/itaipu-suministro-20-383-gwh-de-energia-electrica-a-paraguay-en-el-2024/"
    },

    # =========================================================================
    # BRASIL - URUGUAY
    # =========================================================================
    (2022, "Brasil", "Uruguay"): {
        "energia": 100,
        "notas": "Estimado",
        "fuente": "https://adme.com.uy/db-docs/Docs_secciones/nid_526/Informe_Anual_2023.pdf"
    },
    (2022, "Uruguay", "Brasil"): {
        "energia": 50,
        "notas": "Estimado",
        "fuente": "https://adme.com.uy/db-docs/Docs_secciones/nid_526/Informe_Anual_2023.pdf"
    },
    (2023, "Brasil", "Uruguay"): {
        "energia": 1398,
        "notas": "Importación por sequía",
        "fuente": "https://adme.com.uy/db-docs/Docs_secciones/nid_526/Informe_Anual_2023.pdf"
    },
    (2023, "Uruguay", "Brasil"): {
        "energia": 17.3,
        "notas": "LISTO",
        "fuente": "https://adme.com.uy/db-docs/Docs_secciones/nid_526/Informe_Anual_2023.pdf"
    },
    (2024, "Brasil", "Uruguay"): {
        "energia": 50,
        "notas": "Estimado - Flujos mínimos",
        "fuente": "https://enperspectiva.uy/en-perspectiva-programa/analisis-exante/energia-electrica-cuales-fueron-las-claves-de-este-mercado-en-2024-exante/"
    },
    (2024, "Uruguay", "Brasil"): {
        "energia": 500,
        "notas": "Estimado",
        "fuente": "https://enperspectiva.uy/en-perspectiva-programa/analisis-exante/energia-electrica-cuales-fueron-las-claves-de-este-mercado-en-2024-exante/"
    },

    # =========================================================================
    # CHILE - PERU (Sin interconexión activa)
    # =========================================================================
    (2021, "Chile", "Perú"): {
        "energia": 0,
        "notas": "Sin interconexión operativa",
        "fuente": "https://www.comunidadandina.org/temas/dg-tis/interconexion-electrica/"
    },
    (2021, "Perú", "Chile"): {
        "energia": 0,
        "notas": "Sin interconexión operativa",
        "fuente": "https://www.comunidadandina.org/temas/dg-tis/interconexion-electrica/"
    },
    (2022, "Chile", "Perú"): {
        "energia": 0,
        "notas": "Sin interconexión operativa",
        "fuente": "https://www.comunidadandina.org/temas/dg-tis/interconexion-electrica/"
    },
    (2022, "Perú", "Chile"): {
        "energia": 0,
        "notas": "Sin interconexión operativa",
        "fuente": "https://www.comunidadandina.org/temas/dg-tis/interconexion-electrica/"
    },
    (2023, "Chile", "Perú"): {
        "energia": 0,
        "notas": "Sin interconexión operativa",
        "fuente": "https://www.comunidadandina.org/temas/dg-tis/interconexion-electrica/"
    },
    (2023, "Perú", "Chile"): {
        "energia": 0,
        "notas": "Sin interconexión operativa",
        "fuente": "https://www.comunidadandina.org/temas/dg-tis/interconexion-electrica/"
    },
    (2024, "Chile", "Perú"): {
        "energia": 0,
        "notas": "Sin interconexión operativa",
        "fuente": "https://www.comunidadandina.org/temas/dg-tis/interconexion-electrica/"
    },
    (2024, "Perú", "Chile"): {
        "energia": 0,
        "notas": "Sin interconexión operativa",
        "fuente": "https://www.comunidadandina.org/temas/dg-tis/interconexion-electrica/"
    },

    # =========================================================================
    # COLOMBIA - ECUADOR
    # =========================================================================
    (2021, "Colombia", "Ecuador"): {
        "energia": 0,
        "notas": "Ver archivo fuente",
        "fuente": "https://www.primicias.ec/noticias/economia/ecuador-exporto-menos-electricidad-colombia-peru/"
    },
    (2021, "Ecuador", "Colombia"): {
        "energia": 461,
        "notas": "Ver archivo fuente",
        "fuente": "https://www.primicias.ec/noticias/economia/ecuador-exporto-menos-electricidad-colombia-peru/"
    },
    (2022, "Colombia", "Ecuador"): {
        "energia": 200,
        "notas": "Estimado",
        "fuente": "https://www.cenace.gob.ec/wp-content/uploads/downloads/2023/04/Parte-1-Informe-Anual-2022.pdf"
    },
    (2022, "Ecuador", "Colombia"): {
        "energia": 300,
        "notas": "Estimado",
        "fuente": "https://www.cenace.gob.ec/wp-content/uploads/downloads/2023/04/Parte-1-Informe-Anual-2022.pdf"
    },
    (2023, "Colombia", "Ecuador"): {
        "energia": 1296.58,
        "notas": "LISTO",
        "fuente": "https://www.cenace.gob.ec/wp-content/uploads/downloads/2024/04/Parte-1-Informe-Anual-CENACE-2023.pdf"
    },
    (2023, "Ecuador", "Colombia"): {
        "energia": 487.6,
        "notas": "LISTO",
        "fuente": "https://www.celec.gob.ec/cocacodo/noticias/entre-febrero-a-julio-de-2023-ecuador-exporto-usd-3213-millones-de-energia-electrica/"
    },
    (2024, "Colombia", "Ecuador"): {
        "energia": 2500,
        "notas": "Estimado - Crisis energética Ecuador",
        "fuente": "https://www.bloomberglinea.com/latinoamerica/colombia/ecuador-y-colombia-mas-alla-de-los-aranceles-la-electricidad-y-el-petroleo-en-juego/"
    },
    (2024, "Ecuador", "Colombia"): {
        "energia": 100,
        "notas": "Estimado - Crisis energética Ecuador",
        "fuente": "https://www.bloomberglinea.com/latinoamerica/colombia/ecuador-y-colombia-mas-alla-de-los-aranceles-la-electricidad-y-el-petroleo-en-juego/"
    },

    # =========================================================================
    # COLOMBIA - PANAMA (Sin interconexión)
    # =========================================================================
    (2021, "Colombia", "Panamá"): {
        "energia": 0,
        "notas": "Sin interconexión construida",
        "fuente": "https://mire.gob.pa/interconexion-electrica-colombia-panama-un-proyecto-que-potencia-la-region/"
    },
    (2021, "Panamá", "Colombia"): {
        "energia": 0,
        "notas": "Sin interconexión construida",
        "fuente": "https://mire.gob.pa/interconexion-electrica-colombia-panama-un-proyecto-que-potencia-la-region/"
    },
    (2022, "Colombia", "Panamá"): {
        "energia": 0,
        "notas": "Sin interconexión construida",
        "fuente": "https://mire.gob.pa/interconexion-electrica-colombia-panama-un-proyecto-que-potencia-la-region/"
    },
    (2022, "Panamá", "Colombia"): {
        "energia": 0,
        "notas": "Sin interconexión construida",
        "fuente": "https://mire.gob.pa/interconexion-electrica-colombia-panama-un-proyecto-que-potencia-la-region/"
    },
    (2023, "Colombia", "Panamá"): {
        "energia": 0,
        "notas": "Sin interconexión construida",
        "fuente": "https://mire.gob.pa/interconexion-electrica-colombia-panama-un-proyecto-que-potencia-la-region/"
    },
    (2023, "Panamá", "Colombia"): {
        "energia": 0,
        "notas": "Sin interconexión construida",
        "fuente": "https://mire.gob.pa/interconexion-electrica-colombia-panama-un-proyecto-que-potencia-la-region/"
    },
    (2024, "Colombia", "Panamá"): {
        "energia": 0,
        "notas": "Sin interconexión construida",
        "fuente": "https://mire.gob.pa/interconexion-electrica-colombia-panama-un-proyecto-que-potencia-la-region/"
    },
    (2024, "Panamá", "Colombia"): {
        "energia": 0,
        "notas": "Sin interconexión construida",
        "fuente": "https://mire.gob.pa/interconexion-electrica-colombia-panama-un-proyecto-que-potencia-la-region/"
    },

    # =========================================================================
    # ECUADOR - PERU
    # =========================================================================
    (2021, "Ecuador", "Perú"): {
        "energia": 40,
        "notas": "Ver archivo fuente",
        "fuente": "https://www.primicias.ec/noticias/economia/ecuador-exporto-menos-electricidad-colombia-peru/"
    },
    (2021, "Perú", "Ecuador"): {
        "energia": 0,
        "notas": "Flujo Ecuador→Perú",
        "fuente": "https://www.primicias.ec/noticias/economia/ecuador-exporto-menos-electricidad-colombia-peru/"
    },
    (2022, "Ecuador", "Perú"): {
        "energia": 20,
        "notas": "Estimado",
        "fuente": "https://www.cenace.gob.ec/wp-content/uploads/downloads/2023/04/Parte-1-Informe-Anual-2022.pdf"
    },
    (2022, "Perú", "Ecuador"): {
        "energia": 0.53,
        "notas": "LISTO",
        "fuente": "https://www.cenace.gob.ec/wp-content/uploads/downloads/2023/04/Parte-1-Informe-Anual-2022.pdf"
    },
    (2023, "Ecuador", "Perú"): {
        "energia": 10.35,
        "notas": "LISTO",
        "fuente": "https://www.celec.gob.ec/cocacodo/noticias/entre-febrero-a-julio-de-2023-ecuador-exporto-usd-3213-millones-de-energia-electrica/"
    },
    (2023, "Perú", "Ecuador"): {
        "energia": 24.37,
        "notas": "LISTO",
        "fuente": "https://www.cenace.gob.ec/wp-content/uploads/downloads/2024/04/Parte-1-Informe-Anual-CENACE-2023.pdf"
    },
    (2024, "Ecuador", "Perú"): {
        "energia": 5,
        "notas": "Estimado - Crisis energética Ecuador",
        "fuente": "https://www.primicias.ec/economia/ecuador-electricidad-colombia-importaciones-compras-aranceles-tasa-seguridad-114355/"
    },
    (2024, "Perú", "Ecuador"): {
        "energia": 50,
        "notas": "Estimado - Crisis energética Ecuador",
        "fuente": "https://www.primicias.ec/economia/ecuador-electricidad-colombia-importaciones-compras-aranceles-tasa-seguridad-114355/"
    },

    # =========================================================================
    # CENTROAMÉRICA - Datos adicionales
    # =========================================================================

    # COSTA RICA - NICARAGUA
    (2022, "Costa Rica", "Nicaragua"): {
        "energia": 81,
        "notas": "LISTO",
        "fuente": "https://apps.grupoice.com/CenceWeb/documentos/3/3008/16/Informe%20%20Anual%20CENCE%202022.pdf"
    },
    (2022, "Nicaragua", "Costa Rica"): {
        "energia": 0.2,
        "notas": "LISTO",
        "fuente": "https://apps.grupoice.com/CenceWeb/documentos/3/3008/16/Informe%20%20Anual%20CENCE%202022.pdf"
    },
    (2023, "Costa Rica", "Nicaragua"): {
        "energia": 150,
        "notas": "Estimado basado en tendencia",
        "fuente": "https://apps.grupoice.com/CenceWeb/"
    },
    (2023, "Nicaragua", "Costa Rica"): {
        "energia": 5,
        "notas": "Estimado basado en tendencia",
        "fuente": "https://apps.grupoice.com/CenceWeb/"
    },
    (2024, "Costa Rica", "Nicaragua"): {
        "energia": 200,
        "notas": "Estimado",
        "fuente": "https://observador.cr/en-2025-aumentara-la-compra-de-electricidad-a-otros-paises-de-la-region-segun-las-previsiones-del-ice/"
    },
    (2024, "Nicaragua", "Costa Rica"): {
        "energia": 10,
        "notas": "Estimado",
        "fuente": "https://observador.cr/en-2025-aumentara-la-compra-de-electricidad-a-otros-paises-de-la-region-segun-las-previsiones-del-ice/"
    },

    # COSTA RICA - PANAMA
    (2022, "Costa Rica", "Panamá"): {
        "energia": 1284,
        "notas": "LISTO",
        "fuente": "https://apps.grupoice.com/CenceWeb/documentos/3/3008/16/Informe%20%20Anual%20CENCE%202022.pdf"
    },
    (2022, "Panamá", "Costa Rica"): {
        "energia": 28,
        "notas": "LISTO",
        "fuente": "https://apps.grupoice.com/CenceWeb/documentos/3/3008/16/Informe%20%20Anual%20CENCE%202022.pdf"
    },
    (2023, "Costa Rica", "Panamá"): {
        "energia": 800,
        "notas": "Estimado basado en tendencia",
        "fuente": "https://apps.grupoice.com/CenceWeb/"
    },
    (2023, "Panamá", "Costa Rica"): {
        "energia": 100,
        "notas": "Estimado basado en tendencia",
        "fuente": "https://apps.grupoice.com/CenceWeb/"
    },
    (2024, "Costa Rica", "Panamá"): {
        "energia": 600,
        "notas": "Estimado",
        "fuente": "https://observador.cr/en-2025-aumentara-la-compra-de-electricidad-a-otros-paises-de-la-region-segun-las-previsiones-del-ice/"
    },
    (2024, "Panamá", "Costa Rica"): {
        "energia": 150,
        "notas": "Estimado",
        "fuente": "https://observador.cr/en-2025-aumentara-la-compra-de-electricidad-a-otros-paises-de-la-region-segun-las-previsiones-del-ice/"
    },

    # GUATEMALA - HONDURAS (Parte del MER)
    # Guatemala es exportador neto, Honduras importador. Estimaciones basadas en MER total ~2700 GWh/año
    (2021, "Guatemala", "Honduras"): {
        "energia": 150,
        "notas": "Estimado MER",
        "fuente": "https://crie.org.gt/mer/"
    },
    (2021, "Honduras", "Guatemala"): {
        "energia": 20,
        "notas": "Estimado MER",
        "fuente": "https://crie.org.gt/mer/"
    },
    (2022, "Guatemala", "Honduras"): {
        "energia": 180,
        "notas": "Estimado MER",
        "fuente": "https://crie.org.gt/mer/"
    },
    (2022, "Honduras", "Guatemala"): {
        "energia": 25,
        "notas": "Estimado MER",
        "fuente": "https://crie.org.gt/mer/"
    },
    (2023, "Guatemala", "Honduras"): {
        "energia": 200,
        "notas": "Estimado MER",
        "fuente": "https://crie.org.gt/mer/"
    },
    (2023, "Honduras", "Guatemala"): {
        "energia": 30,
        "notas": "Estimado MER",
        "fuente": "https://crie.org.gt/mer/"
    },
    (2024, "Guatemala", "Honduras"): {
        "energia": 220,
        "notas": "Estimado MER",
        "fuente": "https://crie.org.gt/mer/"
    },
    (2024, "Honduras", "Guatemala"): {
        "energia": 35,
        "notas": "Estimado MER",
        "fuente": "https://crie.org.gt/mer/"
    },

    # GUATEMALA - MEXICO
    (2022, "Guatemala", "México"): {
        "energia": 1481,
        "notas": "Aproximado",
        "fuente": "https://www.unav.edu/web/global-affairs/los-beneficios-de-la-integracion-electrica-el-caso-de-centroamerica"
    },
    (2022, "México", "Guatemala"): {
        "energia": 100,
        "notas": "Estimado",
        "fuente": "https://www.unav.edu/web/global-affairs/los-beneficios-de-la-integracion-electrica-el-caso-de-centroamerica"
    },

    # GUATEMALA - EL SALVADOR (Parte del MER)
    # El Salvador es importador histórico, pero en 2023-2024 pasó a ser exportador
    (2021, "Guatemala", "El Salvador"): {
        "energia": 300,
        "notas": "Estimado MER",
        "fuente": "https://crie.org.gt/mer/"
    },
    (2021, "El Salvador", "Guatemala"): {
        "energia": 50,
        "notas": "Estimado MER",
        "fuente": "https://crie.org.gt/mer/"
    },
    (2022, "Guatemala", "El Salvador"): {
        "energia": 280,
        "notas": "Estimado MER",
        "fuente": "https://crie.org.gt/mer/"
    },
    (2022, "El Salvador", "Guatemala"): {
        "energia": 80,
        "notas": "Estimado MER",
        "fuente": "https://crie.org.gt/mer/"
    },
    (2023, "Guatemala", "El Salvador"): {
        "energia": 150,
        "notas": "Estimado MER",
        "fuente": "https://crie.org.gt/mer/"
    },
    (2023, "El Salvador", "Guatemala"): {
        "energia": 200,
        "notas": "Estimado MER - El Salvador exportador",
        "fuente": "https://crie.org.gt/mer/"
    },
    (2024, "Guatemala", "El Salvador"): {
        "energia": 120,
        "notas": "Estimado MER",
        "fuente": "https://crie.org.gt/mer/"
    },
    (2024, "El Salvador", "Guatemala"): {
        "energia": 250,
        "notas": "Estimado MER - El Salvador exportador",
        "fuente": "https://crie.org.gt/mer/"
    },

    # HONDURAS - NICARAGUA (Parte del MER)
    # Nicaragua es el mayor importador del MER (~37% de retiros en 2024)
    (2021, "Honduras", "Nicaragua"): {
        "energia": 100,
        "notas": "Estimado MER",
        "fuente": "https://crie.org.gt/mer/"
    },
    (2021, "Nicaragua", "Honduras"): {
        "energia": 30,
        "notas": "Estimado MER",
        "fuente": "https://crie.org.gt/mer/"
    },
    (2022, "Honduras", "Nicaragua"): {
        "energia": 120,
        "notas": "Estimado MER",
        "fuente": "https://crie.org.gt/mer/"
    },
    (2022, "Nicaragua", "Honduras"): {
        "energia": 25,
        "notas": "Estimado MER",
        "fuente": "https://crie.org.gt/mer/"
    },
    (2023, "Honduras", "Nicaragua"): {
        "energia": 150,
        "notas": "Estimado MER",
        "fuente": "https://crie.org.gt/mer/"
    },
    (2023, "Nicaragua", "Honduras"): {
        "energia": 20,
        "notas": "Estimado MER",
        "fuente": "https://crie.org.gt/mer/"
    },
    (2024, "Honduras", "Nicaragua"): {
        "energia": 180,
        "notas": "Estimado MER - Nicaragua mayor importador",
        "fuente": "https://crie.org.gt/mer/"
    },
    (2024, "Nicaragua", "Honduras"): {
        "energia": 15,
        "notas": "Estimado MER",
        "fuente": "https://crie.org.gt/mer/"
    },

    # HONDURAS - EL SALVADOR (Parte del MER)
    (2021, "Honduras", "El Salvador"): {
        "energia": 80,
        "notas": "Estimado MER",
        "fuente": "https://crie.org.gt/mer/"
    },
    (2021, "El Salvador", "Honduras"): {
        "energia": 40,
        "notas": "Estimado MER",
        "fuente": "https://crie.org.gt/mer/"
    },
    (2022, "Honduras", "El Salvador"): {
        "energia": 70,
        "notas": "Estimado MER",
        "fuente": "https://crie.org.gt/mer/"
    },
    (2022, "El Salvador", "Honduras"): {
        "energia": 60,
        "notas": "Estimado MER",
        "fuente": "https://crie.org.gt/mer/"
    },
    (2023, "Honduras", "El Salvador"): {
        "energia": 50,
        "notas": "Estimado MER",
        "fuente": "https://crie.org.gt/mer/"
    },
    (2023, "El Salvador", "Honduras"): {
        "energia": 100,
        "notas": "Estimado MER - El Salvador exportador",
        "fuente": "https://crie.org.gt/mer/"
    },
    (2024, "Honduras", "El Salvador"): {
        "energia": 40,
        "notas": "Estimado MER",
        "fuente": "https://crie.org.gt/mer/"
    },
    (2024, "El Salvador", "Honduras"): {
        "energia": 120,
        "notas": "Estimado MER - El Salvador exportador",
        "fuente": "https://crie.org.gt/mer/"
    },
}
