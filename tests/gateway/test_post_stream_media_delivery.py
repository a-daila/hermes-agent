"""Regression tests for _deliver_media_from_response post-stream delivery.

Fixes #20834: bare local filesystem paths that appeared in tool output or
inspected content must NOT be promoted to attachments after streaming.
Only explicit MEDIA: directives should trigger post-stream uploads.
"""
from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_runner():
    """Build a minimal GatewayRunner-like object with just the method under test."""
    from gateway.run import GatewayRunner  # noqa: PLC0415

    runner = object.__new__(GatewayRunner)
    return runner


def _make_event(chat_id: str = "C123", thread_id: str | None = None):
    event = MagicMock()
    event.source.chat_id = chat_id
    event.source.thread_id = thread_id
    return event


def _make_adapter(*, extract_media_return=None, extract_images_return=None, extract_local_files_return=None):
    adapter = MagicMock()
    adapter.name = "test-adapter"
    adapter.extract_media.return_value = (extract_media_return or [], "")
    adapter.extract_images.return_value = ([], "cleaned-text")
    adapter.extract_local_files.return_value = (extract_local_files_return or [], "")
    adapter.send_multiple_images = AsyncMock()
    adapter.send_voice = AsyncMock()
    adapter.send_video = AsyncMock()
    adapter.send_document = AsyncMock()
    return adapter


class TestPostStreamBarePathIgnored:
    """Bare local paths in response text must NOT trigger post-stream uploads."""

    def test_bare_local_path_in_response_does_not_trigger_upload(self, tmp_path):
        """A response that contains /path/to/image.png but no MEDIA: directive
        must not upload anything after the text is already sent (fixes #20834)."""
        img = tmp_path / "internal_reference.png"
        img.write_bytes(b"PNG")

        response = f"I analysed the file at {img}. No attachment intended."
        adapter = _make_adapter(
            extract_media_return=[],
            extract_local_files_return=[str(img)],  # simulates old behavior
        )
        event = _make_event()
        runner = _make_runner()

        asyncio.run(runner._deliver_media_from_response(response, event, adapter))

        adapter.send_multiple_images.assert_not_called()
        adapter.send_document.assert_not_called()
        adapter.send_video.assert_not_called()
        adapter.send_voice.assert_not_called()

    def test_bare_local_video_path_in_response_does_not_trigger_upload(self, tmp_path):
        """A response containing a local video path but no MEDIA: directive must
        not upload anything."""
        vid = tmp_path / "captured_output.mp4"
        vid.write_bytes(b"MP4")

        response = f"Processing finished; intermediate output at {vid}."
        adapter = _make_adapter(
            extract_media_return=[],
            extract_local_files_return=[str(vid)],
        )
        event = _make_event()
        runner = _make_runner()

        asyncio.run(runner._deliver_media_from_response(response, event, adapter))

        adapter.send_video.assert_not_called()
        adapter.send_document.assert_not_called()


class TestPostStreamExplicitMediaDirectiveStillWorks:
    """Explicit MEDIA: directives must continue to be delivered post-stream."""

    def test_explicit_media_image_is_delivered(self, tmp_path):
        """An explicit MEDIA: tag must still result in an image upload."""
        img = tmp_path / "chart.png"
        img.write_bytes(b"PNG")

        response = f"Here is the chart. MEDIA:{img}"
        adapter = _make_adapter(
            extract_media_return=[(str(img), False)],
        )
        event = _make_event()
        runner = _make_runner()

        asyncio.run(runner._deliver_media_from_response(response, event, adapter))

        adapter.send_multiple_images.assert_called_once()

    def test_explicit_media_document_is_delivered(self, tmp_path):
        """A non-image explicit MEDIA: file must be sent as a document."""
        doc = tmp_path / "report.pdf"
        doc.write_bytes(b"PDF")

        response = f"Report generated. MEDIA:{doc}"
        adapter = _make_adapter(
            extract_media_return=[(str(doc), False)],
        )
        event = _make_event()
        runner = _make_runner()

        asyncio.run(runner._deliver_media_from_response(response, event, adapter))

        adapter.send_document.assert_called_once()
