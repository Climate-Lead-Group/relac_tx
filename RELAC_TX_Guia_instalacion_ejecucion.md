# OG-MOMF — Guía de Instalación y Ejecución

## Metadatos
- **Público objetivo:** quien lo requiera
- **Sistema operativo:** Windows
- **Repositorio:** público (`main`)
- **Formato:** Quick Start
- **Solvers disponibles:** GLPK, CBC, CPLEX, Gurobi
- **Nota CPLEX:** requiere licencia y también **Microsoft Visual Studio** (no VS Code)
- **Nota Gurobi:** requiere licencia académica o comercial

## 1. Requisitos del Sistema

### Software Necesario
- Windows 10 o superior
- Git para Windows
- Miniconda o Anaconda
- Al menos un solver: GLPK, CBC, CPLEX o Gurobi

### Recomendaciones de Rutas
- Usar rutas cortas como `C:\dev\relac_tx\` o `D:\dev\relac_tx\`
- **Evitar:**
  - Rutas con espacios o caracteres especiales (tildes, ñ, etc.)
  - Rutas demasiado largas
  - Carpetas sincronizadas con la nube (OneDrive, Dropbox, Google Drive)

## 2. Instalación de Prerequisitos

### 2.1 Solvers

#### GLPK y CBC (incluidos en el entorno)
- **No requieren instalación manual:** ambos están declarados en `environment.yaml` (`glpk` y `coincbc`) y se instalan junto con el entorno Conda al ejecutar `run.py`.
- Si tu entorno `OG-MOMF-env` es anterior a esta inclusión, `run.py` detecta que faltan los binarios `glpsol`/`cbc` y los instala en su siguiente ejecución. Instalación manual equivalente (en **Anaconda Prompt**):
  ```bash
  conda install -n OG-MOMF-env -c conda-forge glpk coincbc
  ```
- **Verificación** (en **Anaconda Prompt**, con el entorno activo):
  ```bash
  conda activate OG-MOMF-env
  glpsol --version
  cbc -v
  CTRL+Z
  ```
  `glpsol` debe mostrar "GLPK LP/MIP Solver, v5.0" (o superior); `cbc` debe indicar la versión (2.10.x) y fecha de compilación.
- **Nota:** los binarios viven dentro del entorno (`...\envs\OG-MOMF-env\Library\bin`), por lo que solo están en el `PATH` con el entorno activo o vía `conda run` (como hace `run.py`). Si prefieres una instalación global fuera de Conda, sigue las *Guías CLG – GLPK / CBC*.

#### CPLEX
- **Versión recomendada:** 22.1.1.0
- **Requisitos adicionales:**
  - Licencia académica o comercial
  - Microsoft Visual Studio (no VS Code)
- **Verificación** (en **Anaconda Prompt**):
  ```bash
  cplex
  CTRL+Z
  ```
- **Nota:** Si el comando no responde, agrega CPLEX al `PATH` o usa la ruta completa al ejecutable

#### Gurobi
- **Versión recomendada:** 11.0 o superior
- **Requisitos adicionales:**
  - Licencia académica o comercial
- Instálalo siguiendo la documentación oficial de Gurobi
- **Verificación** (en **Anaconda Prompt**):
  ```bash
  gurobi_cl --version
  ```
- **Nota:** Si el comando no responde, agrega Gurobi al `PATH` o usa la ruta completa al ejecutable

#### Recomendación de uso de solvers
- **GLPK:** Ideal para modelos pequeños (ejecución rápida en problemas simples)
- **CBC:** Recomendado para modelos medianos
- **CPLEX:** Excelente rendimiento en modelos grandes y complejos
- **Gurobi:** Mejor rendimiento en modelos grandes y complejos, especialmente en problemas MIP

### 2.2 Git

1. Descargar [Git para Windows](https://git-scm.com/downloads/win)
2. Instalar Git con las opciones por defecto
3. Abrir **Git Bash**
4. Configurar tu identidad (en **Git Bash**):
   ```bash
   git config --global user.name "tu_nombre"
   git config --global user.email "tu_email@ejemplo.com"
   ```

### 2.3 Miniconda

1. Descargar [Miniconda](https://www.anaconda.com/download/success) para Windows
2. Instalar Miniconda para tu usuario
3. Abrir **Anaconda Prompt**
4. Aceptar los Términos de Servicio requeridos (en **Anaconda Prompt**):
   ```bash
   conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main
   conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r
   conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/msys2
   ```

**Nota importante:** No es necesario crear manualmente el entorno virtual ni instalar dependencias. El script `run.py` gestiona automáticamente la creación y actualización del entorno según `environment.yaml`.

## 3. Configuración Inicial

### 3.1 Clonar el Repositorio

1. Crear la carpeta de trabajo (en **Git Bash**):
   ```bash
   mkdir -p /c/dev
   cd /c/dev
   ```

2. Clonar el repositorio (en **Git Bash**):
   ```bash
   git clone https://github.com/clg-admin/relac_tx.git
   ```

### 3.2 Configuración del Solver (opcional)

Si deseas cambiar el solver por defecto:

1. Editar el archivo: `relac_tx\inputs\config\Config_MOMF_T1_AB.yaml`
2. Buscar la clave `solver` y cambiarla a uno de estos valores:
   - `glpk`
   - `cbc`
   - `cplex` (por defecto)
   - `gurobi`
3. Guardar el archivo

#### Configuración adicional para CPLEX

Si usas CPLEX, es importante configurar el número de threads:

1. En el mismo archivo `Config_MOMF_T1_AB.yaml`, buscar la variable `cplex_threads`
2. Ajustar el valor según tu máquina:
   - **Si solo ejecutas el modelo:** Dejar al menos 2 threads libres
   - **Si realizas otras tareas simultáneamente:** Dejar más threads libres

**Ejemplo:** Si tu máquina tiene 8 cores:
- Para uso exclusivo del modelo: configurar `cplex_threads: 6`
- Para uso compartido: configurar `cplex_threads: 4` o menos

**Nota:** Una configuración incorrecta de threads puede causar que el sistema se vuelva lento o no responda durante la ejecución.

#### Configuración adicional para Gurobi

Si usas Gurobi, es importante configurar el número de threads:

1. En el mismo archivo `Config_MOMF_T1_AB.yaml`, buscar la variable `gurobi_threads`
2. Ajustar el valor según tu máquina siguiendo las mismas recomendaciones que para CPLEX

### 3.3 Configuración Avanzada (opcional)

El archivo `Config_MOMF_T1_AB.yaml` contiene parámetros adicionales que puedes ajustar:

#### Seeds para Reproducibilidad
Para garantizar resultados determinísticos y reproducibles:
- `cbc_random_seed`: Semilla para CBC (por defecto: 12345)
- `cplex_random_seed`: Semilla para CPLEX (por defecto: 12345)
- `gurobi_seed`: Semilla para Gurobi (por defecto: 12345)

**Nota:** Estos parámetros aseguran que ejecutar el modelo múltiples veces con los mismos datos de entrada produzca resultados idénticos.

#### Anualización de Capital
- `annualize_capital`: Activa/desactiva la anualización de inversiones de capital (por defecto: True)

Cuando está activado (`True`), el modelo calcula los costos anualizados de las inversiones de capital usando el método del Factor de Recuperación de Capital (CRF).

## 4. Ejecución del Modelo

### 4.1 Comando de Ejecución

1. Navegar a la carpeta del proyecto (en **Anaconda Prompt**):
   ```bash
   cd C:\dev\relac_tx
   ```

2. Ejecutar el modelo (en **Anaconda Prompt**):
   ```bash
   python run.py
   ```

### 4.2 ¿Qué hace run.py?

El script `run.py` se encarga automáticamente de:
- Detectar si existe el entorno Conda y crearlo si es necesario
- Verificar e instalar las dependencias faltantes
- Inicializar el repositorio DVC si no existe
- Ejecutar el pipeline completo del modelo
- Generar los archivos de salida con la fecha actual
- Mostrar el tiempo total de ejecución al finalizar

### 4.3 Tiempo de Ejecución

Al finalizar la ejecución, `run.py` mostrará el tiempo total que tomó el pipeline, por ejemplo:
```
✅ ¡Pipeline completado en 1h 23m 45s!
```

Esto te ayuda a:
- Monitorear el rendimiento del modelo
- Comparar tiempos entre diferentes solvers
- Identificar oportunidades de optimización

## 5. Archivos de Salida

### 5.1 Ubicación
Todos los archivos de salida se generan en: `relac_tx/outputs/`

### 5.2 Archivos Generados

El modelo genera 6 archivos CSV:
- `RELAC_TX_Inputs.csv` - Inputs de la última ejecución
- `RELAC_TX_Inputs_YYYY-MM-DD.csv` - Histórico de inputs con fecha
- `RELAC_TX_Outputs.csv` - Outputs de la última ejecución
- `RELAC_TX_Outputs_YYYY-MM-DD.csv` - Histórico de outputs con fecha
- `RELAC_TX_Combined_Inputs_Outputs.csv` - Combinación de la última ejecución
- `RELAC_TX_Combined_Inputs_Outputs_YYYY-MM-DD.csv` - Histórico combinado con fecha

**Nota:** Los archivos con fecha (YYYY-MM-DD) mantienen un registro histórico de cada ejecución.

### 5.3 Verificación

Después de la ejecución, confirma:
- La presencia de los 6 archivos
- La fecha y hora de modificación corresponde a la ejecución reciente

## 6. Solución de Problemas Frecuentes

### Problema: "Conda ToS no aceptados"
**Solución:** Ejecutar nuevamente los tres comandos del paso 2.3 (en **Anaconda Prompt**)

### Problema: "Solver no encontrado"
**Solución:** 
- Verificar que el solver está instalado correctamente
- Agregar el solver al `PATH` del sistema
- Reinstalar siguiendo las *Guías CLG* correspondientes

### Problema: "Error en rutas"
**Solución:** Verificar que:
- No hay espacios en la ruta
- No hay caracteres especiales (tildes, ñ)
- La ruta no es demasiado larga
- No está en una carpeta sincronizada con la nube

### Problema: "Cambiar solver no surte efecto"
**Solución:**
1. Confirmar que editaste y guardaste `Config_MOMF_T1_AB.yaml`
2. Verificar que el solver alternativo está instalado
3. Volver a ejecutar `python run.py`

### Problema: "Permisos denegados"
**Solución:** Algunas operaciones pueden requerir permisos de administrador:
- Ejecutar Anaconda Prompt como Administrador
- Verificar permisos de escritura en la carpeta del proyecto

## 7. Notas Importantes

- **Siempre usar `run.py`:** Este script gestiona todo el proceso automáticamente
- **Terminal correcta:** 
  - Usar **Git Bash** para operaciones de Git
  - Usar **Anaconda Prompt** para ejecutar el modelo
- **Entorno automático:** No crear manualmente entornos Conda, `run.py` lo gestiona
- **Archivos históricos:** Los archivos con fecha permiten mantener un registro de todas las ejecuciones