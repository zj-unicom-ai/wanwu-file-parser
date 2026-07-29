"""Model strategy tests: lazy paddleocrvl import + per-model endpoint wiring."""
from __future__ import annotations

import sys

from app.models import strategy


class TestStrategy:
    def test_mineru_client_uses_resolved_endpoint(self, monkeypatch):
        captured = {}

        class FakeMineruClient:
            def __init__(self, endpoint):
                captured["endpoint"] = endpoint

        monkeypatch.setattr(strategy, "MineruClient", FakeMineruClient)
        strategy.init_mineru_client()
        # Endpoint must include /file_parse (client does not append it).
        assert captured["endpoint"].endswith("/file_parse")

    def test_paddleocrvl_client_is_lazy_and_uses_host_base(self, monkeypatch):
        # PaddleOCRVLClient must not be imported until init_paddleocrvl_client runs.
        sys.modules.pop("app.models.paddleocrvl.client", None)
        captured = {}

        class FakePaddleClient:
            def __init__(self, base):
                captured["base"] = base

        # Inject a fake module so the lazy import inside the initializer finds it.
        import types

        fake_mod = types.ModuleType("app.models.paddleocrvl.client")
        fake_mod.PaddleOCRVLClient = FakePaddleClient
        monkeypatch.setitem(sys.modules, "app.models.paddleocrvl.client", fake_mod)

        strategy.init_paddleocrvl_client()
        assert "/layout-parsing" not in captured["base"]
        assert "/restructure-pages" not in captured["base"]

    def test_strategies_dict_has_both(self):
        assert set(strategy.CLIENT_STRATEGIES.keys()) == {"mineru", "paddleocrvl"}
