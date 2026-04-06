# CV Analyzer Backend

Backend API para análisis de currículums con inteligencia artificial, sistema de pagos integrado con Mercado Pago, y gestión de créditos para usuarios.

## 🚀 Tecnologías

### Web Framework & Server
- **FastAPI** (0.115.6) - Framework async para APIs REST
- **Uvicorn** (0.34.0) - Servidor ASGI

### Database
- **PostgreSQL** (16) - Base de datos relacional
- **SQLAlchemy** (2.0.36) - ORM async
- **Alembic** (1.14.1) - Migraciones de base de datos
- **AsyncPG** (0.30.0) - Driver async para PostgreSQL

### Autenticación y Seguridad
- **python-jose** (3.3.0) - JWT (JSON Web Tokens)
- **Passlib** (1.7.4) + **bcrypt** (4.0.1) - Hashing de contraseñas

### Validación y Configuración
- **Pydantic** (2.10.4) - Validación de datos
- **Pydantic Settings** (2.7.1) - Configuración por variables de entorno
- **python-dotenv** (1.0.1) - Carga de variables de entorno
- **email-validator** (2.2.0) - Validación de emails

### HTTP Client
- **httpx** (0.28.1) - Cliente HTTP async

### Procesamiento de Documentos
- **BeautifulSoup4** (4.12.3) - Parseo de HTML
- **PyPDF** (5.1.0) - Extracción de texto de PDFs

### Scraping
- **Playwright** (1.49.0) - Automatización de navegadores

### Pagos
- **MercadoPago SDK** (2.3.0) - Integración con pasarela de pagos

### Email
- **aiosmtplib** (3.0.2) - Cliente SMTP async

### IA Providers
- **Google Generative AI** (1.70.0) - Gemini models
- **Cerebras Cloud SDK** (1.67.0) - Llama models
- **Groq** (1.1.2) - Fast inference models

## 📦 Instalación

### Requisitos Previos
- Python 3.11+
- PostgreSQL 16+
- Docker y Docker Compose (opcional, para la base de datos)

### 1. Clonar el repositorio
```bash
git clone <repo-url>
cd back-analyzer-cv
```

### 2. Crear entorno virtual
```bash
python -m venv venv
source venv/bin/activate  # En Linux/Mac
# o
venv\Scripts\activate  # En Windows
```

### 3. Instalar dependencias
```bash
pip install -r requirements.txt
```

### 4. Configurar base de datos

**Opción A: Usar Docker Compose (Recomendado)**
```bash
docker-compose up -d
```

**Opción B: PostgreSQL local**
Asegúrate de tener PostgreSQL corriendo y crea la base de datos:
```sql
CREATE DATABASE cv_analyzer;
```

### 5. Configurar variables de entorno
```bash
cp .env.example .env
```

Edita el archivo `.env` con tus configuraciones:

```env
# Database
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/cv_analyzer

# Auth
SECRET_KEY=tu-clave-segura-random
ACCESS_TOKEN_EXPIRE_MINUTES=30

# MercadoPago (Sandbox para desarrollo)
MERCADOPAGO_ACCESS_TOKEN=TEST-your-access-token
MERCADOPAGO_PUBLIC_KEY=TEST-your-public-key

# AI Providers (configura al menos uno)
GEMINI_API_KEY=your-gemini-api-key
GEMINI_MODEL=gemini-2.0-flash

# Email (opcional, para confirmaciones)
GMAIL_EMAIL=your-email@gmail.com
GMAIL_APP_PASSWORD=your-app-password

# Billing
FREE_ANALYSIS_LIMIT=3
ANALYSIS_PRICE_USD=2.99

# CORS (para desarrollo)
CORS_ORIGINS=http://localhost:3000,http://localhost:5173
```

### 6. Ejecutar migraciones de base de datos
```bash
alembic upgrade head
```

### 7. Iniciar el servidor
```bash
uvicorn main:app --reload
```

El API estará disponible en: `http://localhost:8000`

### 8. Verificar instalación
```bash
curl http://localhost:8000/api/health
```

Deberías ver una respuesta JSON con el estado del servicio, base de datos y providers de IA disponibles.

## 📚 Documentación de la API

Una vez iniciado el servidor, la documentación interactiva está disponible en:
- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

## 🏗️ Estructura del Proyecto

```
back-analyzer-cv/
├── app/
│   ├── ai/               # Servicios y providers de IA
│   ├── analysis/          # Análisis de CVs
│   ├── auth/             # Autenticación y autorización
│   ├── payments/          # Sistema de pagos (MercadoPago)
│   ├── history/          # Historial de análisis
│   ├── stats/            # Estadísticas
│   └── shared/           # Utilidades compartidas (DB, email, etc.)
├── alembic/             # Migraciones de base de datos
├── main.py              # Entry point de la aplicación
└── requirements.txt      # Dependencias de Python
```

## 🔑 Endpoints Principales

| Ruta | Método | Descripción | Auth |
|-------|--------|-------------|-------|
| `/api/auth/register` | POST | Registro de usuario | No |
| `/api/auth/login` | POST | Iniciar sesión | No |
| `/api/analysis` | POST | Crear análisis de CV | Sí |
| `/api/payments/create-package-preference` | POST | Crear preferencia de pago | Sí |
| `/api/payments/webhook` | POST | Webhook MercadoPago | No |
| `/api/history` | GET | Historial de análisis | Sí |
| `/api/health` | GET | Health check | No |

## ⚠️ Notas

### Scraping de LinkedIn (Pendiente de Implementar)
El módulo de scraping para LinkedIn está actualmente **no implementado**. Playwright está instalado como dependencia pero no hay funcionalidad activa.

**Estado**: Pendiente
**Tecnología**: Playwright
**Objetivo**: Extraer información de perfiles de LinkedIn para enriquecer el análisis de CVs

### MercadoPago
- Configura las credenciales de sandbox para desarrollo
- Para producción, cambia `TEST-` por credenciales reales
- Configura `MERCADOPAGO_WEBHOOK_URL` para notificaciones de pago

### AI Providers
- Configura al menos un provider de IA en el archivo `.env`
- Los providers disponibles son: Gemini, Cerebras, Groq, y Ollama (local)
- El sistema fallback automáticamente si uno falla

## 🐛 Solución de Problemas

### Error de conexión a la base de datos
- Verifica que PostgreSQL esté corriendo: `docker ps`
- Verifica que las credenciales en `.env` sean correctas

### Error de migraciones
- Ejecuta: `alembic current` para ver la versión actual
- Si está desactualizado: `alembic upgrade head`

### AI Provider no responde
- Verifica que la API key sea correcta en `.env`
- Revisa los logs del servidor para ver el error específico

## 📝 Licencia

Este proyecto es propiedad privada. Todos los derechos reservados.

## 👤 Autor

[Your Name] - [Contact Information]
