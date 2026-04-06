#!/usr/bin/env python3
"""Script para verificar qué versión del código está cargada."""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def check_code_version():
    """Verificar versión del código cargado."""
    print("=" * 80)
    print("VERIFICACIÓN DE VERSIÓN DEL CÓDIGO")
    print("=" * 80)

    # Importar y verificar
    print("\n1. Importando módulos...")
    try:
        from app.ai import service as ai_service
        print("   ✅ app.ai.service importado")
    except Exception as e:
        print(f"   ❌ Error importando app.ai.service: {e}")
        return

    try:
        from app.analysis import services as analysis_services
        print("   ✅ app.analysis.services importado")
    except Exception as e:
        print(f"   ❌ Error importando app.analysis.services: {e}")
        return

    # Verificar orden de providers
    print("\n2. Verificando orden de providers...")
    test_service = ai_service.AIAnalyzerService()
    provider_names = test_service.provider_names
    print(f"   Providers: {provider_names}")

    if provider_names[1] == 'groq':
        print("   ✅ Código ACTUALIZADO (Groq es el 2do provider)")
    elif provider_names[1] == 'cerebras':
        print("   ❌ Código ANTIGUO (Cerebras es el 2do provider)")
    else:
        print(f"   ⚠️  Orden desconocido: {provider_names[1]}")

    # Verificar si existen los mensajes de debug
    print("\n3. Buscando mensajes de debug en el código...")
    import inspect

    ai_source = inspect.getsource(ai_service.AIAnalyzerService)
    if "🔥🔥🔥 AI SERVICE MODULE LOADED - VERSION 2025-04-06" in ai_source:
        print("   ✅ Código con mensajes de debug encontrados")
    else:
        print("   ❌ Código sin mensajes de debug (versión antigua)")

    analysis_source = inspect.getsource(analysis_services._perform_analysis)
    if "🔥🔥🔥 ANALYSIS MODULE LOADED - VERSION 2025-04-06" in analysis_source:
        print("   ✅ Código de análisis con mensajes de debug encontrados")
    else:
        print("   ❌ Código de análisis sin mensajes de debug (versión antigua)")

    print("\n" + "=" * 80)
    print("CONCLUSIÓN")
    print("=" * 80)

    if provider_names[1] == 'groq':
        print("✅ EL CÓDIGO ESTÁ ACTUALIZADO - El fallback debería funcionar a Groq")
        print("\nSi no ves el fallback funcionando:")
        print("   1. MATA todos los procesos: pkill -9 -f uvicorn")
        print("   2. Limpia caché: find . -type d -name __pycache__ -exec rm -rf {} +")
        print("   3. Reactiva venv: deactivate && source venv/bin/activate")
        print("   4. Inicia: python -m uvicorn main:app --host 0.0.0.0 --port 8000")
        return 0
    else:
        print("❌ EL CÓDIGO ESTÁ ANTIGUO - Necesitas limpiar caché y reiniciar")
        print("\nPasos para corregir:")
        print("   1. MATA todos los procesos: pkill -9 -f uvicorn")
        print("   2. Limpia caché: find . -type d -name __pycache__ -exec rm -rf {} +")
        print("   3. Reactiva venv: deactivate && source venv/bin/activate")
        print("   4. Inicia: python -m uvicorn main:app --host 0.0.0.0 --port 8000")
        return 1


if __name__ == "__main__":
    exit_code = check_code_version()
    sys.exit(exit_code)
