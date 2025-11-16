import json
import os
import sys
import tempfile

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from cli import dashboard_state, ingest_events_from_file


def test_ingest_json_array(tmp_path):
    dashboard_state.clear()
    events = [
        {"timestamp": "2025-01-01T00:00:00Z", "event_type": "alert", "src_ip": "10.0.0.1"},
        {"timestamp": "2025-01-01T00:00:01Z", "event_type": "flow", "src_ip": "10.0.0.2"},
    ]
    p = tmp_path / "eve.json"
    p.write_text(json.dumps(events))
    ingested = ingest_events_from_file(str(p))
    assert ingested == 2
    assert dashboard_state.total_received >= 2


def test_ingest_jsonlines(tmp_path):
    dashboard_state.clear()
    lines = [
        json.dumps({"timestamp": "2025-01-01T00:00:00Z", "event_type": "alert", "src_ip": "10.0.0.1"}),
        json.dumps({"timestamp": "2025-01-01T00:00:00Z", "event_type": "alert", "src_ip": "10.0.0.2"}),
    ]
    p = tmp_path / "eve.json"
    p.write_text("\n".join(lines))
    ingested = ingest_events_from_file(str(p))
    assert ingested == 2
    assert dashboard_state.event_type_counts.get("alert", 0) >= 2
