#!/usr/bin/env python3
"""Create a test PDF with text content using fpdf."""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def create_test_pdf():
    """Create a PDF with sample CV content."""
    try:
        from fpdf import FPDF

        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)

        text = """Juan Pérez
Desarrollador Python Senior

EXPERIENCIA PROFESSIONAL

Senior Python Developer | Tech Corp (2020 - Present)
- Desarrollo de APIs REST con FastAPI
- Implementacion de microservicios con Docker y Kubernetes
- Optimizacion de consultas SQL en PostgreSQL
- CI/CD con GitHub Actions

Python Developer | StartupXYZ (2018 - 2020)
- Desarrollo de aplicaciones web con Django
- Integracion con APIs de terceros
- Tests automatizados con pytest

TECNOLOGIAS
- Python: 5 anos
- FastAPI: 3 anos
- PostgreSQL: 4 anos
- Docker: 3 anos
- Kubernetes: 2 anos
- CI/CD: 3 anos

EDUCACION
- Ingenieria en Computacion | Universidad (2014 - 2018)
"""

        # Write text to PDF
        lines = text.split('\n')
        y = 10
        for line in lines:
            pdf.cell(0, 10, line, ln=True)
            y += 10
            if y > 280:
                pdf.add_page()
                y = 10

        return pdf.output(dest='S').encode('latin-1')

    except ImportError:
        # If fpdf not available, create minimal PDF with pypdf
        from pypdf import PdfWriter
        import io

        pdf_writer = PdfWriter()
        page = pdf_writer.add_blank_page(width=612, height=792)
        pdf_bytes = io.BytesIO()
        pdf_writer.write(pdf_bytes)
        pdf_bytes.seek(0)

        # Note: This will be empty, but at least valid PDF
        return pdf_bytes.getvalue()


if __name__ == "__main__":
    pdf_bytes = create_test_pdf()
    with open("test_cv.pdf", "wb") as f:
        f.write(pdf_bytes)
    print("✅ test_cv.pdf creado")
