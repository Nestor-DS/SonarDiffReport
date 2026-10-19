# SonarDiffReport

Genera un documento Word (.docx) con una tabla comparativa **Antes / Después** de los
issues de SonarQube (SonarLint en Eclipse o SonarQube Web) entre dos ramas de Git,
usando capturas de pantalla **semi-automáticas** de una región fija que tú seleccionas.

El usuario abre cada archivo manualmente en Eclipse/Sonar (no se automatiza la
navegación del UI); la app muestra el nombre del siguiente archivo y espera a la
hotkey global **F9** para capturar la región definida. Todo lo demás (diff Git,
checkout de ramas, guardado de capturas, Word, restauración de la rama original)
está automatizado.

## Requisitos

- Python 3.11+
- Git instalado y accesible desde el PATH
- Windows, Linux o macOS (probado principalmente en Windows)

## Instalación

```bash
git clone <repo-url>
cd SonarDiffReport

python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
```

## Uso

```bash
python main.py
```

### Flujo de usuario

1. **Selecciona el repositorio** Git con "Examinar…".
2. Pulsa **"Listar ramas locales"** (o **"Listar local + remoto"** para incluir
   `origin/…`) y elige la **rama base (Antes)** y la **rama a comparar
   (Después)**. También puedes escribir los nombres a mano o usar
   **"Buscar…"** junto a cada campo:
   - Diálogo con filtro por texto sobre ramas locales y remotas.
   - **"Buscar en remoto…"** consulta `git ls-remote` e incluye ramas del
     remoto que aún no hayas traído (marcadas como *sin fetch*); al ejecutar
     la comparación se hace un fetch puntual solo de esa rama.
3. Define la **región de captura** con "Seleccionar región (Antes)…":
   se abre un overlay a pantalla completa; **arrastra el rectángulo** sobre el
   panel de issues de SonarLint/SonarQube y suelta. `ESC` cancela.
   - Por defecto la misma región se usa para Antes y Después (checkbox).
   - Si lo desmarcas, se te pedirá una segunda región al terminar la fase Antes.
4. Elige la ruta del **documento Word de salida**.
5. Pulsa **"Generar comparación"** y confirma los checkouts de rama:
   - La app cambia a la rama base. Para cada archivo **modificado o eliminado**
     aparece su nombre en la barra de progreso: ábrelo en Eclipse/Sonar,
     deja visible el panel de issues y pulsa **F9**.
   - La app cambia a la rama a comparar. Repite el proceso para cada archivo
     **modificado o nuevo** (F9).
   - Al terminar se genera el .docx y **se restaura la rama en la que estabas**.
6. Archivos **nuevos** solo aparecen en la columna Después; **eliminados**, solo
   en Antes (marcados en la tabla).

Puedes pulsar **Cancelar** en cualquier momento: se aborta el flujo y se restaura
la rama original.

### Ejemplo

```
main vs ndsp, 3 archivos cambiados:
  M src/Foo.java
  M src/Bar.java
  A src/Nuevo.java

Fase ANTES  (main):    capturas de Foo.java, Bar.java      → F9 en cada uno
Fase DESPUÉS (ndsp):   capturas de Foo.java, Bar.java, Nuevo.java → F9 en cada uno
Salida: comparacion_main_vs_ndsp.docx
```

## Tests

Sin dependencias externas, desde la raíz:

```bash
python tests/test_file_change.py
```

## Configuración persistente

La última selección (repositorio, ramas, ruta de salida, regiones) se guarda en:

```
~/.sonar_compare/config.json
```

Se recarga automáticamente al arrancar.

## Logs

Los logs rotatorios quedan en `~/.sonar_compare/sonar_compare.log`.

## Notas (Windows)

- **Escalado de pantalla**: el proceso se marca como DPI-aware para que la región
  seleccionada en el overlay coincida píxel a píxel con la captura. No ejecutes
  la app con privilegios elevados si Eclipse/Sonar no los tiene (la hotkey global
  F9 debe llegar a la app).
- **Multi-monitor**: el overlay cubre todo el escritorio virtual; puedes arrastrar
  la región en cualquier monitor.

## Arquitectura

```
sonar_compare/
├── main.py                      # Entry point (DPI awareness, logging, Tk)
├── gui/
│   ├── main_window.py           # Ventana principal + adaptador al flujo
│   ├── branch_search_dialog.py  # Búsqueda de ramas con filtro + ls-remote
│   ├── region_selector.py       # Overlay para seleccionar la región (drag)
│   └── bridge.py                # Puente seguro worker-thread → hilo de Tk
├── core/
│   ├── git_service.py           # diff, ramas, checkout (subprocess, sin deps)
│   ├── screenshot_service.py    # mss + hotkey F9 (pynput)
│   ├── comparison_service.py    # Orquestador del flujo Antes/Después
│   ├── word_service.py          # Generación del .docx (python-docx)
│   └── errors.py                # Jerarquía de excepciones de dominio
├── models/
│   ├── file_change.py           # FileChange + ChangeStatus
│   ├── comparison.py            # ComparisonEntry (fila de la tabla)
│   └── screen_region.py         # ScreenRegion (coords. absolutas)
├── config/
│   └── settings.py              # AppSettings + load/save JSON atómico
└── utils/
    └── logger.py                # Logging a consola + fichero rotatorio
```

Decisiones principales:

- **subprocess en vez de GitPython**: una dependencia menos, compatible con
  PyInstaller y con mensajes de error de Git tal cual.
- **Hilo de trabajo + `UiBridge`**: la GUI nunca se congela; los diálogos y el
  selector de región se ejecutan en el hilo de Tk vía cola + `root.after`.
- **Servicios con Protocolo de UI** (`WorkflowUi`): el orquestador no conoce
  Tkinter, lo que permite testear el flujo con un stub de UI.
- **Temp dir por ejecución**: las capturas se limpian automáticamente tras
  generar el Word.

## Notas sobre ramas remotas

- Se pueden usar ramas remotas directamente: `origin/main`, un nombre corto
  existente solo en remoto (Git crea la rama de tracking) o una rama aún no
  traída (se hará `git fetch` puntual de esa rama antes de empezar).
- Si eliges una ref con prefijo (`origin/x`) y ya existe una rama local `x`,
  el checkout se hace en *detached HEAD* sobre el estado exacto de
  `origin/x` (lo que suele interesarte para el "Antes").
- El botón **"Buscar en remoto…"** usa el remote por defecto (`origin` si
  existe); puede tardar unos segundos si el remoto está lejos.

## Limitaciones conocidas

- Un solo repositorio y una región por ejecución (por diseño, simplicidad).

## Futuro (posibles extensiones)

- Exportación a PDF, métricas numéricas de issues, multi-proyecto,
  hotkey configurable, captura automática por OCR.

## Empaquetado con PyInstaller

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name SonarDiffReport main.py
```

`main.py` ya llama a `multiprocessing.freeze_support()` y no usa rutas relativas
al CWD, por lo que funciona sin cambios con PyInstaller.
