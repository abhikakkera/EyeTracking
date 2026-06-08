"""
Unit tests for data schema, CSV/JSON export, and session recording.
"""
from __future__ import annotations

import csv
import json
import tempfile
from pathlib import Path

import pytest

from src.data.schema import (
    BlinkEvent, DetectionMethod, FixationEvent, FrameQuality,
    FrameRecord, SaccadeEvent, SessionMetadata, TestType,
)
from src.data.session_recorder import SessionData, SessionRecorder
from src.data.export_csv import export_session as csv_export
from src.data.export_json import export_session as json_export


# ---------------------------------------------------------------------------
# Schema / dataclass tests
# ---------------------------------------------------------------------------

class TestFrameRecord:
    def test_defaults(self):
        r = FrameRecord(session_id="s", frame_number=0, timestamp_sec=0.0)
        assert not r.face_detected
        assert not r.blink_detected
        assert r.frame_quality == FrameQuality.GOOD
        assert r.confidence_score == 0.0

    def test_quality_enum_values(self):
        values = {q.value for q in FrameQuality}
        assert "good" in values
        assert "questionable" in values
        assert "bad" in values

    def test_detection_method_enum(self):
        assert DetectionMethod.CONTOUR_ELLIPSE.value == "contour_ellipse"
        assert DetectionMethod.NONE.value == "none"


class TestSessionMetadata:
    def test_session_id_auto_generated(self):
        m1 = SessionMetadata()
        m2 = SessionMetadata()
        assert m1.session_id != m2.session_id

    def test_test_type_enum(self):
        assert TestType.FREE_VIEWING.value == "free_viewing"
        assert TestType.SMOOTH_PURSUIT.value == "smooth_pursuit"


# ---------------------------------------------------------------------------
# Session recorder tests
# ---------------------------------------------------------------------------

def _make_frame_record(n: int, ts: float, session_id: str = "test") -> FrameRecord:
    return FrameRecord(
        session_id=session_id,
        frame_number=n,
        timestamp_sec=ts,
        face_detected=True,
        left_pupil_detected=True,
        right_pupil_detected=True,
        gaze_x=0.5,
        gaze_y=0.5,
        confidence_score=0.85,
        frame_quality=FrameQuality.GOOD,
    )


class TestSessionRecorder:
    def test_start_and_add_frames(self):
        rec = SessionRecorder()
        meta = SessionMetadata(session_id="sess-001")
        rec.start(meta)
        for i in range(10):
            rec.add_frame(_make_frame_record(i, float(i) / 30.0))
        assert rec.frame_count == 10

    def test_finish_fills_totals(self):
        rec = SessionRecorder()
        meta = SessionMetadata(session_id="sess-002")
        rec.start(meta)
        for i in range(5):
            rec.add_frame(_make_frame_record(i, float(i) / 30.0))
        finished_meta = rec.finish()
        assert finished_meta.total_frames == 5
        assert finished_meta.good_frames == 5  # all frames are GOOD

    def test_add_frame_before_start_does_not_raise(self):
        rec = SessionRecorder()
        rec.add_frame(_make_frame_record(0, 0.0))  # should log warning but not crash

    def test_finish_without_start_raises(self):
        rec = SessionRecorder()
        with pytest.raises(RuntimeError):
            rec.finish()

    def test_blink_event_recorded(self):
        rec = SessionRecorder()
        rec.start(SessionMetadata(session_id="blink-test"))
        blink = BlinkEvent(
            session_id="blink-test",
            start_timestamp_sec=0.1,
            end_timestamp_sec=0.25,
            duration_ms=150.0,
            affected_eye="left",
        )
        rec.add_blink(blink)
        meta = rec.finish()
        assert meta.blink_count == 1


# ---------------------------------------------------------------------------
# CSV export tests
# ---------------------------------------------------------------------------

class TestCSVExport:
    def _make_session(self, n_frames: int = 5) -> SessionData:
        meta = SessionMetadata(session_id="csv-test-session")
        session = SessionData(meta)
        for i in range(n_frames):
            session.frames.append(_make_frame_record(i, float(i) / 30.0, "csv-test-session"))
        session.blinks.append(BlinkEvent(
            session_id="csv-test-session",
            start_timestamp_sec=0.1, end_timestamp_sec=0.25,
            duration_ms=150.0, affected_eye="both",
        ))
        session.saccades.append(SaccadeEvent(
            session_id="csv-test-session",
            start_timestamp_sec=0.5, end_timestamp_sec=0.53,
            duration_ms=30.0, start_x=0.3, start_y=0.5,
            end_x=0.7, end_y=0.5, amplitude_px=40.0,
            peak_velocity_px_per_sec=1333.0, direction_deg=0.0,
        ))
        session.fixations.append(FixationEvent(
            session_id="csv-test-session",
            start_timestamp_sec=0.6, end_timestamp_sec=0.9,
            duration_ms=300.0, center_x=0.5, center_y=0.5,
            dispersion_px=8.0,
        ))
        return session

    def test_writes_four_files(self):
        session = self._make_session()
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = csv_export(session, tmpdir)
            assert len(paths) == 4
            for p in paths:
                assert Path(p).exists()

    def test_frame_csv_has_correct_row_count(self):
        n = 7
        session = self._make_session(n_frames=n)
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = csv_export(session, tmpdir)
            frames_csv = [p for p in paths if "frames" in str(p)][0]
            with open(frames_csv) as fh:
                rows = list(csv.DictReader(fh))
            assert len(rows) == n

    def test_frame_csv_has_expected_columns(self):
        session = self._make_session()
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = csv_export(session, tmpdir)
            frames_csv = [p for p in paths if "frames" in str(p)][0]
            with open(frames_csv) as fh:
                reader = csv.DictReader(fh)
                cols = reader.fieldnames
            assert "session_id" in cols
            assert "gaze_x" in cols
            assert "blink_detected" in cols
            assert "confidence_score" in cols

    def test_saccade_csv_content(self):
        session = self._make_session()
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = csv_export(session, tmpdir)
            sac_csv = [p for p in paths if "saccades" in str(p)][0]
            with open(sac_csv) as fh:
                rows = list(csv.DictReader(fh))
            assert len(rows) == 1
            assert float(rows[0]["amplitude_px"]) == pytest.approx(40.0)


# ---------------------------------------------------------------------------
# JSON export tests
# ---------------------------------------------------------------------------

class TestJSONExport:
    def _make_session(self) -> SessionData:
        meta = SessionMetadata(session_id="json-test-session")
        meta.timestamp_start = 1000.0
        meta.timestamp_end = 1060.0
        session = SessionData(meta)
        for i in range(3):
            session.frames.append(_make_frame_record(i, float(i) / 30.0, "json-test-session"))
        return session

    def test_writes_two_files(self):
        session = self._make_session()
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = json_export(session, tmpdir)
            assert len(paths) == 2
            for p in paths:
                assert Path(p).exists()

    def test_metadata_json_has_disclaimer(self):
        session = self._make_session()
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = json_export(session, tmpdir)
            meta_json = [p for p in paths if "metadata" in str(p)][0]
            with open(meta_json) as fh:
                doc = json.load(fh)
            assert "disclaimer" in doc
            assert "Parkinson" in doc["disclaimer"]

    def test_metadata_json_has_summary(self):
        session = self._make_session()
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = json_export(session, tmpdir)
            meta_json = [p for p in paths if "metadata" in str(p)][0]
            with open(meta_json) as fh:
                doc = json.load(fh)
            assert "summary" in doc
            assert "total_frames" in doc["summary"]

    def test_events_json_structure(self):
        session = self._make_session()
        session.blinks.append(BlinkEvent(
            session_id="json-test-session",
            start_timestamp_sec=0.1, end_timestamp_sec=0.2,
            duration_ms=100.0, affected_eye="left",
        ))
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = json_export(session, tmpdir)
            events_json = [p for p in paths if "events" in str(p)][0]
            with open(events_json) as fh:
                doc = json.load(fh)
            assert "blinks" in doc
            assert "saccades" in doc
            assert "fixations" in doc
            assert len(doc["blinks"]) == 1
