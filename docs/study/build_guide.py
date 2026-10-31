"""Embed figures and screenshots into the study guide as data URIs (single self-contained HTML file).

Usage:
    python docs/study/build_guide.py <output.html>
Images: docs/figures/*.png (kept as PNG) and docs/figures/screens/*.png (converted to JPEG to keep the page small).
"""

import base64
import io
import re
import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
FIG = HERE.parent / "figures"


def data_uri(rel: str) -> str:
    path = FIG / rel
    img = Image.open(path)
    buf = io.BytesIO()
    if rel.startswith("screens/"):
        img = img.convert("RGB")
        if img.width > 1200:
            img = img.resize((1200, round(img.height * 1200 / img.width)))
        img.save(buf, "JPEG", quality=78, optimize=True)
        mime = "image/jpeg"
    else:
        img.save(buf, "PNG", optimize=True)
        mime = "image/png"
    return f"data:{mime};base64," + base64.b64encode(buf.getvalue()).decode()


def main() -> None:
    out = Path(sys.argv[1])
    html = (HERE / "guide.html").read_text(encoding="utf-8")
    html = re.sub(r"\{\{IMG:([^}]+)\}\}", lambda m: data_uri(m.group(1)), html)
    out.write_text(html, encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
