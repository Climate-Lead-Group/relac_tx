# RELAC TX - Energy System Optimization Model

Sistema de modelado de optimización energética basado en OSeMOSYS para América Latina y el Caribe.

## Descripción

Este proyecto implementa un pipeline automatizado para la ejecución de modelos de optimización energética utilizando OSeMOSYS. El sistema soporta múltiples solvers (GLPK, CBC, CPLEX, Gurobi) y está diseñado para garantizar reproducibilidad completa de los resultados.

## Características Principales

- **Pipeline Automatizado**: Gestión completa del flujo de trabajo con DVC
- **Múltiples Solvers**: Soporte para GLPK, CBC, CPLEX y Gurobi
- **Reproducibilidad Garantizada**: Seeds configurables para resultados determinísticos
- **Medición de Rendimiento**: Timer integrado para monitorear tiempos de ejecución
- **Gestión Automática de Entorno**: Creación y actualización automática del entorno Conda

## Requisitos del Sistema

- Windows 10 o superior
- Git para Windows
- Miniconda o Anaconda
- Al menos un solver: GLPK, CBC, CPLEX o Gurobi

## Inicio Rápido

```bash
# Clonar el repositorio
git clone https://github.com/clg-admin/relac_tx.git
cd relac_tx

# Ejecutar el modelo (desde Anaconda Prompt)
python run.py
```

El script `run.py` gestiona automáticamente:
- Creación del entorno Conda
- Instalación de dependencias
- Ejecución del pipeline completo
- Generación de archivos de salida

## Documentación

Para instrucciones detalladas de instalación y configuración, consulta la guía completa:
- **Guía de Instalación y Ejecución**: `RELAC_TX_Guia_instalacion_ejecucion.md`

## Estructura de Archivos de Salida

Los resultados se generan en `t1_confection/` con los siguientes archivos:
- `RELAC_TX_Inputs.csv` / `RELAC_TX_Inputs_YYYY-MM-DD.csv`
- `RELAC_TX_Outputs.csv` / `RELAC_TX_Outputs_YYYY-MM-DD.csv`
- `RELAC_TX_Combined_Inputs_Outputs.csv` / `RELAC_TX_Combined_Inputs_Outputs_YYYY-MM-DD.csv`

Los archivos con fecha mantienen un histórico completo de ejecuciones.

## Configuración

El archivo principal de configuración es `t1_confection/MOMF_T1_AB.yaml`, donde puedes ajustar:
- Solver a utilizar (`solver: 'cplex'`)
- Número de threads para solvers comerciales
- Seeds para reproducibilidad
- Anualización de capital (`annualize_capital`)

## Editor de Tecnologías Secundarias

El proyecto incluye un sistema para facilitar la edición de tecnologías secundarias (Secondary Techs) en los archivos de parametrización, con soporte para integración automática de datos OLADE.

### Uso del Editor

1. **Generar plantilla de edición**:
   ```bash
   python t1_confection/D1_generate_editor_template.py
   ```
   Esto crea el archivo `Secondary_Techs_Editor.xlsx` con dos hojas:
   - **Instructions**: Para edición manual con listas desplegables
   - **OLADE_Config**: Configuración de integración automática con datos OLADE

2. **Edición Manual** (Hoja "Instructions"):
   - Seleccionar: Escenario (BAU, NDC, NDC+ELC, NDC_NoRPO, o ALL)
   - Seleccionar: País, Tecnología (Tech.Name) y Parámetro
   - Ingresar los valores para los años deseados (2021-2050)
   - La columna "Tech" se completa automáticamente con VLOOKUP

3. **Integración OLADE** (Hoja "OLADE_Config"):

   Permite poblar automáticamente el parámetro `ResidualCapacity` para tecnologías PWR usando datos de capacidad instalada de OLADE.

   | Parámetro | Descripción |
   |-----------|-------------|
   | `ResidualCapacitiesFromOLADE` | YES/NO - Habilitar integración OLADE |
   | `CapacityFactorGrowth (%)` | Tasa de crecimiento anual (ej: 5.0) |
   | `GrowthType` | Compound (exponencial) o Simple (lineal) |
   | `PetroleumSplitMode` | OIL_only o Split_PET_OIL |

   **PetroleumSplitMode**:
   - `OIL_only`: Asigna toda la capacidad de petróleo a OIL (Fuel oil)
   - `Split_PET_OIL`: Divide entre PET (Diésel) y OIL (Fuel oil) usando proporciones del archivo `Shares.xlsx`

4. **Aplicar cambios**:
   ```bash
   python t1_confection/D2_update_secondary_techs.py
   ```

### Características del Sistema

- **Listas desplegables**: Facilitan la selección de escenarios, países, tecnologías y parámetros
- **Mapeo Tech.Name → Tech**: Conversión automática de nombres descriptivos a códigos técnicos
- **Integración OLADE**: Población automática de ResidualCapacity desde datos de capacidad instalada
- **Conversión MW → GW**: Los datos OLADE (en MW) se convierten automáticamente a GW
- **Proyección temporal**: Aplica tasas de crecimiento para años antes y después del año base OLADE (2023)
- **Respaldos automáticos**: Un backup por escenario antes de aplicar cambios
- **Projection.Mode**: Se actualiza automáticamente a "User defined" al modificar valores
- **Logs detallados**: Registro completo con identificación de país en cada operación

### Archivos Relacionados

| Archivo | Descripción |
|---------|-------------|
| `D1_generate_editor_template.py` | Genera la plantilla Excel |
| `D2_update_secondary_techs.py` | Aplica los cambios a los escenarios |
| `Secondary_Techs_Editor.xlsx` | Plantilla de edición (generada) |
| `Capacidad instalada por fuente - Anual - OLADE.xlsx` | Datos fuente OLADE |
| `Shares.xlsx` | Proporciones para split de petróleo por escenario |

### Mapeo de Países OLADE → Modelo

Algunos códigos de país difieren entre OLADE y el modelo:

| País | OLADE | Modelo |
|------|-------|--------|
| Barbados | BAR | JAM |
| Chile | CHI | CHL |
| Costa Rica | CRC | CRI |

## Licencia

Este proyecto está licenciado bajo la Licencia MIT - consulta el archivo [LICENSE](LICENSE) para más detalles.

Copyright (c) 2025 Climate Lead Group

Este proyecto está desarrollado por Climate Lead Group para análisis de sistemas energéticos en América Latina y el Caribe.
