# Matriz de Balance Energético - Electricidad

## Resumen

Este directorio contiene los datos y scripts para analizar flujos de electricidad entre países de América Latina, incluyendo:
- Datos agregados de OLADE (producción, importación, exportación por país)
- Flujos bilaterales recopilados de fuentes públicas
- Estimaciones bilaterales basadas en datos de OLADE

---

## Estructura de Archivos

```
t1_confection/Matriz Balance energético/
├── OLADE - Matriz de balance energético - Anual.xlsx  ← Archivo fuente OLADE
├── Matriz_ImportExport_PorPais.xlsx                   ← Totales por país (generado)
├── flujos_energia_interconexiones.xlsx                ← Flujos bilaterales recopilados
├── flujos_energia_estimados_olade.xlsx                ← Estimaciones desde OLADE (generado)
│
├── generar_matriz_electricidad.py                     ← Script: extrae datos de OLADE
├── generar_tabla_flujos_energia.py                    ← Script: genera flujos bilaterales
├── datos_flujos_internet.py                           ← Datos de flujos (dependencia)
├── estimar_flujos_desde_olade.py                      ← Script: estima flujos desde OLADE
│
└── README_PROCESO.md                                  ← Este archivo
```

---

## Archivos Excel

### 1. OLADE - Matriz de balance energético - Anual.xlsx
**Tipo:** Archivo fuente (entrada)

Archivo original de OLADE con 37 hojas (una por país/año).
- **Años:** 2021, 2023
- **Países:** 19 países de América Latina
- **Datos:** Producción, importación, exportación de electricidad (GWh)

### 2. Matriz_ImportExport_PorPais.xlsx
**Tipo:** Generado por `generar_matriz_electricidad.py`

Totales agregados por país extraídos de OLADE.

| Columna | Descripción |
|---------|-------------|
| País | Nombre del país |
| Año | 2021 o 2023 |
| Producción_Electricidad_GWh | Generación local |
| Importación_Electricidad_GWh | Total importado |
| Exportación_Electricidad_GWh | Total exportado |
| Balance_Neto_GWh | Exportación - Importación |

**Hojas:**
- `Matriz_Completa`: Datos por país y año (37 filas)
- `Resumen_Por_País`: Totales agregados (19 filas)

### 3. flujos_energia_interconexiones.xlsx
**Tipo:** Generado por `generar_tabla_flujos_energia.py`

Flujos bilaterales recopilados de fuentes públicas (reportes de operadores, noticias, etc.).

| Columna | Descripción |
|---------|-------------|
| Año | 2021-2024 |
| País Salida | País exportador |
| País Entrada | País importador |
| Energía (GWh) | Valor del flujo |
| Notas | Contexto del dato |
| Fuente | URL o referencia |

**Interconexiones incluidas:** 20 pares de países con líneas de transmisión.

### 4. flujos_energia_estimados_olade.xlsx
**Tipo:** Generado por `estimar_flujos_desde_olade.py`

Estimaciones de flujos bilaterales que cuadran exactamente con los totales de OLADE.

| Columna | Descripción |
|---------|-------------|
| Año | 2021-2024 |
| País Salida | País exportador |
| País Entrada | País importador |
| Energía (GWh) | Valor original bilateral |
| Energía_Export (GWh) | Estimación basada en exportaciones OLADE |
| Energía_Import (GWh) | Estimación basada en importaciones OLADE |
| Notas | Método de estimación |
| Fuente | OLADE |

**Metodología:**
- `Energía_Export`: Distribuye la exportación OLADE del país de salida entre sus vecinos según proporciones de `flujos_energia_interconexiones.xlsx`
- `Energía_Import`: Distribuye la importación OLADE del país de entrada entre sus vecinos según proporciones

**Verificación:**
- Suma de `Energía_Export` por país de salida = Exportación OLADE (exacto)
- Suma de `Energía_Import` por país de entrada = Importación OLADE (exacto)

---

## Scripts Python

### generar_matriz_electricidad.py

Extrae datos de electricidad del archivo OLADE.

```bash
python generar_matriz_electricidad.py
```

**Entrada:** `OLADE - Matriz de balance energético - Anual.xlsx`
**Salida:** `Matriz_ImportExport_PorPais.xlsx`

### generar_tabla_flujos_energia.py

Genera la tabla de flujos bilaterales con datos recopilados.

```bash
python generar_tabla_flujos_energia.py
```

**Dependencia:** `datos_flujos_internet.py`
**Salida:** `flujos_energia_interconexiones.xlsx`

### estimar_flujos_desde_olade.py

Genera estimaciones de flujos bilaterales basadas en OLADE.

```bash
python estimar_flujos_desde_olade.py
```

**Entrada:**
- `flujos_energia_interconexiones.xlsx` (para proporciones)
- `Matriz_ImportExport_PorPais.xlsx` (totales OLADE)

**Salida:** `flujos_energia_estimados_olade.xlsx`

---

## Interconexiones Eléctricas

Las 20 interconexiones consideradas:

| Región | Interconexión |
|--------|---------------|
| Cono Sur | Argentina-Bolivia, Argentina-Brasil, Argentina-Chile, Argentina-Paraguay, Argentina-Uruguay |
| Cono Sur | Bolivia-Chile, Bolivia-Perú |
| Cono Sur | Brasil-Paraguay, Brasil-Uruguay |
| Andina | Chile-Perú, Colombia-Ecuador, Ecuador-Perú |
| Andina | Colombia-Panamá |
| Centroamérica (SIEPAC) | Costa Rica-Nicaragua, Costa Rica-Panamá |
| Centroamérica (SIEPAC) | Guatemala-Honduras, Guatemala-México, Guatemala-El Salvador |
| Centroamérica (SIEPAC) | Honduras-Nicaragua, Honduras-El Salvador |

---

## Flujo de Trabajo

```
┌─────────────────────────────────────────┐
│ OLADE - Matriz de balance energético    │
│ (Archivo fuente)                        │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│ generar_matriz_electricidad.py          │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│ Matriz_ImportExport_PorPais.xlsx        │
│ (Totales por país)                      │
└────────────────┬────────────────────────┘
                 │
                 ├──────────────────────────────────────┐
                 │                                      │
                 ▼                                      ▼
┌─────────────────────────────────────────┐  ┌─────────────────────────────────────────┐
│ flujos_energia_interconexiones.xlsx     │  │ estimar_flujos_desde_olade.py           │
│ (Datos bilaterales recopilados)         │  │                                         │
└────────────────┬────────────────────────┘  └────────────────┬────────────────────────┘
                 │                                            │
                 └──────────────┬─────────────────────────────┘
                                │
                                ▼
                 ┌─────────────────────────────────────────┐
                 │ flujos_energia_estimados_olade.xlsx     │
                 │ (Estimaciones que cuadran con OLADE)   │
                 └─────────────────────────────────────────┘
```

---

## Notas Importantes

### Diferencia entre datos bilaterales y OLADE

Los totales de OLADE pueden diferir de la suma de flujos bilaterales porque:
1. OLADE incluye intercambio con países fuera de la región (ej: México-USA)
2. Diferencias metodológicas entre fuentes
3. Pérdidas en transmisión (2-5%)

### Dos columnas de estimación

El archivo `flujos_energia_estimados_olade.xlsx` tiene dos estimaciones:
- **Energía_Export**: Útil cuando se quiere que las exportaciones cuadren con OLADE
- **Energía_Import**: Útil cuando se quiere que las importaciones cuadren con OLADE

Ambas no pueden coincidir simultáneamente si los totales de OLADE no son iguales.

### Años disponibles

| Archivo | Años |
|---------|------|
| OLADE | 2021, 2023 |
| Flujos bilaterales | 2021, 2022, 2023, 2024 |
| Estimaciones | 2021, 2023 (de OLADE), 2022, 2024 (originales) |

---

## Requisitos

```bash
pip install pandas openpyxl
```

---

## Referencias

- **OLADE:** https://www.olade.org/
- **CIER:** https://www.cier.org/
- **SIEPAC (Centroamérica):** https://www.enteoperador.org/
- **Itaipú Binacional:** https://www.itaipu.gov.br/
- **Yacyretá:** https://www.eby.gov.py/
- **Salto Grande:** https://www.saltogrande.org/

---

**Última actualización:** 2025-02-06
