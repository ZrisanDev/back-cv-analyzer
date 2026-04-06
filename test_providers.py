#!/usr/bin/env python3
"""Test script to verify AI providers fallback without PDF."""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from app.ai.service import AIAnalyzerService


async def test_providers():
    """Test the AI service with all providers."""
    print("=" * 60)
    print("TEST DE AI PROVIDERS - SIN PDF")
    print("=" * 60)

    # Create service
    print("\n1. Creando AIAnalyzerService...")
    service = AIAnalyzerService()

    print(f"\n2. Providers en orden de fallback:")
    for i, provider in enumerate(service._providers, 1):
        available = "✅" if provider.is_available else "❌"
        print(f"   {i}. {provider.name:12} {available}")

    print(f"\n3. Iniciando análisis...")
    print(f"   CV Text: 'Desarrollador Python con 5 años de experiencia en FastAPI, PostgreSQL y Docker'")
    print(f"   Job Desc: 'Buscamos Senior Developer con experiencia en Python, FastAPI y microservicios'")

    try:
        # Run analysis
        result = await service.analyze_cv(
            cv_text="Desarrollador Python con 5 años de experiencia en FastAPI, PostgreSQL y Docker. Tengo experiencia en microservicios, CI/CD y Kubernetes.",
            job_description="Buscamos Senior Developer con experiencia en Python, FastAPI y microservicios. Experiencia con Docker y PostgreSQL es requerida."
        )

        print(f"\n{'='*60}")
        print(f"✅ ANÁLISIS COMPLETADO EXITOSAMENTE")
        print(f"{'='*60}")
        print(f"\n📊 Score de compatibilidad: {result.compatibility_score}/100")
        print(f"\n✅ Keywords encontrados ({len(result.present_keywords)}):")
        for kw in result.present_keywords[:5]:
            print(f"   • {kw}")

        print(f"\n❌ Keywords faltantes ({len(result.missing_keywords)}):")
        for kw in result.missing_keywords[:5]:
            print(f"   • {kw}")

        print(f"\n💪 Fortalezas ({len(result.strengths)}):")
        for strength in result.strengths[:3]:
            print(f"   • {strength}")

        print(f"\n⚠️  Debilidades ({len(result.weaknesses)}):")
        for weakness in result.weaknesses[:3]:
            print(f"   • {weakness}")

        print(f"\n📝 Resumen ejecutivo:")
        print(f"   {result.executive_summary[:200]}...")

        return 0

    except Exception as e:
        print(f"\n{'='*60}")
        print(f"❌ ERROR EN EL ANÁLISIS")
        print(f"{'='*60}")
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(test_providers())
    sys.exit(exit_code)
