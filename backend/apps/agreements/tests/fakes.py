"""Test-only stand-in for the PDF renderer: deterministic bytes, no WeasyPrint."""

import hashlib


class FakeRenderer:
    def __init__(self) -> None:
        self.rendered: list[str] = []
        self.fail = False

    def render(self, html: str) -> bytes:
        if self.fail:
            raise RuntimeError("renderer down")
        self.rendered.append(html)
        return b"%PDF-1.7 fake\n" + hashlib.sha256(html.encode()).hexdigest().encode()
