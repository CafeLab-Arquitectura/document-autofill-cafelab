# document-autofill-cafelab

Microservicio de apoyo de CaféLab. Recibe la foto o el PDF de una **guía de remisión (Formato X)**, la lee con **Google Cloud Document AI** (Custom Extractor) y devuelve los datos del lote de café como **sugerencias** para autocompletar el formulario de registro de lote.

- **No es un bounded context.** No valida ni crea lotes: eso sigue siendo de Management, al que este servicio nunca llama.
- **No guarda nada.** No guarda el archivo ni el resultado; cada petición llama a Document AI.
- **Stack:** Python 3.12, FastAPI y `google-cloud-documentai`.

## Contenido

- [Cómo funciona](#cómo-funciona)
- [Endpoint](#endpoint)
- [Probarlo con curl](#probarlo-con-curl)
- [Variables de entorno](#variables-de-entorno)
- [Correr en local](#correr-en-local)
- [Limitaciones](#limitaciones)
- [Reglas de normalización](#reglas-de-normalización)
- [Timeout, reintento y logs](#timeout-reintento-y-logs)
- [Arquitectura](#arquitectura)
- [Tests](#tests)
- [Docker](#docker)
- [Persistencia desactivada](#persistencia-desactivada)

## Cómo funciona

```text
Front ──JWT──► API Gateway ──X-User-Id──► document-autofill ──► Document AI (Custom Extractor)
                (valida el token)          │
                                           ├─ valida el archivo (tipo, tamaño, páginas)
                                           ├─ llama a Document AI (timeout 10 s, 1 reintento)
                                           └─ normaliza los campos y agrega advertencias
```

1. El API Gateway valida el JWT y reenvía la petición con la cabecera `X-User-Id`. Este servicio **no valida el JWT**: confía en esa cabecera, igual que los demás microservicios.
2. Se valida el archivo: JPG, PNG o PDF, máximo 10 MB, y si es PDF, una sola página.
3. Document AI lee la sección "4. DATOS DEL LOTE DE CAFÉ" con un procesador Custom Extractor en modo zero-shot (sin entrenamiento).
4. Los valores se normalizan a lo que acepta Management. Los dudosos se devuelven igual, con advertencias.

## Endpoint

### `POST /api/v1/documents/autofill`

- **Cuerpo:** `multipart/form-data` con un solo archivo en el campo `file`.
- **Cabecera:** `X-User-Id`, obligatoria. La pone el Gateway; en local se envía a mano.

Respuesta `200`:

```json
{
  "extractionId": null,
  "cached": false,
  "fields": {
    "lotName":          { "value": "Finca El Mirador L-14", "confidence": 0.93 },
    "supplierName":     { "value": "Cooperativa Agraria Ejemplo", "confidence": 0.88 },
    "coffeeType":       { "value": "Arábica", "confidence": 0.91 },
    "origin":           { "value": "Villa Rica, Oxapampa, Perú", "confidence": 0.95 },
    "processingMethod": { "value": "Lavado", "confidence": 0.62 },
    "altitudeMeters":   { "value": 1650, "confidence": 0.97 },
    "initialWeight":    { "value": 69, "confidence": 0.96 },
    "certifications":   { "value": ["ORGANIC"], "confidence": 0.80 }
  },
  "warnings": [
    { "field": "processingMethod", "code": "LOW_CONFIDENCE", "message": "Revisar: confianza 0.62 menor al umbral 0.7" }
  ]
}
```

- `value` es `null` si el campo no se encontró o no es válido; `confidence` es `null` si no se encontró.
- `supplierName` es solo informativo: el usuario elige el `supplierId` a mano.
- `extractionId` y `cached` se mantienen por compatibilidad con el contrato, pero valen siempre `null` y `false` (ver [Persistencia desactivada](#persistencia-desactivada)).

Errores, con el mismo formato que los otros servicios (`{ "message": "..." }`):

| Código | Cuándo | Ejemplo de `message` |
|---|---|---|
| 401 | Falta `X-User-Id` o no es un entero positivo | Usuario no autenticado: falta la cabecera X-User-Id o no es válida. |
| 413 | El archivo supera `MAX_FILE_MB` | El archivo supera el máximo de 10 MB. |
| 415 | El contenido no es JPG, PNG ni PDF | Formato no permitido. Usa JPG, PNG o PDF. |
| 422 | Archivo vacío, corrupto, protegido con contraseña, ausente, más de un archivo, o PDF de más de 1 página | El PDF tiene 2 páginas; solo se acepta un PDF de 1 página. |
| 502 | Document AI falló (después del reintento, si el error era transitorio) | No se pudo leer el documento automáticamente. Completa el formulario manualmente. |
| 504 | Document AI no respondió a tiempo, tampoco en el reintento | La lectura automática del documento tardó demasiado. Completa el formulario manualmente. |

Ante un 502 o un 504, el front debe dejar que el usuario complete el formulario a mano.

La documentación interactiva (OpenAPI) está en **`/docs`**, con el contrato, los campos, los códigos de error y ejemplos.

### `GET /health`

Responde `{"status":"UP"}`.

## Probarlo con curl

**Directo al servicio** (en local, con la cabecera `X-User-Id` a mano):

```bash
curl -H "X-User-Id: 42" -F "file=@guia_formato_X_ejemplo.pdf" \
  http://localhost:8000/api/v1/documents/autofill
```

En **Windows PowerShell** hay que escribir `curl.exe`, porque `curl` es un alias de `Invoke-WebRequest`:

```powershell
curl.exe -H "X-User-Id: 42" -F "file=@C:\ruta\guia_formato_X_ejemplo.pdf" http://localhost:8000/api/v1/documents/autofill
```

**A través del API Gateway** (con el JWT de sign-in; el Gateway pone el `X-User-Id`):

```bash
curl -H "Authorization: Bearer <token>" -F "file=@guia_formato_X_ejemplo.pdf" \
  http://localhost:8080/api/v1/documents/autofill
```

Más casos:

```bash
# 401: sin X-User-Id
curl -F "file=@guia.pdf" http://localhost:8000/api/v1/documents/autofill

# 415: formato no permitido
curl -H "X-User-Id: 42" -F "file=@notas.txt" http://localhost:8000/api/v1/documents/autofill
```

También se puede probar desde http://localhost:8000/docs → `POST /api/v1/documents/autofill` → **Try it out**.

## Variables de entorno

Copia `.env.example` como `.env` y completa los valores. **Nunca subas el `.env` ni el JSON de credenciales**: los dos están en el `.gitignore`.

El servicio valida la configuración al arrancar. Si algo falta o es inválido, se detiene y lista las variables con problemas, sin mostrar sus valores.

| Variable | Obligatoria | Por defecto | Descripción |
|---|---|---|---|
| `GCP_PROJECT_ID` | Sí | | ID del proyecto de Google Cloud |
| `DOCAI_LOCATION` | Sí | | Región del procesador: `us` o `eu` |
| `DOCAI_PROCESSOR_ID` | Sí | | ID del procesador Custom Extractor |
| `DOCAI_PROCESSOR_VERSION` | No | versión predeterminada | ID de la versión del procesador |
| `GOOGLE_APPLICATION_CREDENTIALS` | No* | | Ruta al JSON de la cuenta de servicio (rol *Document AI API User*). Si se define, el archivo debe existir |
| `CONFIDENCE_THRESHOLD` | No | `0.7` | Confianza mínima (0 a 1). Por debajo, el campo se devuelve igual, con advertencia `LOW_CONFIDENCE` |
| `MAX_FILE_MB` | No | `10` | Tamaño máximo del archivo |
| `DOCAI_TIMEOUT_SECONDS` | No | `10` | Timeout de cada llamada a Document AI |
| `PORT` | No | `8000` | Puerto HTTP |

\* Fuera de Google Cloud hace falta para autenticarse con Document AI.

Para crear el procesador y la cuenta de servicio, ver [docs/fase-0-google-cloud.md](docs/fase-0-google-cloud.md). El script [scripts/probar_procesador.py](scripts/probar_procesador.py) prueba el procesador con un archivo local antes de levantar el servicio.

## Correr en local

```bash
python -m venv .venv
# Windows (PowerShell)
.venv\Scripts\Activate.ps1
# Linux/macOS
source .venv/bin/activate

pip install -r requirements-dev.txt
cp .env.example .env      # y completa los valores

python -m app.main        # http://localhost:8000
```

Con recarga automática para desarrollo:

```bash
uvicorn app.main:create_app --factory --reload --port 8000
```

## Limitaciones

- **Una página por documento.** Un PDF de más de una página se rechaza con 422. Las imágenes (JPG, PNG) cuentan como una página.
- **Máximo 10 MB** por archivo (`MAX_FILE_MB`), y un solo archivo por petición.
- **Sin entrenamiento.** El procesador Custom Extractor funciona en modo zero-shot: lee bien el Formato X del equipo, pero otros formatos de guía pueden dar campos vacíos o equivocados.
- **Son sugerencias.** Los valores pueden estar mal: el usuario debe revisarlos antes de guardar el lote, sobre todo los que traen advertencias.
- **La confianza casi siempre es 1.0.** En zero-shot, Document AI suele devolver confianza 1.0, así que `LOW_CONFIDENCE` aparece poco.
- **Sin caché.** Enviar dos veces el mismo archivo llama dos veces a Document AI, y cada página tiene costo.
- **Tiempo de respuesta:** unos 4 a 6 s por guía. El peor caso, con timeout y reintento, es de unos 21 s.

## Reglas de normalización

| Campo | Regla | Si no se cumple |
|---|---|---|
| `lotName`, `supplierName`, `origin` | Texto, con espacios simplificados | `null` + `NOT_FOUND` si falta |
| `coffeeType` | Arábica, Robusta o Mezcla, sin distinguir mayúsculas ni tildes ("arabica" → "Arábica") | `null` + `INVALID_VALUE` |
| `processingMethod` | Lavado, Natural, Honey, Fermentación anaeróbica o Maceración carbónica | `null` + `INVALID_VALUE` |
| `altitudeMeters`, `initialWeight` | Un solo número >= 0. El punto es decimal ("69.5" → 69.5). Una coma seguida de exactamente 3 dígitos separa miles ("1,650 msnm" → 1650); con otra cantidad de dígitos es decimal ("60,5" → 60.5) | `null` + `INVALID_NUMBER` (por ejemplo "-5", "1.650,5" o "1650 - 1800") |
| `certifications` | ORGANIC, FAIR_TRADE o RAINFOREST, reconocidas en español o inglés ("Orgánico", "Comercio Justo", "Rainforest Alliance"…). Tabla en [app/domain/vocabulary.py](app/domain/vocabulary.py) | Se descarta + `UNKNOWN_CERTIFICATION` |

- Si el modelo devuelve el mismo campo dos veces, se usa el de mayor confianza. En `certifications`, la confianza es la más baja de la lista.
- `LOW_CONFIDENCE` aparece cuando la confianza es menor a `CONFIDENCE_THRESHOLD`; el valor se devuelve igual.
- El formato del archivo se detecta por su contenido (los primeros bytes), no por el nombre ni el `Content-Type`.

## Timeout, reintento y logs

- Cada llamada a Document AI tiene un timeout de `DOCAI_TIMEOUT_SECONDS` (10 s).
- Ante un error transitorio (timeout, 5xx, `UNAVAILABLE`, `DEADLINE_EXCEEDED`), el servicio hace **un solo reintento**, después de una pausa de 1 s. Los 4xx no se reintentan.
- Si falla, responde 504 cuando el último error fue un timeout y 502 en los demás casos.
- Los reintentos automáticos de la librería de Google (hasta 300 s) están desactivados con `retry=None`: el único reintento es el del servicio.

Los logs salen por stdout, una línea JSON por evento. Nunca incluyen el archivo, el hash completo ni los valores leídos:

```json
{"timestamp": "2026-11-11T05:20:03.936+00:00", "level": "INFO", "logger": "app.application.retrying_extractor", "event": "docai.call", "userId": 42, "fileHash": "0906add4d1dc", "attempt": 1, "durationMs": 4825, "ok": true}
{"timestamp": "2026-11-11T05:20:03.943+00:00", "level": "INFO", "logger": "app.application.autofill_document", "event": "autofill.request", "userId": 42, "fileHash": "0906add4d1dc", "result": "extracted", "durationMs": 4871}
```

| Evento | Cuándo | Campos |
|---|---|---|
| `autofill.request` | Una vez por petición | `userId`, `fileHash` (los 12 primeros caracteres del SHA-256 de archivo + userId), `durationMs`, `result` (`extracted`, `rejected`, `docai_failed`, `docai_timeout`) y `reason` si falló |
| `docai.call` | Cada intento contra Document AI | `attempt`, `durationMs`, `ok`, y si falló: `errorType`, `cause`, `willRetry` |

## Arquitectura

Arquitectura hexagonal (puertos y adaptadores) con capas de DDD. Las dependencias apuntan hacia adentro: el dominio no conoce FastAPI ni Google.

```text
app/
├── domain/           Modelos y reglas: validación del archivo, normalización, vocabularios
├── application/      Caso de uso, puertos y política de reintento
├── infrastructure/   Adaptadores de salida: Document AI, lectura de archivos, logs y configuración
├── interfaces/http/  Adaptadores de entrada: routers de FastAPI, identidad y formato de errores
└── main.py           Une las capas y arranca el servidor
tests/
```

- **Capa anticorrupción:** el adaptador de Document AI traduce las respuestas y los errores de Google a objetos propios del servicio. Ningún tipo de Google sale de `infrastructure`.
- **Reintento como decorador:** `RetryingDocumentExtractor` envuelve cualquier extractor, así la política se prueba sin la nube.
- Los casos de uso dependen de puertos; los tests usan adaptadores falsos.

## Tests

```bash
pytest
```

Los tests no leen el `.env` local ni llaman a Google Cloud. Cubren:
- la validación del archivo y la identidad;
- la normalización y las advertencias;
- el adaptador de Document AI, con respuestas simuladas;
- el reintento, el timeout y los logs;
- el contrato OpenAPI.

## Docker

```bash
docker build -t document-autofill-cafelab .
docker run --rm -p 8000:8000 --env-file .env \
  -v /ruta/local/credenciales.json:/secrets/gcp.json:ro \
  -e GOOGLE_APPLICATION_CREDENTIALS=/secrets/gcp.json \
  document-autofill-cafelab
```

La imagen no incluye `.env` ni archivos JSON: las credenciales se montan al ejecutar el contenedor.

En el API Gateway, la ruta `/api/v1/documents/**` apunta a este servicio con una URL fija (`DOCUMENT_AUTOFILL_URL`). Este servicio **no se registra en Eureka**.

## Persistencia desactivada

El servicio no usa base de datos: no guarda las extracciones y no hay idempotencia.

El código se conserva desactivado por si se decide reactivarlo:
- [app/infrastructure/persistence/](app/infrastructure/persistence/): repositorio PostgreSQL. No se importa desde la aplicación; su `__init__.py` explica los pasos para reactivarlo.
- [db/migrations/001_create_document_extractions.sql](db/migrations/001_create_document_extractions.sql): **no hace falta ejecutarlo**.
- `psycopg` y `psycopg-pool` están comentados en `requirements.txt`.
