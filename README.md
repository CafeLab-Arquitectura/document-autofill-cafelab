# document-autofill-cafelab

Microservicio de apoyo de CaféLab. Recibe la foto o el PDF de una guía de remisión (Formato X), la procesa con Google Cloud Document AI (Custom Extractor) y devuelve los datos del lote de café como **sugerencias** para autocompletar el formulario.

No es un bounded context: no valida ni crea lotes. Eso sigue siendo responsabilidad de Management, al que este servicio nunca llama.

> Estado: Fase 4. Document AI real, normalización de campos e idempotencia con PostgreSQL. El reintento llega en la Fase 5.

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
| 502 | Document AI falló: el usuario debe completar el formulario manualmente |
| 503 | La base de datos no responde: el usuario debe completar el formulario manualmente |

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
### Idempotencia

Cada petición calcula `SHA-256(bytes del archivo + userId en decimal)`.

- Si ya existe un registro para ese hash y ese usuario, devuelve el resultado guardado con `"cached": true` y **no** vuelve a llamar a Document AI.
- Si no existe, procesa el archivo, lo guarda y devuelve `"cached": false`.
- Si llegan dos peticiones iguales a la vez, el `UNIQUE (user_id, file_hash)` deja guardar solo una. La otra recibe ese mismo registro.
- Solo se guardan los campos y las advertencias, **nunca el archivo**. Los fallos (archivo rechazado, error de Document AI) no se guardan.
- El resultado guardado conserva las advertencias con las que se creó: si después cambia `CONFIDENCE_THRESHOLD`, no se recalcula.
- Si la base no responde, el servicio devuelve 503 **sin** llamar a Document AI, para no pagar una lectura que no se puede guardar.

## Arquitectura

Arquitectura hexagonal (puertos y adaptadores) con capas de DDD. Las dependencias apuntan hacia adentro: el dominio no conoce FastAPI, Google ni PostgreSQL.

```text
app/
├── domain/           Modelos del servicio y reglas de normalización (código puro)
├── application/      Casos de uso y puertos (interfaces) que necesita el dominio
├── infrastructure/   Adaptadores de salida: Document AI, PostgreSQL y configuración
├── interfaces/http/  Adaptadores de entrada: routers de FastAPI y formato de errores
└── main.py           Une las capas y arranca el servidor
tests/
```

- Los tipos de la librería de Google no salen de `infrastructure`: el adaptador los traduce a objetos del dominio (capa anticorrupción).
- Los casos de uso dependen de puertos, así los tests usan adaptadores falsos o en memoria sin llamar a la nube.

## Requisitos

- Python 3.12
- Un procesador de Document AI configurado (ver [docs/fase-0-google-cloud.md](docs/fase-0-google-cloud.md))
- Una base PostgreSQL (Supabase)

## Variables de entorno

Copia `.env.example` como `.env` y completa los valores. El servicio valida la configuración al arrancar y se detiene con la lista de variables inválidas. El mensaje nunca muestra los valores, para no exponer secretos.

| Variable | Obligatoria | Por defecto | Descripción |
|---|---|---|---|
| `GCP_PROJECT_ID` | Sí | | ID del proyecto de Google Cloud |
| `DOCAI_LOCATION` | Sí | | Región del procesador: `us` o `eu` |
| `DOCAI_PROCESSOR_ID` | Sí | | ID del procesador Custom Extractor |
| `DOCAI_PROCESSOR_VERSION` | No | versión predeterminada | ID de la versión del procesador |
| `GOOGLE_APPLICATION_CREDENTIALS` | No* | | Ruta al JSON de la cuenta de servicio. Si se define, el archivo debe existir |
| `DATABASE_URL` | Sí | | `postgresql://USUARIO:CONTRASEÑA@HOST:6543/postgres` |
| `CONFIDENCE_THRESHOLD` | No | `0.7` | Confianza mínima (0 a 1); por debajo se devuelve el campo con advertencia |
| `MAX_FILE_MB` | No | `10` | Tamaño máximo del archivo |
| `DOCAI_TIMEOUT_SECONDS` | No | `10` | Timeout por llamada a Document AI |
| `PORT` | No | `8000` | Puerto HTTP |

\* Fuera de Google Cloud hace falta para autenticarse con Document AI.

### Supabase y prepared statements

Los servicios de CaféLab se conectan al pooler de Supabase en **modo transacción (puerto 6543)**, que no soporta prepared statements. psycopg 3 los crea solo cuando una consulta se repite varias veces. Este servicio los desactiva con `prepare_threshold=None` (ver [postgres_repository.py](app/infrastructure/persistence/postgres_repository.py)).

`DATABASE_URL` usa el formato de Python, no el de JDBC:

```env
DATABASE_URL=postgresql://postgres.<project-ref>:<contraseña>@aws-0-us-east-1.pooler.supabase.com:6543/postgres?sslmode=require
```

Si la contraseña tiene caracteres especiales, codifícalos en la URL (`@` → `%40`, `#` → `%23`).

### Migración

El script [db/migrations/001_create_document_extractions.sql](db/migrations/001_create_document_extractions.sql) crea el esquema `document_autofill` y la tabla `document_extractions`. **Se ejecuta a mano, una vez**, con el mismo usuario de `DATABASE_URL`: por ejemplo, desde el SQL Editor de Supabase o con `psql "$DATABASE_URL" -f db/migrations/001_create_document_extractions.sql`. Se puede repetir sin problema.

Sin la tabla, el servicio arranca, pero `POST /api/v1/documents/autofill` responde 503.

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

Los tests no leen el `.env` local ni llaman a servicios reales. Usan un repositorio en memoria.

Las pruebas de integración del repositorio PostgreSQL ([tests/integration](tests/integration)) se saltan si no existe `TEST_DATABASE_URL`. Úsalas **solo con una base local o desechable**, nunca con Supabase: crean el esquema y borran las filas que insertan.

```bash
docker run -d --rm --name autofill-pg-test -e POSTGRES_PASSWORD=test -p 55432:5432 postgres:16-alpine
TEST_DATABASE_URL=postgresql://postgres:test@localhost:55432/postgres pytest tests/integration
docker rm -f autofill-pg-test
```

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
