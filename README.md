# document-autofill-cafelab

Microservicio de apoyo de CaféLab. Recibe la foto o el PDF de una guía de remisión (Formato X), la procesa con Google Cloud Document AI (Custom Extractor) y devuelve los datos del lote de café como **sugerencias** para autocompletar el formulario.

No es un bounded context: no valida ni crea lotes. Eso sigue siendo responsabilidad de Management, al que este servicio nunca llama.

> Estado: proyecto base (Fase 1). Por ahora solo expone `GET /health`.

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

Los servicios de CaféLab se conectan al pooler de Supabase en **modo transacción (puerto 6543)**, que no soporta prepared statements. Este servicio usará psycopg 3 con `prepare_threshold=None` para desactivarlos. Se configura en la Fase 4, junto con la persistencia.

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

## Docker

```bash
docker build -t document-autofill-cafelab .
docker run --rm -p 8000:8000 --env-file .env \
  -v /ruta/local/credenciales.json:/secrets/gcp.json:ro \
  -e GOOGLE_APPLICATION_CREDENTIALS=/secrets/gcp.json \
  document-autofill-cafelab
```

La imagen no incluye `.env` ni archivos JSON. Las credenciales se montan al ejecutar el contenedor.

## Identidad (se implementa en la Fase 2)

Como los demás microservicios, este servicio no valida el JWT. Confía en la cabecera `X-User-Id` que inyecta el API Gateway después de validar el token. Si falta o no es numérica, responde 401.
