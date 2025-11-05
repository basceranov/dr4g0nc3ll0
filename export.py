# export.py
import os, tempfile
import markdown2

def _html_wrap(body_html: str) -> str:
    return f"""<!doctype html>
<html lang="it">
<meta charset="utf-8">
<title>OSINT Report</title>
<style>
  @page {{ size: A4; margin: 18mm; }}
  body {{ font-family: Arial, Helvetica, sans-serif; line-height: 1.35; font-size: 12pt; }}
  h1,h2,h3 {{ margin-top: 1.2em; }}
  code, pre {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace; }}
  a {{ text-decoration: none; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ border: 1px solid #ddd; padding: 6px; }}
  blockquote {{ border-left: 3px solid #ccc; margin: 0; padding: .5em 1em; color: #555; }}
</style>
<body>
{body_html}
</body>
</html>"""

def save_markdown(md: str, path: str):
    with open(path, "w", encoding="utf-8") as f:
        f.write(md)

def save_pdf_from_markdown(md: str, path: str):
    html = markdown2.markdown(md)
    full_html = _html_wrap(html)

    # 1) Prova WeasyPrint se disponibile (tipicamente ok su Linux)
    try:
        from weasyprint import HTML
        HTML(string=full_html).write_pdf(path)
        return
    except Exception as e_weasy:
        pass  # fallback a Playwright

    # 2) Fallback: Playwright/Chromium (consigliato su Windows)
    try:
        from playwright.sync_api import sync_playwright
        with tempfile.NamedTemporaryFile(delete=False, suffix=".html", mode="w", encoding="utf-8") as tmp:
            tmp.write(full_html)
            tmp_path = tmp.name

        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(f"file:///{tmp_path}", wait_until="load")
            page.pdf(path=path, format="A4", print_background=True, margin={"top":"18mm","right":"18mm","bottom":"18mm","left":"18mm"})
            browser.close()
        os.unlink(tmp_path)
    except Exception as e_pw:
        raise RuntimeError(
            "PDF export fallito. WeasyPrint non disponibile e Playwright non funzionante.\n"
            f"WeasyPrint error: {e_weasy}\nPlaywright error: {e_pw}"
        )
