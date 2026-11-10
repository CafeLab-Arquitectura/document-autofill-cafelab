# Fase 0: Google Cloud y Document AI

Guía manual para preparar el procesador **Custom Extractor** que usará `document-autofill-cafelab`.
Todos los pasos se hacen en la consola de Google Cloud (https://console.cloud.google.com) con una cuenta que tenga permisos de propietario o editor en el proyecto.

> Los nombres de botones y menús de la consola pueden cambiar un poco con el tiempo. Si algo no coincide, busca la opción equivalente en la misma pantalla.

Al final tendrás estos cuatro datos para el `.env` (paso 7):

| Variable | Ejemplo de formato (no son valores reales) |
|---|---|
| `GCP_PROJECT_ID` | `mi-proyecto-123456` |
| `DOCAI_LOCATION` | `us` o `eu` |
| `DOCAI_PROCESSOR_ID` | `a1b2c3d4e5f6a7b8` |
| `DOCAI_PROCESSOR_VERSION` | `a1b2c3d4e5f6a7b8` (opcional) |

---

## 1. Crear o elegir el proyecto y vincular la facturación

1. En la barra superior de la consola, abre el selector de proyectos.
2. Elige un proyecto existente del equipo o haz clic en **Proyecto nuevo**:
   - Nombre: por ejemplo `cafelab-document-autofill`.
   - Anota el **ID del proyecto** que muestra la consola (no es igual al nombre). Ese es `GCP_PROJECT_ID`.
3. Ve a **Facturación** (menú ☰ → Facturación).
4. Si el proyecto no tiene cuenta de facturación, haz clic en **Vincular una cuenta de facturación** y elige la cuenta (por ejemplo, la de créditos educativos o de prueba gratuita).
5. Recomendado: en **Facturación → Presupuestos y alertas**, crea un presupuesto pequeño con alerta por correo para evitar sorpresas. Document AI cobra por página procesada.

## 2. Habilitar la API de Document AI

1. Menú ☰ → **APIs y servicios → Biblioteca**.
2. Busca **Cloud Document AI API**.
3. Haz clic en **Habilitar** y espera a que termine.

## 3. Crear el procesador Custom Extractor

1. Menú ☰ → **Document AI** (o busca "Document AI" en la barra de búsqueda).
2. Abre **Document AI Workbench** y, dentro, **Custom Extractor** → **Crear procesador**.
3. Completa:
   - **Nombre del procesador**: `cafelab-guia-remision`.
   - **Región**: `US` o `EU`. Esta elección es definitiva para el procesador y debe coincidir con `DOCAI_LOCATION` (`us` o `eu`).
4. Haz clic en **Crear**.
5. En la página del procesador, en **Información del procesador**, copia el **ID** (una cadena hexadecimal). Ese es `DOCAI_PROCESSOR_ID`.
   - La consola también muestra el **Endpoint de predicción**, con forma `https://us-documentai.googleapis.com/v1/projects/<número>/locations/us/processors/<id>:process`. Sirve para confirmar región e ID.

> Si el asistente pide un **bucket de Cloud Storage** para el conjunto de datos, elige la opción de almacenamiento administrado por Google (si está disponible) o crea un bucket nuevo en la misma región. Ahí solo se guardan los documentos de ejemplo que subas en el paso 5, no los que procese el servicio.

## 4. Definir el esquema (8 campos)

1. En el procesador, abre la pestaña **Compilación (Build)** y luego **Editar esquema** (o **Comenzar → Definir campos**).
2. Crea los campos con **Agregar campo nuevo**, uno por fila de esta tabla:

| Nombre del campo | Tipo de datos | Ocurrencia | Descripción sugerida (ayuda al modelo zero-shot) |
|---|---|---|---|
| `lot_name` | Texto sin formato (Plain text) | Opcional, una vez | Valor de la fila "Nombre del lote" en la sección "4. DATOS DEL LOTE DE CAFÉ". |
| `supplier_name` | Texto sin formato | Opcional, una vez | Nombre del proveedor en la sección 2 de la guía de remisión. |
| `coffee_type` | Texto sin formato | Opcional, una vez | Valor de la fila "Tipo de café" (por ejemplo Arábica, Robusta o Mezcla). |
| `origin` | Texto sin formato | Opcional, una vez | Valor de la fila "Origen" (lugar de procedencia del café). |
| `processing_method` | Texto sin formato | Opcional, una vez | Valor de la fila "Proceso poscosecha" (por ejemplo Lavado, Natural, Honey). |
| `altitude_meters` | Texto sin formato | Opcional, una vez | Valor de la fila "Altitud (msnm)", tal como aparece escrito. |
| `initial_weight_kg` | Texto sin formato | Opcional, una vez | Valor de la fila "Peso neto (kg)", tal como aparece escrito. |
| `certifications` | Texto sin formato | **Opcional, varias veces** | Cada certificación de la fila "Certificaciones", una por valor. |

Notas sobre el esquema:

- Los nombres deben quedar **exactamente** así (minúsculas y guion bajo). El servicio busca las entidades por esos nombres.
- Todos los campos van como **Texto sin formato**, incluidos altitud y peso. El servicio se encarga de convertir "1,650 msnm" en `1650` y "69,5" en `69.5`, y de normalizar los valores de las listas. Así la regla vive en un solo lugar y es testeable.
- Todos son **opcionales**: si el modelo no encuentra un campo, el servicio responde `null` con la advertencia `NOT_FOUND` en lugar de fallar.
- `certifications` es el único campo **repetido** ("varias veces"), porque una guía puede tener más de una certificación.
3. Guarda el esquema.

## 5. Subir el PDF de ejemplo, etiquetar y desplegar la versión zero-shot

### 5.1 Subir el documento de ejemplo

1. En la pestaña **Compilación**, haz clic en **Importar documentos**.
2. Sube el PDF de ejemplo del **Formato X** (una página).
   - Usa un ejemplo con datos ficticios. No subas guías con datos reales de proveedores.
3. Asígnalo al conjunto **Prueba (Test)** si la consola lo pregunta. En modo zero-shot no se entrena, así que este documento solo sirve para revisar y evaluar.

### 5.2 Etiquetar los campos

1. Abre el documento importado. Si la consola ofrece **Etiquetado automático (Auto-label)** con el modelo base, úsalo como punto de partida.
2. Revisa cada uno de los 8 campos: marca en el documento el texto correcto o corrige lo que el modelo propuso.
3. Para `certifications`, marca **cada** certificación como una instancia separada.
4. Marca el documento como **Etiquetado** y guarda.

> El etiquetado aquí no entrena al modelo. Sirve para que la evaluación de la versión compare lo que extrae el modelo con lo correcto.

### 5.3 Crear la versión con el modelo base (zero-shot)

1. Ve a la pestaña **Compilación** o **Administrar versiones**.
2. Elige **Crear versión nueva** y selecciona la opción **basada en el modelo base / modelo fundacional (generativo), sin entrenamiento**. No elijas "entrenar modelo personalizado".
   - En algunas consolas ya aparece una versión **preentrenada** del modelo fundacional (por ejemplo, con nombre `pretrained-foundation-model-...`). Si existe, puedes usarla directamente.
3. Ponle un nombre, por ejemplo `zero-shot-v1`, y crea la versión.
4. Opcional: en **Evaluar y probar**, ejecuta la evaluación contra el documento etiquetado para ver qué campos acierta.

### 5.4 Desplegar y marcar como predeterminada

1. En **Administrar versiones**, en la fila de la versión, abre el menú ⋮ → **Desplegar versión**. Espera a que el estado sea **Desplegada** (puede tardar varios minutos).
2. En el mismo menú, elige **Establecer como predeterminada**.
3. Copia el **ID de la versión** (aparece en la lista de versiones o en sus detalles). Ese es `DOCAI_PROCESSOR_VERSION`.
   - Si no configuras `DOCAI_PROCESSOR_VERSION`, el servicio usará la versión predeterminada del procesador.

## 6. Crear la cuenta de servicio y su clave JSON

1. Menú ☰ → **IAM y administración → Cuentas de servicio** → **Crear cuenta de servicio**.
   - Nombre: `document-autofill-cafelab`.
   - Descripción: "Usada por el microservicio document-autofill-cafelab para procesar documentos".
2. En **Otorgar a esta cuenta de servicio acceso al proyecto**, agrega **solo** este rol:
   - **Usuario de la API de Document AI** (`roles/documentai.apiUser`).
   - No agregues Editor, Propietario ni Administrador de Document AI.
3. Haz clic en **Listo**.
4. Abre la cuenta creada → pestaña **Claves** → **Agregar clave → Crear clave nueva** → tipo **JSON** → **Crear**. Se descarga un archivo `.json`.
5. Guarda ese archivo **fuera del repositorio**, por ejemplo:
   - Windows: `C:\Users\<usuario>\.gcp\document-autofill-cafelab.json`
   - Linux/macOS: `~/.gcp/document-autofill-cafelab.json`
6. Nunca subas ese archivo a GitHub ni lo pegues en chats o issues. Si se filtra, elimínalo en la pestaña **Claves** y crea otro.

> Si la consola dice que la creación de claves está deshabilitada, la organización tiene activa la política `iam.disableServiceAccountKeyCreation`. En ese caso, pide a quien administre la organización que la desactive para este proyecto, o usa `gcloud auth application-default login` solo para pruebas locales.

## 7. Anotar los datos para el `.env`

Con lo anterior, completa tu `.env` local (nunca el `.env.example`):

```env
GCP_PROJECT_ID=<ID del proyecto, paso 1>
DOCAI_LOCATION=<us o eu, paso 3>
DOCAI_PROCESSOR_ID=<ID del procesador, paso 3>
DOCAI_PROCESSOR_VERSION=<ID de la versión, paso 5.4; opcional>
GOOGLE_APPLICATION_CREDENTIALS=<ruta absoluta al JSON, paso 6>
```

---

## 8. Verificar el procesador con `scripts/probar_procesador.py`

Este script envía un archivo local al procesador y muestra los campos extraídos con su confianza. No guarda nada.

### Requisitos

- Python 3.12.
- La librería oficial:

```bash
python -m venv .venv
# Windows (PowerShell)
.venv\Scripts\Activate.ps1
# Linux/macOS
source .venv/bin/activate

pip install google-cloud-documentai==3.17.0
```

### Variables de entorno

El script lee las mismas variables del paso 7. Defínelas en la terminal:

```powershell
# Windows (PowerShell)
$env:GCP_PROJECT_ID = "<proyecto>"
$env:DOCAI_LOCATION = "us"
$env:DOCAI_PROCESSOR_ID = "<procesador>"
$env:DOCAI_PROCESSOR_VERSION = "<versión>"   # opcional
$env:GOOGLE_APPLICATION_CREDENTIALS = "C:\Users\<usuario>\.gcp\document-autofill-cafelab.json"
```

```bash
# Linux/macOS
export GCP_PROJECT_ID="<proyecto>"
export DOCAI_LOCATION="us"
export DOCAI_PROCESSOR_ID="<procesador>"
export DOCAI_PROCESSOR_VERSION="<versión>"   # opcional
export GOOGLE_APPLICATION_CREDENTIALS="$HOME/.gcp/document-autofill-cafelab.json"
```

### Ejecutar

```bash
python scripts/probar_procesador.py ruta/a/guia-formato-x.pdf
```

Acepta `.pdf`, `.jpg`, `.jpeg` y `.png`.

Salida esperada (valores ilustrativos):

```text
Procesador: projects/<proyecto>/locations/us/processors/<procesador>/processorVersions/<versión>
Archivo:    guia-formato-x.pdf (application/pdf, 84.2 KB)
Páginas:    1

CAMPO                 CONFIANZA  VALOR
lot_name                   0.93  Finca El Mirador L-14
supplier_name              0.88  Cooperativa ...
coffee_type                0.91  Arábica
origin                     0.95  Villa Rica, Oxapampa, Perú
processing_method          0.62  Lavado
altitude_meters            0.97  1,650 msnm
initial_weight_kg          0.96  69
certifications             0.80  ORGANIC

Campos del esquema no encontrados: (ninguno)
```

### Qué revisar

- Aparecen los 8 nombres de campo. Si sale alguno en "no encontrados", revisa el nombre en el esquema (paso 4) o su descripción.
- Las confianzas son razonables (la mayoría por encima de 0.7).
- Si sale `403 PERMISSION_DENIED`: la cuenta de servicio no tiene el rol del paso 6, o el JSON es de otro proyecto.
- Si sale `404 NOT_FOUND`: el ID del procesador, de la versión o la región no coinciden.
- Si sale `400 FAILED_PRECONDITION`: la versión no está desplegada (paso 5.4).
