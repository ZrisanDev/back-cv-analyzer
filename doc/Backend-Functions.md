Eres un asistente experto en desarrollo backend.
Necesito que me ayudes a construir el backend de una
aplicación llamada "CV Analyzer" que analiza CVs contra
ofertas de trabajo.

AUTENTICACIÓN

- Registro de usuario con nombre, correo y contraseña
- Inicio de sesión con correo y contraseña
- Cierre de sesión
- Recuperación de contraseña por correo
- Protección de rutas privadas con tokens

EXTRACCIÓN Y ANÁLISIS

- Recibir un archivo CV en formato PDF
- Extraer automáticamente todo el texto del PDF
- Recibir una oferta de trabajo de dos formas posibles:
  - Texto pegado directamente
  - URL de una oferta (hacer scraping del contenido)
- Analizar el CV contra la oferta y retornar:
  - Puntuación de compatibilidad (0-100%)
  - Keywords presentes en la oferta que están en el CV
  - Keywords importantes de la oferta que faltan en el CV
  - Por cada keyword o tecnología faltante, indicar:
    - Qué es exactamente
    - Por qué es importante para ese puesto
    - Qué debe aprender o practicar para dominarla
    - Recursos o camino sugerido para aprenderla
  - Fortalezas detectadas del candidato
  - Debilidades o gaps detectados con sugerencias concretas
  - Resumen ejecutivo del análisis

HISTORIAL

- Guardar cada análisis asociado al usuario autenticado
- Consultar historial de análisis del usuario
- Obtener detalle de un análisis específico
- Eliminar un análisis del historial

ESTADÍSTICAS

- Calcular por usuario:
  - Total de análisis realizados
  - Promedio histórico de compatibilidad
  - Evolución de puntuaciones en el tiempo
  - Top keywords que más le han faltado históricamente

PAGOS CON MERCADOPAGO

- Cada análisis tiene un costo (definir precio)
- Crear preferencia de pago en MercadoPago
  antes de procesar el análisis
- Webhook para recibir confirmación de pago
- Solo procesar el análisis si el pago fue aprobado
- Guardar estado del pago asociado a cada análisis
- Manejar pagos fallidos, pendientes y aprobados

IA-ANALYZER API

- Cerebras
- Groq
- Ollama
