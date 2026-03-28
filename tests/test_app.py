import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ui.app import app

app.config["TESTING"] = True
app.config["SECRET_KEY"] = "test-secret"

client = app.test_client()

FOUND_FORM = dict(
    soil_name="Medium Sand",
    gamma="18.0",
    phi_k="30.0",
    c_k="0",
    B="2.0",
    Df="1.0",
    Gk="200",
    Qk="80",
    Es_kpa="10000",
    nu="0.3",
    s_lim="0.025",
    project="TestProject",
    job_ref="TP-001",
    calc_by="Test",
    checked_by="QA",
)

WALL_FORM = dict(
    soil_name="Granular Fill",
    gamma="18.0",
    phi_k="30.0",
    c_k="0",
    H_wall="4.0",
    B_base="3.0",
    B_toe="0.8",
    t_stem_base="0.4",
    t_stem_top="0.3",
    t_base="0.5",
    surcharge_kpa="0",
    project="TestProject",
    job_ref="TP-001",
    calc_by="Test",
    checked_by="QA",
)

SHEET_PILE_FORM = dict(
    phi_k="38.0",
    c_k="0",
    gamma="20.0",
    h_retain="6.0",
    prop_type="propped_top",
    delta_deg="0",
    surcharge_kpa="10.0",
    project="TestProject",
    job_ref="TP-001",
    calc_by="Test",
    checked_by="QA",
)


def _ok(resp, label):
    assert resp.status_code == 200, f"FAIL {label}: HTTP {resp.status_code}\n{resp.data[:400].decode('utf-8', 'replace')}"


def test_home_page():
    r = client.get("/")
    _ok(r, "GET /")
    assert b"DesignApp" in r.data


def test_foundation_form():
    r = client.get("/foundation")
    _ok(r, "GET /foundation")
    assert b"Foundation" in r.data


def test_foundation_analyse_valid():
    r = client.post("/foundation/analyse", data=FOUND_FORM)
    _ok(r, "POST /foundation/analyse")
    html = r.data.decode("utf-8", errors="replace")
    assert any(k in html for k in ("Rd", "kN", "Utilisation", "PASS", "FAIL", "bearing", "Bearing"))


def test_wall_form():
    r = client.get("/wall")
    _ok(r, "GET /wall")
    assert b"Wall" in r.data or b"wall" in r.data


def test_wall_analyse_valid():
    r = client.post("/wall/analyse", data=WALL_FORM)
    _ok(r, "POST /wall/analyse")
    html = r.data.decode("utf-8", errors="replace")
    assert any(k in html for k in ("Ka", "Kp", "Sliding", "PASS", "FAIL"))


def test_sheet_pile_form():
    r = client.get("/sheet-pile")
    _ok(r, "GET /sheet-pile")
    assert b"Sheet" in r.data or b"sheet" in r.data


def test_sheet_pile_analyse_valid():
    r = client.post("/sheet-pile/analyse", data=SHEET_PILE_FORM)
    _ok(r, "POST /sheet-pile/analyse")
    html = r.data.decode("utf-8", errors="replace")
    assert any(k in html for k in ("Sheet", "Pile", "PASS", "FAIL", "embedment"))


def test_api_health_excludes_slope_session_key():
    r = client.get("/api/health")
    _ok(r, "GET /api/health")
    data = json.loads(r.data)
    assert data["status"] == "ok"
    assert data["app"] == "DesignApp"
    assert data["version"] == "2.0"
    assert "slope" not in data["session"]
    assert set(data["session"].keys()) == {"foundation", "wall", "sheet_pile"}


def test_api_soils():
    r = client.get("/api/soils")
    _ok(r, "GET /api/soils")
    data = json.loads(r.data)
    assert isinstance(data, list)
    assert len(data) >= 5
    assert "name" in data[0]


def test_project_export_pdf_without_slope():
    with app.test_client() as c:
        _ok(c.post("/foundation/analyse", data=FOUND_FORM), "foundation for project PDF")
        _ok(c.post("/wall/analyse", data=WALL_FORM), "wall for project PDF")
        r = c.get("/project/export/pdf")
        assert r.status_code == 200
        assert r.data[:4] == b"%PDF"
