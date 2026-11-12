"""PERSISTENCIA DESACTIVADA.

El servicio no usa base de datos: no guarda extracciones y no hay idempotencia.
Este paquete no se importa desde la aplicación. Se conserva para poder reactivar
la persistencia (tabla document_autofill.document_extractions) si se decide más adelante.

Para reactivarla:
1. Descomentar psycopg y psycopg-pool en requirements.txt.
2. Agregar DATABASE_URL a la configuración (app/infrastructure/config.py).
3. Inyectar un ExtractionRepository en AutofillDocument y crear PostgresExtractionRepository en app/main.py.
4. Ejecutar db/migrations/001_create_document_extractions.sql.

La versión con persistencia activa está en el historial de git (commit aed4905).
"""
