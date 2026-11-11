# document-autofill-cafelab

Microservicio de apoyo de CaféLab. Recibe la foto o el PDF de una guía de remisión (Formato X), la procesa con Google Cloud Document AI (Custom Extractor) y devuelve los datos del lote de café como **sugerencias** para autocompletar el formulario.

No es un bounded context: no valida ni crea lotes. Eso sigue siendo responsabilidad de Management, al que este servicio nunca llama.

> Estado: Fase 5. Document AI real, normalización de campos, timeout con un solo reintento y logs en JSON. Sin base de datos: no se guarda nada (ver [Persistencia desactivada](#persistencia-desactivada)).

## Endpoint

`POST /api/v1/documents/autofill` (multipart/form-data, campo `file`)

```bash
curl -H "X-User-Id: 42" -F "file=@guia.pdf" http://localhost:8000/api/v1/documents/autofill
```

| Código | Cuándo |
|---|---|
| 200 | Sugerencias del lote (`fields` y `warnings`) |
| 401 | Falta `X-User-Id` o no es un entero positivo |
| 413 | El archivo supera `MAX_FILE_MB` |
| 415 | El contenido no es JPG, PNG ni PDF |
| 422 | Archivo vacío, corrupto, protegido con contraseña, ausente, más de un archivo o PDF de más de 1 página |
| 502 | Document AI falló (después del reintento, si el error era transitorio): el usuario debe completar el formulario manualmente |
| 504 | Document AI no respondió a tiempo, tampoco en el reintento: el usuario debe completar el formulario manualmente |

### Normalización de campos

| Campo | Regla | Si no se cumple |
|---|---|---|
| `lotName`, `supplierName`, `origin` | Texto, espacios simplificados | `NOT_FOUND` si falta |
| `coffeeType` | Arábica, Robusta o Mezcla, sin distinguir mayúsculas ni tildes | `null` + `INVALID_VALUE` |
| `processingMethod` | Lavado, Natural, Honey, Fermentación anaeróbica o Maceración carbónica | `null` + `INVALID_VALUE` |
| `altitudeMeters`, `initialWeight` | Un solo número >= 0. El punto es decimal ("69.5" → 69.5). Una coma seguida de exactamente 3 dígitos separa miles ("1,650 msnm" → 1650); con otra cantidad de dígitos es decimal ("60,5" → 60.5) | `null` + `INVALID_NUMBER` (por ejemplo "-5", "1.650,5" o "1650 - 1800") |
| `certifications` | ORGANIC, FAIR_TRADE o RAINFOREST, reconocidas en español o inglés (tabla en [app/domain/vocabulary.py](app/domain/vocabulary.py)) | Se descarta + `UNKNOWN_CERTIFICATION` |

- Campo ausente: valor y confianza `null` + `NOT_FOUND`.
- Confianza menor a `CONFIDENCE_THRESHOLD`: el valor se devuelve igual + `LOW_CONFIDENCE`.
- Si el modelo devuelve el mismo campo dos veces, se usa el de mayor confianza. En `certifications`, la confianza es la más baja de la lista.

Notas:
- El formato se detecta por el contenido del archivo (sus primeros bytes), no por el nombre ni el `Content-Type`. Si el archivo dice ser JPG, PNG o PDF pero su contenido no lo es, se trata como corrupto (422).
- `extractionId` y `cached` se mantienen en la respuesta para no cambiar el contrato, pero valen siempre `null` y `false`: el servicio no guarda nada y cada petición llama a Document AI.

### Persistencia desactivada

El servicio **no usa base de datos**: no guarda las extracciones y no hay idempotencia. Enviar dos veces el mismo archivo llama dos veces a Document AI (cada página tiene costo).

El código de persistencia se conserva desactivado, por si se decide reactivarlo:
- [app/infrastructure/persistence/](app/infrastructure/persistence/): repositorio PostgreSQL (psycopg 3, `prepare_threshold=None` para el pooler de Supabase). No se importa desde la aplicación. Su `__init__.py` explica los pasos para reactivarlo.
- [db/migrations/001_create_document_extractions.sql](db/migrations/001_create_document_extractions.sql): **no hace falta ejecutarlo**.
- `psycopg` y `psycopg-pool` están comentados en `requirements.txt`.

### Timeout, reintento y logs

- Cada llamada a Document AI tiene un timeout de `DOCAI_TIMEOUT_SECONDS` (10 s por defecto).
- Ante un error transitorio (timeout, 5xx, `UNAVAILABLE`, `DEADLINE_EXCEEDED`) se hace **un solo reintento**, después de una pausa de 1 s. Los 4xx no se reintentan. El peor caso son unos 21 s (10 s + 1 s + 10 s).
- Si falla, responde 504 cuando el último error fue timeout y 502 en los demás casos.
- Los reintentos automáticos de la librería de Google (hasta 300 s) están desactivados con `retry=None`: el único reintento es el del servicio.

Los logs salen por stdout, una línea JSON por evento. Nunca incluyen el archivo, el hash completo ni los valores leídos:

```json
{"timestamp": "2026-11-11T05:20:03.936+00:00", "level": "INFO", "logger": "app.application.retrying_extractor", "event": "docai.call", "userId": 42, "fileHash": "0906add4d1dc", "attempt": 1, "durationMs": 4825, "ok": true}
{"timestamp": "2026-11-11T05:20:03.943+00:00", "level": "INFO", "logger": "app.application.autofill_document", "event": "autofill.request", "userId": 42, "fileHash": "0906add4d1dc", "result": "extracted", "durationMs": 4871}
```

| Evento | Cuándo | Campos |
|---|---|---|
| `autofill.request` | Una vez por petición | `userId`, `fileHash` (12 caracteres), `durationMs`, `result` (`extracted`, `rejected`, `docai_failed`, `docai_timeout`) y `reason` si falló |
| `docai.call` | Cada intento contra Document AI | `attempt`, `durationMs`, `ok`, y si falló: `errorType`, `cause`, `willRetry` |

## Arquitectura

Arquitectura hexagonal (puertos y adaptadores) con capas de DDD. Las dependencias apuntan hacia adentro: el dominio no conoce FastAPI ni Google.

```text
app/
├── domain/           Modelos del servicio y reglas de normalización (código puro)
├── application/      Casos de uso y puertos (interfaces) que necesita el dominio
├── infrastructure/   Adaptadores de salida: Document AI, archivos, logs y configuración
├── interfaces/http/  Adaptadores de entrada: routers de FastAPI y formato de errores
└── main.py           Une las capas y arranca el servidor
tests/
```

- Los tipos de la librería de Google no salen de `infrastructure`: el adaptador los traduce a objetos del dominio (capa anticorrupción).
- Los casos de uso dependen de puertos, así los tests usan adaptadores falsos sin llamar a la nube.

## Requisitos

- Python 3.12
- Un procesador de Document AI configurado (ver [docs/fase-0-google-cloud.md](docs/fase-0-google-cloud.md))

## Variables de entorno

Copia `.env.example` como `.env` y completa los valores. El servicio valida la configuración al arrancar y se detiene con la lista de variables inválidas. El mensaje nunca muestra los valores, para no exponer secretos.

| Variable | Obligatoria | Por defecto | Descripción |
|---|---|---|---|
| `GCP_PROJECT_ID` | Sí | | ID del proyecto de Google Cloud |
| `DOCAI_LOCATION` | Sí | | Región del procesador: `us` o `eu` |
| `DOCAI_PROCESSOR_ID` | Sí | | ID del procesador Custom Extractor |
| `DOCAI_PROCESSOR_VERSION` | No | versión predeterminada | ID de la versión del procesador |
| `GOOGLE_APPLICATION_CREDENTIALS` | No* | | Ruta al JSON de la cuenta de servicio. Si se define, el archivo debe existir |
| `CONFIDENCE_THRESHOLD` | No | `0.7` | Confianza mínima (0 a 1); por debajo se devuelve el campo con advertencia |
| `MAX_FILE_MB` | No | `10` | Tamaño máximo del archivo |
| `DOCAI_TIMEOUT_SECONDS` | No | `10` | Timeout por llamada a Document AI |
| `PORT` | No | `8000` | Puerto HTTP |

\* Fuera de Google Cloud hace falta para autenticarse con Document AI.

## Correr en local

```bash
python -m venv .venv
# Windows (PowerShell)
.venv\Scripts\Activate.ps1
# Linux/macOS
source .venv/bin/activate

pip install -r requirements-dev.txt
cp .env.example .env   # y completa los valores

python -m app.main
```

También con recarga automática para desarrollo:

```bash
uvicorn app.main:create_app --factory --reload --port 8000
```

Comprobar que está arriba:

```bash
curl http://localhost:8000/health
# {"status":"UP"}
```

La documentación OpenAPI queda en http://localhost:8000/docs.

## Tests

```bash
pytest
```

Los tests no leen el `.env` local ni llaman a servicios reales.

Las pruebas de integración de [tests/integration](tests/integration) son de la persistencia desactivada: se saltan solas.

## Docker

```bash
docker build -t document-autofill-cafelab .
docker run --rm -p 8000:8000 --env-file .env \
  -v /ruta/local/credenciales.json:/secrets/gcp.json:ro \
  -e GOOGLE_APPLICATION_CREDENTIALS=/secrets/gcp.json \
  document-autofill-cafelab
```

La imagen no incluye `.env` ni archivos JSON. Las credenciales se montan al ejecutar el contenedor.

## Identidad

Como los demás microservicios, este servicio no valida el JWT. Confía en la cabecera `X-User-Id` que inyecta el API Gateway después de validar el token. Si falta o no es numérica, responde 401.
