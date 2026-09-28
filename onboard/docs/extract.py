"""Plain text from an uploaded document, keeping one line per printed line so the
paragraph splitter can see leading numbers. No AI."""
from __future__ import annotations
import io


def extract_text(filename: str, data: bytes) -> str:
    name = filename.lower()
    if name.endswith('.docx'):
        import mammoth
        return mammoth.extract_raw_text(io.BytesIO(data)).value
    if name.endswith('.pdf'):
        import pdfplumber
        pages = []
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page in pdf.pages:
                pages.append(page.extract_text(layout=False) or '')
        return '\n'.join(pages)
    if name.endswith(('.txt', '.md')):
        return data.decode('utf-8', errors='replace')
    raise ValueError('Upload a .docx, .pdf or .txt file')
