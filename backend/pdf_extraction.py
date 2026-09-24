"""Local, page-by-page PDF conversion with explicit extraction failures."""
import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from pypdf import PdfReader


@dataclass
class PageText:
    page: int
    text: str
    method: str
    error: str | None = None


@dataclass
class Extraction:
    source: str
    pages: list[PageText]

    @property
    def ready(self) -> bool:
        return bool(self.pages) and all(p.error is None for p in self.pages)

    @property
    def text(self) -> str:
        return "\n\n".join(
            f"--- Page {p.page} ---\n{p.text}"
            + (f"\n[REVIEW REQUIRED: {p.error}]" if p.error else "")
            for p in self.pages
        )


def clean_text(text: str) -> str:
    # Preserve layout whitespace. This is normalization, not prompt-injection protection.
    return "".join(c for c in text if c.isprintable() or c in "\n\t\r").strip()


def ocr_page(path: Path, index: int) -> str:
    """Render locally at 300 DPI; imports stay optional for text-only PDFs."""
    try:
        import pypdfium2 as pdfium
        import pytesseract
    except ImportError as exc:
        raise RuntimeError("OCR dependencies missing; run pip install -r requirements.txt") from exc

    with pdfium.PdfDocument(str(path)) as document:
        page = document[index]
        try:
            bitmap = page.render(scale=300 / 72)
            try:
                image = bitmap.to_pil()
                try:
                    return pytesseract.image_to_string(image, lang="eng", timeout=120)
                finally:
                    image.close()
            finally:
                bitmap.close()
        finally:
            page.close()


def extract_pdf(path: Path) -> Extraction:
    pages = []
    with path.open("rb") as stream:
        reader = PdfReader(stream)
        if reader.is_encrypted and not reader.decrypt(""):
            raise ValueError("Password-protected PDF: provide an unlocked copy.")
        if not reader.pages:
            raise ValueError("PDF contains no pages.")
        for number, page in enumerate(reader.pages, start=1):
            text = ""
            try:
                text = clean_text(page.extract_text(extraction_mode="layout") or "")
                # Images can contain scanned text even when a header is selectable.
                needs_ocr = sum(c.isalnum() for c in text) < 40 or bool(page.images)
            except Exception:
                needs_ocr = True
            if not needs_ocr:
                pages.append(PageText(number, text, "embedded"))
                continue
            try:
                recognized = clean_text(ocr_page(path, number - 1))
                if not recognized or sum(c.isalnum() for c in recognized) < 40:
                    raise ValueError("Little or no readable text; inspect this page (it may be blank).")
                pages.append(PageText(number, recognized, "ocr"))
            except Exception as exc:
                pages.append(PageText(number, text, "failed", str(exc)))
    return Extraction(path.name, pages)


def save_extraction(result: Extraction, directory: Path, stem: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    text_path = directory / f"{stem}_extracted.txt"
    text_path.write_text(result.text, encoding="utf-8")
    report = asdict(result)
    report["ready_for_evaluation"] = result.ready
    (directory / f"{stem}_extraction.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return text_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--output", type=Path, default=Path("Output"))
    args = parser.parse_args()
    try:
        result = extract_pdf(args.pdf)
        destination = save_extraction(result, args.output, args.pdf.stem)
    except Exception as exc:
        print(f"Extraction failed: {exc}")
        return 1
    print(f"Saved {destination}; ready for evaluation: {result.ready}")
    for page in result.pages:
        if page.error:
            print(f"Page {page.page}: {page.error}")
    return 0 if result.ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
