from pathlib import Path

import markdown

from app.repositories.home.models.home_model import HomePage

README_PATH = Path(__file__).resolve().parents[4] / "README.md"

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>{title}</title>
    <style>
      body {{
        font-family: ui-sans-serif, system-ui, sans-serif;
        max-width: 48rem;
        margin: 2rem auto;
        padding: 0 1rem;
        line-height: 1.5;
      }}
      pre, code {{
        background: #f4f4f5;
      }}
      pre {{
        padding: 0.75rem 1rem;
        overflow: auto;
      }}
      table {{
        border-collapse: collapse;
        width: 100%;
      }}
      th, td {{
        border: 1px solid #d4d4d8;
        padding: 0.4rem 0.6rem;
        text-align: left;
      }}
    </style>
  </head>
  <body>
    {body}
  </body>
</html>
"""


def render() -> HomePage:
    title = "verifik-smartcheck"
    raw = README_PATH.read_text(encoding="utf-8")
    body = markdown.markdown(raw, extensions=["tables", "fenced_code"])

    return HomePage(title=title, html=HTML_PAGE.format(title=title, body=body))
