"""Unit tests for LinkedIn image generation and the takeaway sentence."""

import struct
from pathlib import Path
from typing import Any

import pytest

from mcp_vs_code_mode.bench.analysis import Summary, summarise
from mcp_vs_code_mode.bench.linkedin import render_linkedin, takeaway

pytestmark = pytest.mark.unit


def _png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    assert data[12:16] == b"IHDR"
    width, height = struct.unpack(">II", data[16:24])
    return int(width), int(height)


def _summary(synthetic: Any, code_tokens: int, mcp_tokens: int = 1000) -> tuple[Summary, Any]:
    tokens: dict[str, list[int]] = {}
    latency: dict[str, list[float]] = {}
    for key in ("A", "B10", "B50", "B200"):
        tokens[f"{key}:mcp"], tokens[f"{key}:code"] = [mcp_tokens], [code_tokens]
        latency[f"{key}:mcp"], latency[f"{key}:code"] = [1000.0], [900.0]
    paths = synthetic.build(synthetic.uniform(15, tokens, latency))
    return summarise(paths), paths


def test_image_dimensions_are_exact(synthetic: Any, tmp_path: Path) -> None:
    summary, _ = _summary(synthetic, 300)
    landscape, portrait = render_linkedin(summary, tmp_path / "li")
    assert landscape.name == "linkedin-landscape.png"
    assert portrait.name == "linkedin-portrait.png"
    assert _png_size(landscape) == (1200, 627)
    assert _png_size(portrait) == (1080, 1350)


def test_takeaway_fewer(synthetic: Any) -> None:
    summary, _ = _summary(synthetic, 290)
    assert takeaway(summary) == (
        "At 200 transactions per account, Code Mode used 71% fewer tokens per task "
        "than MCP tool calling (mean of 15 runs)."
    )


def test_takeaway_more(synthetic: Any) -> None:
    summary, _ = _summary(synthetic, 1120)
    assert takeaway(summary) == (
        "At 200 transactions per account, Code Mode used 12% more tokens per task "
        "than MCP tool calling (mean of 15 runs)."
    )


def test_takeaway_equal(synthetic: Any) -> None:
    summary, _ = _summary(synthetic, 1000)
    text = takeaway(summary)
    assert "about the same number of tokens per task as MCP tool calling" in text
    assert "fewer" not in text
    assert "more" not in text


def test_takeaway_without_data(synthetic: Any) -> None:
    summary = summarise(synthetic.build([]))
    assert takeaway(summary) == "No measured token comparison is available for this run."


def test_images_render_without_data(synthetic: Any, tmp_path: Path) -> None:
    summary = summarise(synthetic.build([]))
    landscape, portrait = render_linkedin(summary, tmp_path / "li")
    assert _png_size(landscape) == (1200, 627)
    assert _png_size(portrait) == (1080, 1350)
