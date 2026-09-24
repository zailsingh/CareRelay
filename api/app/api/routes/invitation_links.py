from html import escape
from urllib.parse import quote

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/invite/{token}", include_in_schema=False, response_class=HTMLResponse)
def open_invitation(token: str) -> HTMLResponse:
    """Hand an email-safe HTTP(S) invitation link to the installed app."""
    app_url = f"carerelay://invite/{quote(token, safe='')}"
    safe_app_url = escape(app_url, quote=True)
    html = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="robots" content="noindex,nofollow">
    <meta http-equiv="refresh" content="0;url={safe_app_url}">
    <title>Open CareRelay</title>
  </head>
  <body>
    <main>
      <h1>Open CareRelay</h1>
      <p>This invitation opens securely in the CareRelay app.</p>
      <p><a href="{safe_app_url}">Open CareRelay</a></p>
    </main>
  </body>
</html>"""
    return HTMLResponse(
        html,
        headers={
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",
            "X-Robots-Tag": "noindex, nofollow",
        },
    )
