from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.config.settings import get_settings
from app.tools.azure_search import build_filter, run_search
from app.tools.errors import SourceUnavailable


def test_build_filter_none():
    s = get_settings()
    assert build_filter(s, None, None) is None


def test_build_filter_source_only():
    s = get_settings()
    assert build_filter(s, "confluence", None) == "source_type eq 'confluence'"


def test_build_filter_incident_only():
    s = get_settings()
    assert build_filter(s, None, "INC0012345") == "incident_number eq 'INC0012345'"


def test_build_filter_combined():
    s = get_settings()
    got = build_filter(s, "servicenow", "INC0012345")
    assert got == "source_type eq 'servicenow' and incident_number eq 'INC0012345'"


def test_build_filter_escapes_single_quote():
    s = get_settings()
    # A malicious incident number attempting OData injection is escaped
    got = build_filter(s, None, "IN'C")
    assert got == "incident_number eq 'IN''C'"


@patch("app.tools.azure_search._make_client")
def test_run_search_maps_hits(mock_make, fake_search_hits):
    mock_client = MagicMock()
    mock_client.search.return_value = [
        {**h, "@search.score": h["score"]} for h in fake_search_hits
    ]
    mock_make.return_value = mock_client

    hits = run_search(query="vpn broken")
    assert len(hits) == 2
    assert hits[0].title == "Reset your VPN password"
    assert hits[0].source_type == "confluence"
    assert hits[1].incident_number == "INC0012345"


@patch("app.tools.azure_search._make_client")
def test_run_search_raises_source_unavailable_on_error(mock_make):
    mock_client = MagicMock()
    mock_client.search.side_effect = OSError("network dead")
    mock_make.return_value = mock_client

    with pytest.raises(SourceUnavailable) as excinfo:
        run_search(query="anything")
    assert excinfo.value.source == "azure_search"
