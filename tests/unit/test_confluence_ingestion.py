from pathlib import Path

from backend.knowledge.loaders import fetch_confluence_page, html_to_text


class FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


def test_html_to_text_strips_confluence_markup() -> None:
    html = '<h1>Overview</h1><p>Use <strong>two approved</strong> checks.</p>'

    body = html_to_text(html)

    assert "Overview" in body
    assert "two approved" in body
    assert "<" not in body


def test_html_to_text_removes_macro_noise_and_preserves_blocks() -> None:
    html = '<h1>Features</h1><ac:structured-macro ac:name="toc"><ac:parameter>default</ac:parameter></ac:structured-macro><p>Access workspace insights.</p><script>tracking()</script>'

    body = html_to_text(html)

    assert body == "Features\nAccess workspace insights."


def test_fetch_confluence_page_reads_page_content(monkeypatch) -> None:
    def fake_get(url: str, **kwargs):
        assert url == "https://hackthoncp.atlassian.net/wiki/rest/api/content/655361"
        assert kwargs["params"] == {"expand": "body.storage,metadata"}
        return FakeResponse({
            "id": "655361",
            "title": "Overview of Machine Learning Models",
            "body": {"storage": {"value": "<p>Employees must complete <strong>two approved identity checks</strong>.</p>"}},
        })

    monkeypatch.setattr("backend.knowledge.loaders.httpx.get", fake_get)

    result = fetch_confluence_page(
        "https://hackthoncp.atlassian.net/wiki/spaces/~7120202886c6cb70d148adb432c610e7204d62/pages/655361/Overview+of+Machine+Learning+Models+and+Their+Applications+in+Various+Industries",
        base_url="https://hackthoncp.atlassian.net",
        email="user@example.com",
        api_token="token",
    )

    assert "Overview of Machine Learning Models" in result
    assert "two approved identity checks" in result


def test_fetch_confluence_page_uses_langchain_loader_when_available(monkeypatch) -> None:
    class FakeDocument:
        page_content = "This page was loaded through LangChain."

    class FakeLoader:
        def __init__(self, url: str, username: str, api_key: str):
            assert url == "https://hackthoncp.atlassian.net"
            assert username == "user@example.com"
            assert api_key == "token"

        def load(self, page_ids: list[str]):
            assert page_ids == ["655361"]
            return [FakeDocument()]

    monkeypatch.setattr("backend.knowledge.loaders.ConfluenceLoader", FakeLoader)

    result = fetch_confluence_page(
        "https://hackthoncp.atlassian.net/wiki/spaces/TEAM/pages/655361/Overview",
        base_url="https://hackthoncp.atlassian.net",
        email="user@example.com",
        api_token="token",
    )

    assert "This page was loaded through LangChain." in result
