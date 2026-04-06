#!/usr/bin/env python3
"""Test script for the analysis endpoint without PDF."""

import asyncio
import httpx
import json
import sys
import io
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


async def test_analysis_endpoint():
    """Test the analysis endpoint directly."""
    print("=" * 60)
    print("TEST DEL ENDPOINT /api/analysis/submit")
    print("=" * 60)

    # First, register/login to get token
    print("\n1. Creando usuario de prueba...")
    async with httpx.AsyncClient() as client:
        # Try to register
        register_resp = await client.post(
            'http://localhost:8000/api/auth/register',
            json={
                'email': 'test_providers@example.com',
                'password': 'testpass123',
                'name': 'Test User'
            }
        )
        print(f"   Register: {register_resp.status_code}")
        if register_resp.status_code not in [200, 201, 400]:
            print(f"   Error: {register_resp.text}")
            return 1

        # Login
        print("\n2. Haciendo login...")
        login_resp = await client.post(
            'http://localhost:8000/api/auth/login',
            json={
                'email': 'test_providers@example.com',
                'password': 'testpass123'
            }
        )
        if login_resp.status_code != 200:
            print(f"   Error login: {login_resp.text}")
            return 1

        token = login_resp.json()['access_token']
        print(f"   ✅ Token obtenido")

        # Read the test PDF file
        print("\n3. Leyendo PDF de prueba...")
        with open('test_cv_with_text.pdf', 'rb') as f:
            pdf_bytes = io.BytesIO(f.read())

        # Submit analysis
        print("\n4. Enviando análisis...")
        headers = {
            'Authorization': f'Bearer {token}'
        }
        files = {
            'file': ('test_cv.pdf', pdf_bytes, 'application/pdf')
        }
        data = {
            'job_text': 'Buscamos desarrollador Python con experiencia en FastAPI, PostgreSQL y Docker. Debe tener conocimientos de microservicios y CI/CD.'
        }

        submit_resp = await client.post(
            'http://localhost:8000/api/analysis/submit',
            headers=headers,
            files=files,
            data=data
        )

        print(f"   Status: {submit_resp.status_code}")
        if submit_resp.status_code != 202:
            print(f"   Error: {submit_resp.text}")
            return 1

        analysis_id = submit_resp.json()['id']
        print(f"   ✅ Análisis iniciado: {analysis_id}")

        # Poll for result
        print("\n5. Poll del estado (máx 60 segundos)...")
        for i in range(20):
            await asyncio.sleep(3)

            status_resp = await client.get(
                f'http://localhost:8000/api/analysis/{analysis_id}/status',
                headers=headers
            )
            status_data = status_resp.json()
            status = status_data['status']

            print(f"   Intento {i+1}: {status}")

            if status == 'completed':
                print(f"\n{'='*60}")
                print(f"✅ ANÁLISIS COMPLETADO")
                print(f"{'='*60}")
                print(f"\nScore: {status_data.get('compatibility_score', 'N/A')}")
                print(f"Result: {json.dumps(status_data.get('analysis_result', {}), indent=2)[:500]}...")
                return 0
            elif status == 'failed':
                print(f"\n{'='*60}")
                print(f"❌ ANÁLISIS FALLÓ")
                print(f"{'='*60}")
                print(f"\nError: {status_data.get('error_message', 'Unknown')}")
                return 1

        print(f"\n⏱️  Timeout: El análisis tardó demasiado tiempo")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(test_analysis_endpoint())
    sys.exit(exit_code)
