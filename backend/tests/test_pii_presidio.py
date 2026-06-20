"""Presidio PII detector resilience tests.

Reproduces the production crash where Presidio attempted a runtime spaCy model
download (`spacy.cli.download` -> `sys.exit(1)` -> SystemExit) and tore down the
upload worker. The detector must instead degrade to the regex backend so uploads
keep working, and must not re-attempt a failed engine on every page.
"""

from __future__ import annotations

import pytest

from app.safety.pii import PresidioPIIDetector, RegexPIIDetector, mask_text

_SAMPLE = "Email a@b.com and PAN ABCDE1234F."


def test_falls_back_to_regex_on_systemexit(monkeypatch):
    # SystemExit is exactly what spacy.cli.download() raises on a failed download
    # (it is a BaseException, NOT an Exception — a bare `except Exception` misses it).
    det = PresidioPIIDetector()

    def _boom():
        raise SystemExit(1)

    monkeypatch.setattr(det, "_ensure_analyzer", _boom)

    # Must not raise; must still detect via the regex fallback.
    result = mask_text(_SAMPLE, det)
    types = {e.entity_type for e in result.entities}
    assert "EMAIL_ADDRESS" in types
    assert "IN_PAN" in types
    assert "<EMAIL_ADDRESS>" in result.masked_text


def test_falls_back_to_regex_on_generic_exception(monkeypatch):
    det = PresidioPIIDetector()
    monkeypatch.setattr(
        det, "_ensure_analyzer", lambda: (_ for _ in ()).throw(RuntimeError("no model"))
    )
    result = det.analyze(_SAMPLE)
    assert any(e.entity_type == "EMAIL_ADDRESS" for e in result)


def test_fallback_is_cached_not_retried(monkeypatch):
    det = PresidioPIIDetector()
    calls = {"n": 0}

    def _boom():
        calls["n"] += 1
        raise SystemExit(1)

    monkeypatch.setattr(det, "_ensure_analyzer", _boom)

    det.analyze(_SAMPLE)
    det.analyze(_SAMPLE)
    det.analyze(_SAMPLE)
    # Engine build attempted once; subsequent calls use the cached regex fallback.
    assert calls["n"] == 1
    assert isinstance(det._fallback, RegexPIIDetector)
