"""
ui/api.py  — Adapter layer between UI and math engine.
See DesignApp_Roadmap_v2_0.docx §5 for full API reference.

ARCHITECTURE RULE:
    This is the ONLY module that UI code (Flask routes, CLI) may import from
    the math side.  Nothing else in ui/ may import from core/ or models/.

Data flow:
    raw dicts → [api.py] → model objects → core engines → result dicts

All public functions:
  • Accept only Python primitives / dicts / lists
  • Return only Python primitives / dicts / lists
  • Never raise — errors returned as {'ok': False, 'error': str}
  • Are independently testable without a running web server

Schema (Sprint 2 standardisation):
    Every run_*() return dict includes:
        ok            : bool
        version       : str   — e.g. "1.1"
        analysis_type : str   — "slope" | "foundation" | "wall"
        warnings      : list[str]
        errors        : list[str]   — empty on success

References: EC7 EN 1997-1:2004, Bishop 1955, Craig 2004 Ch.9
"""

from __future__ import annotations
import io, json, math, pathlib, traceback

from models.soil          import Soil
from models.geometry      import SlopeGeometry, SlipCircle
from models.foundation    import Foundation
from models.wall_geometry import RetainingWall
from models.surcharge     import UniformSurcharge

from core.search            import grid_search, SearchResult, _auto_bounds as _search_auto_bounds
from core.factors_of_safety import verify_slope_da1
from core.slicer            import create_slices
from core.limit_equilibrium import bishop_simplified
from core.settlement        import (
    immediate_settlement,
    consolidation_settlement,
    time_to_consolidation,
)
from core.foundation_check  import check_foundation_da1
from core.rankine_coulomb   import ka_rankine, kp_rankine
from core.wall_analysis     import analyse_wall_da1
from models.pile             import Pile, PileSoilLayer
from core.pile_capacity      import verify_pile_da1
from models.sheet_pile       import SheetPile
from core.sheet_pile_analysis import analyse_sheet_pile_da1

# B-02 FIX: resolve data files relative to this file, not the CWD.
# Both json files live in the same directory as api.py (project root).
_HERE             = pathlib.Path(__file__).parent
SOIL_LIBRARY_PATH = _HERE / "data" / "soil_library.json"
EC7_PATH          = _HERE / "data" / "ec7.json"

_VERSION = "1.1"


# ── helpers ──────────────────────────────────────────────────────────────────

def _safe(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc()}


def _auto_bounds(slope: SlopeGeometry) -> dict:
    """Auto-derive grid-search bounds from the core search heuristic."""
    cx_range, cy_range, r_range = _search_auto_bounds(slope)
    return dict(
        cx_range=cx_range,
        cy_range=cy_range,
        r_range=r_range,
        search_zone=dict(
            xc_min=cx_range[0],
            xc_max=cx_range[1],
            yc_min=cy_range[0],
            yc_max=cy_range[1],
            r_min=r_range[0],
            r_max=r_range[1],
        ),
    )


def _search_zone_from_params(params: dict, slope: SlopeGeometry) -> dict:
    """Build the explicit search-zone payload accepted by core/search.py."""
    auto = _auto_bounds(slope)["search_zone"]
    zone = dict(auto)

    alias_pairs = (
        ("xc_min", "cx_min"),
        ("xc_max", "cx_max"),
        ("yc_min", "cy_min"),
        ("yc_max", "cy_max"),
        ("r_min", "r_min"),
        ("r_max", "r_max"),
    )
    for canonical, legacy in alias_pairs:
        value = params.get(canonical)
        if value in (None, ""):
            value = params.get(legacy)
        if value not in (None, ""):
            zone[canonical] = float(value)

    zone["n_cx"] = int(params.get("n_cx", 12))
    zone["n_cy"] = int(params.get("n_cy", 12))
    zone["n_r"] = int(params.get("n_r", 8))
    return zone


def _search_zone_from_analysis(analysis: dict) -> dict | None:
    zone = analysis.get("search_zone")
    if zone:
        return dict(zone)

    cache = analysis.get("search_cache", {})
    if not cache:
        return None

    return {
        "xc_min": cache["cx_range"][0],
        "xc_max": cache["cx_range"][1],
        "yc_min": cache["cy_range"][0],
        "yc_max": cache["cy_range"][1],
        "r_min": cache["r_range"][0],
        "r_max": cache["r_range"][1],
        "n_cx": len(cache.get("cx_values", [])) or 1,
        "n_cy": len(cache.get("cy_values", [])) or 1,
        "n_r": len(cache.get("r_values", [])) or 1,
    }


def _rebuild_search_result(analysis: dict, slope: SlopeGeometry, soil: Soil) -> SearchResult:
    """
    B-08 FIX: Reconstruct a SearchResult from the cached analysis dict.

    Instead of re-running the full grid search (O(n_cx * n_cy * n_r) circles),
    this re-runs Bishop Simplified on the single stored critical circle only —
    one calculation, not hundreds.  The critical circle is identical to the one
    found during the original analysis, so all exports stay consistent.

    Cached search-surface metadata is reused when present so plots and exports
    stay aligned with the accepted search result.

    :param analysis: Serialised result dict from run_slope_analysis().
    :param slope:    Reconstructed SlopeGeometry.
    :param soil:     Reconstructed Soil.
    :return:         SearchResult suitable for plot and PDF export.
    """
    cc_d   = analysis["critical_circle"]
    circ   = SlipCircle(cc_d["cx"], cc_d["cy"], cc_d["r"])
    ru     = analysis.get("ru", 0.0)
    cache  = analysis.get("search_cache", {})
    search_zone = _search_zone_from_analysis(analysis) or {}
    search_surface = analysis.get("search_surface", {})

    # Re-run Bishop on the single critical circle (not a grid sweep)
    slices = create_slices(slope, circ, soil, num_slices=20)
    fos_r  = bishop_simplified(slices, ru=ru)

    return SearchResult(
        critical_circle  = circ,
        fos_min          = analysis.get("fos_char", fos_r.fos),
        best_fos_result  = fos_r,
        fos_grid         = search_surface.get("fos_grid", []),
        cx_values        = cache.get("cx_values", [cc_d["cx"]]),
        cy_values        = cache.get("cy_values", [cc_d["cy"]]),
        r_values         = cache.get("r_values", [cc_d["r"]]),
        cx_range         = tuple(cache.get("cx_range", [cc_d["cx"]-1, cc_d["cx"]+1])),
        cy_range         = tuple(cache.get("cy_range", [cc_d["cy"]-1, cc_d["cy"]+1])),
        r_range          = tuple(cache.get("r_range",  [cc_d["r"]*0.8, cc_d["r"]*1.2])),
        n_circles_tested = cache.get("n_circles_tested", 1),
        n_valid          = cache.get("n_valid", 1),
        method           = analysis.get("method", "bishop_simplified"),
        ru               = ru,
        warnings         = list(analysis.get("warnings", [])),
        search_zone      = search_zone,
        search_diagnostics = dict(analysis.get("search_diagnostics", {})),
        boundary_warning = analysis.get("boundary_warning"),
    )


# ── 1. Library helpers ────────────────────────────────────────────────────────

def get_soil_library() -> list:
    with open(SOIL_LIBRARY_PATH) as f:
        return json.load(f).get("soils", [])

def get_ec7_factors() -> dict:
    with open(EC7_PATH) as f:
        return json.load(f)

def get_material_grades() -> dict:
    return {"concrete": ["C20/25","C25/30","C30/37","C35/45","C40/50"],
            "steel":    ["B500A","B500B","B500C"]}


# ── 2. Slope stability ────────────────────────────────────────────────────────

def run_slope_analysis(params: dict) -> dict:
    """
    Full EC7 DA1 slope stability analysis.

    Required: gamma (kN/m³), phi_k (°), slope_points [[x,y],…]
    Optional: soil_name, c_k (kPa), ru (0-1),
              cx_min/max, cy_min/max, r_min/max,
              n_cx, n_cy, n_r, num_slices

    Returns (schema v1.1):
        ok, version, analysis_type, errors,
        soil, slope_points, ru,
        fos_char, fos_d, passes,
        comb1, comb2, critical_circle,
        method, n_circles_tested,
        slices [{x, b, alpha_deg, weight}],
        search_cache {cx_values, cy_values, cx_range, cy_range, r_range,
                      n_circles_tested, n_valid},
        warnings

    B-08: search_cache stores enough data for _rebuild_search_result() to
    reconstruct a valid SearchResult without re-running the grid.
    """
    def _run():
        soil  = Soil(params.get("soil_name","Soil"),
                     float(params["gamma"]), float(params["phi_k"]),
                     float(params.get("c_k", 0.0)))
        pts   = [(float(p[0]), float(p[1])) for p in params["slope_points"]]
        slope = SlopeGeometry(pts)
        ru    = float(params.get("ru", 0.0))
        ns    = int(params.get("num_slices", 20))
        kh    = float(params.get("kh", 0.0))   # S4: horizontal seismic coefficient
        kv    = float(params.get("kv", 0.0))   # S4: vertical   seismic coefficient

        search_zone = _search_zone_from_params(params, slope)
        sr  = grid_search(
            slope,
            soil,
            ru=ru,
            search_zone=search_zone,
            n_cx=search_zone["n_cx"],
            n_cy=search_zone["n_cy"],
            n_r=search_zone["n_r"],
            num_slices=ns,
        )
        ver    = verify_slope_da1(
            slope,
            soil,
            ru=ru,
            search_zone=search_zone,
            n_cx=search_zone["n_cx"],
            n_cy=search_zone["n_cy"],
            n_r=search_zone["n_r"],
            num_slices=ns,
        )
        slices = create_slices(slope, sr.critical_circle, soil, num_slices=ns)
        circ   = sr.critical_circle

        def _c(c):
            return dict(label=c.label, gamma_phi=round(c.gamma_phi,3),
                        phi_d=round(c.phi_d,3), c_d=round(c.c_d,3),
                        fos_d=round(c.fos_d,4), passes=c.passes)

        return dict(
            ok            = True,
            version       = _VERSION,
            analysis_type = "slope",
            errors        = [],
            soil          = dict(name=soil.name, gamma=soil.gamma,
                                 phi_k=soil.phi_k, c_k=soil.c_k),
            slope_points  = [list(p) for p in pts],
            ru            = ru,
            kh            = kh,
            kv            = kv,
            fos_char      = round(sr.fos_min, 4),
            fos_d         = round(ver.fos_d_min, 4),
            passes        = ver.passes,
            comb1         = _c(ver.comb1),
            comb2         = _c(ver.comb2),
            governing_combination = ver.governing.label,
            da2           = dict(
                label    = ver.da2.label,
                gamma_R  = ver.da2.gamma_R,
                fos_char = round(ver.da2.fos_char, 4),
                fos_d    = round(ver.da2.fos_d, 4),
                passes   = ver.da2.passes,
            ) if ver.da2 else None,
            da3           = dict(
                fos_d  = round(ver.da3_fos_d, 4),
                passes = ver.da3_passes,
            ),
            critical_circle = dict(cx=round(circ.cx,3),
                                   cy=round(circ.cy,3),
                                   r=round(circ.r,3)),
            method           = sr.best_fos_result.method,
            n_circles_tested = sr.n_circles_tested,
            boundary_warning = sr.boundary_warning,
            search_zone      = dict(sr.search_zone),
            search_diagnostics = dict(sr.search_diagnostics),
            search_surface   = dict(
                cx_values=sr.cx_values,
                cy_values=sr.cy_values,
                fos_grid=sr.fos_grid,
            ),
            slices = [dict(x=round(s.x,3), b=round(s.b,3),
                           width=round(s.b,3), height=round(s.height,3),
                           alpha_deg=round(math.degrees(s.alpha),2),
                           weight=round(s.weight,3)) for s in slices],
            search_cache = dict(
                cx_values        = sr.cx_values,
                cy_values        = sr.cy_values,
                r_values         = sr.r_values,
                cx_range         = list(sr.cx_range),
                cy_range         = list(sr.cy_range),
                r_range          = list(sr.r_range),
                n_circles_tested = sr.n_circles_tested,
                n_valid          = sr.n_valid,
            ),
            warnings = list(dict.fromkeys(list(ver.warnings) + list(sr.warnings))),
        )

    r = _safe(_run)
    if "error" in r and "ok" not in r:
        r["ok"]            = False
        r["version"]       = _VERSION
        r["analysis_type"] = "slope"
        r["errors"]        = [r.get("error","Unknown error")]
    return r


# ── 3. Export helpers ─────────────────────────────────────────────────────────

def _rebuild(analysis: dict):
    """Reconstruct Soil, SlopeGeometry, SlipCircle from a result dict."""
    s  = analysis["soil"]
    cc = analysis["critical_circle"]
    return (Soil(s["name"], s["gamma"], s["phi_k"], s.get("c_k",0.0)),
            SlopeGeometry([tuple(p) for p in analysis["slope_points"]]),
            SlipCircle(cc["cx"], cc["cy"], cc["r"]))


def export_slope_plot_png(analysis: dict, dpi: int = 120) -> bytes:
    """
    Slope cross-section + critical circle → PNG bytes.

    B-08 FIX: Uses _rebuild_search_result() (one Bishop call) instead of
    re-running the full grid search (1152 circles).  The critical circle is
    identical to the one found during analysis.
    """
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from exporters.plot_slope import plot_slope_stability
    soil, slope, _ = _rebuild(analysis)
    sr  = _rebuild_search_result(analysis, slope, soil)
    fig = plot_slope_stability(slope, sr,
                               title=f"Critical Slip Circle — {soil.name}",
                               ru=analysis.get("ru", 0.0))
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight")
    plt.close(fig); buf.seek(0)
    return buf.read()


def export_heatmap_png(analysis: dict, dpi: int = 120) -> bytes:
    """FoS heatmap over search grid → PNG bytes."""
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from exporters.plot_bishop import plot_fos_heatmap
    soil, slope, _ = _rebuild(analysis)
    sr = _rebuild_search_result(analysis, slope, soil)
    fig = plot_fos_heatmap(slope, sr)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight")
    plt.close(fig); buf.seek(0)
    return buf.read()


def export_pdf(analysis: dict, out_path: str,
               project="DesignApp", job_ref="",
               calc_by="", checked_by="") -> str:
    """
    Generate PDF calculation sheet → out_path.

    B-08 FIX: _rebuild_search_result() avoids a second full grid sweep.
    """
    from exporters.report_pdf import generate_slope_report
    soil, slope, _ = _rebuild(analysis)
    ru     = analysis.get("ru", 0.0)
    sr     = _rebuild_search_result(analysis, slope, soil)
    ver    = verify_slope_da1(slope, soil, ru=ru, search_zone=_search_zone_from_analysis(analysis))
    slices = create_slices(slope, sr.critical_circle, soil, num_slices=20)
    generate_slope_report(out_path, soil, slope, sr, ver, slices,
                          ru=ru, project=project, job_ref=job_ref,
                          calc_by=calc_by, checked_by=checked_by)
    return out_path


def export_docx(analysis: dict, out_path: str,
                project="DesignApp", job_ref="",
                calc_by="", checked_by="") -> str:
    """
    Generate Word calculation sheet → out_path.

    B-08 FIX: _rebuild_search_result() avoids a second full grid sweep.
    """
    from exporters.report_docx import generate_slope_report_docx
    soil, slope, _ = _rebuild(analysis)
    ru     = analysis.get("ru", 0.0)
    sr     = _rebuild_search_result(analysis, slope, soil)
    ver    = verify_slope_da1(slope, soil, ru=ru, search_zone=_search_zone_from_analysis(analysis))
    slices = create_slices(slope, sr.critical_circle, soil, num_slices=20)
    generate_slope_report_docx(out_path, soil, slope, sr, ver, slices,
                               ru=ru, project=project, job_ref=job_ref,
                               calc_by=calc_by, checked_by=checked_by)
    return out_path


# ── 4. Foundation analysis ────────────────────────────────────────────────────

def run_foundation_analysis(params: dict) -> dict:
    """
    EC7 DA1 bearing capacity + immediate settlement + (optional) consolidation.

    Required: gamma, phi_k, B (m), Df (m), Gk (kN or kN/m)
    Optional: soil_name, c_k, L (m), e_B, e_L, Qk, Hk,
              Es_kpa (default 10000), nu (default 0.3), s_lim (m, default 0.025)

              Clay / consolidation inputs (all optional, all required together):
              Cc          — Compression index (NC branch)
              Cs          — Swelling index (OC branch, default 0)
              e0          — Initial void ratio
              sigma_v0    — Initial effective vertical stress at mid-layer (kPa)
              H_layer     — Compressible layer thickness (m)
              sigma_pc    — Preconsolidation pressure (kPa), omit for NC clay
              cv          — Coefficient of consolidation (m²/year), for time-rate
              t_target_U  — Target degree of consolidation (0–1, default 0.95)

    Returns (schema v1.1):
        ok, version, analysis_type, errors,
        foundation, soil, comb1, comb2, uls_passes,
        s_immediate_mm, s_consolidation_mm, s_total_mm,
        s_lim_mm, sls_passes, t_95_years, passes, warnings

    References:
        EC7 §6.6.1 (SLS: characteristic loads govern settlement).
        Das §11.7 (Terzaghi consolidation). Craig §7.4.
    """
    def _run():
        soil = Soil(params.get("soil_name", "Soil"),
                    float(params["gamma"]),
                    float(params["phi_k"]),
                    float(params.get("c_k", 0.0)))
        fdn  = Foundation(
            B   = float(params["B"]),
            Df  = float(params["Df"]),
            L   = float(params["L"]) if params.get("L") else None,
            e_B = float(params.get("e_B", 0.0)),
            e_L = float(params.get("e_L", 0.0)),
        )
        Gk    = float(params["Gk"])
        Qk    = float(params.get("Qk", 0.0))
        Hk    = float(params.get("Hk", 0.0))
        Es    = float(params.get("Es_kpa", 10_000.0))
        nu    = float(params.get("nu", 0.3))
        s_lim = float(params.get("s_lim", 0.025))

        # B-03 FIX: SLS stress uses characteristic (unfactored) loads per EC7 §6.6.1.
        # q_net includes Qk — previously only Gk was used, under-predicting settlement.
        A_ref     = fdn.A_eff if fdn.A_eff else fdn.B
        q_net_sls = (Gk + Qk) / A_ref
        imm = immediate_settlement(q_net=q_net_sls, B=fdn.B, E_s=Es, nu=nu)

        # ── Settlement path selection ──────────────────────────────────────
        # Path A (Sprint 5): multi-layer clay_layers list
        # Path B (Sprint 1): single-layer legacy keys (Cc, e0, sigma_v0, H_layer)
        # Path C: immediate only
        consol      = None
        t_95        = None
        clay_layers = None

        _layer_list = params.get("clay_layers")   # list of dicts
        _clay_keys  = {"Cc", "e0", "sigma_v0", "H_layer"}

        if _layer_list:
            # Path A — multi-layer Boussinesq consolidation (Sprint 5)
            from core.foundation_check import ClayLayer
            clay_layers = []
            for i, ld in enumerate(_layer_list):
                clay_layers.append(ClayLayer(
                    H         = float(ld["H"]),
                    Cc        = float(ld["Cc"]),
                    e0        = float(ld["e0"]),
                    sigma_v0  = float(ld["sigma_v0"]),
                    Cs        = float(ld.get("Cs", 0.0)),
                    sigma_pc  = float(ld["sigma_pc"]) if ld.get("sigma_pc") not in (None, "") else None,
                    cv        = float(ld["cv"])        if ld.get("cv")       not in (None, "") else None,
                    label     = ld.get("label", f"Layer {i+1}"),
                ))

        elif all(params.get(k) not in (None, "") for k in _clay_keys):
            # Path B — single-layer legacy (B-04 fix, retained for backward compat)
            Cc    = float(params["Cc"])
            Cs    = float(params.get("Cs", 0.0))
            e0    = float(params["e0"])
            sv0   = float(params["sigma_v0"])
            H_lay = float(params["H_layer"])
            sp    = float(params["sigma_pc"]) if params.get("sigma_pc") not in (None, "") else None

            # Boussinesq stress at layer mid-point (Sprint 5 upgrade; replaces 2:1)
            from core.boussinesq import stress_below_centre
            B_eff  = fdn.B_eff or fdn.B
            L_eff  = fdn.L_eff or (B_eff * 50)   # strip → large L
            z_mid  = H_lay / 2.0
            delta_sigma = stress_below_centre(q_net_sls, B_eff, L_eff, z_mid)

            consol = consolidation_settlement(
                H=H_lay, Cc=Cc, e0=e0, sigma_v0=sv0,
                delta_sigma=delta_sigma, Cs=Cs, sigma_pc=sp,
            )
            if params.get("cv") not in (None, ""):
                cv    = float(params["cv"])
                U_tgt = float(params.get("t_target_U", 0.95))
                H_dr  = H_lay / 2.0
                t_res = time_to_consolidation(U=U_tgt, H_dr=H_dr, cv=cv)
                t_95  = round(t_res.t, 2)

        res = check_foundation_da1(
            fdn, soil, Gk=Gk, Qk=Qk, Hk=Hk,
            consolidation=consol, s_immediate_res=imm,
            clay_layers=clay_layers, s_lim=s_lim,
        )

        def _c(c):
            return dict(label=c.label,
                        gG=round(c.gG, 2), gQ=round(c.gQ, 2),
                        Vd=round(c.Vd, 2), Rd=round(c.Rd, 2),
                        utilisation=round(c.utilisation, 3), passes=c.passes)

        # Consolidation from whichever path was active
        if res.layer_results:
            s_cons_mm = round(
                sum(lr.consolidation.s_c for lr in res.layer_results) * 1000, 2
            )
            t_95 = res.t_95_years
            layer_breakdown = [
                dict(
                    label       = lr.layer.label or f"Layer {i+1}",
                    H_m         = round(lr.layer.H, 3),
                    z_mid_m     = round(lr.z_mid, 3),
                    delta_sigma = round(lr.delta_sigma, 2),
                    s_c_mm      = round(lr.consolidation.s_c * 1000, 2),
                    t_95_years  = round(lr.t_95, 2) if lr.t_95 is not None else None,
                )
                for i, lr in enumerate(res.layer_results)
            ]
        elif consol is not None:
            s_cons_mm       = round(consol.s_c * 1000, 2)
            layer_breakdown = []
        else:
            s_cons_mm       = None
            layer_breakdown = []

        return dict(
            ok            = True,
            version       = _VERSION,
            analysis_type = "foundation",
            errors        = [],
            foundation    = dict(B=fdn.B, Df=fdn.Df, L=fdn.L,
                                 B_eff=round(fdn.B_eff, 3),
                                 A_eff=round(fdn.A_eff, 4)),
            soil          = dict(name=soil.name, gamma=soil.gamma,
                                 phi_k=soil.phi_k, c_k=soil.c_k),
            comb1         = _c(res.comb1),
            comb2         = _c(res.comb2),
            uls_passes        = res.uls_passes,
            s_immediate_mm    = round(res.s_immediate.s_i * 1000, 2)
                                if res.s_immediate else None,
            s_consolidation_mm= s_cons_mm,
            s_total_mm        = round(res.s_total * 1000, 2)
                                if res.s_total is not None else None,
            s_lim_mm          = round(res.s_lim * 1000, 1),
            sls_passes        = res.sls_passes,
            t_95_years        = round(t_95, 2) if t_95 is not None else None,
            layer_breakdown   = layer_breakdown,
            passes            = res.passes,
            warnings          = list(res.warnings),
        )

    r = _safe(_run)
    if "error" in r and "ok" not in r:
        r.update(ok=False, version=_VERSION,
                 analysis_type="foundation",
                 errors=[r.get("error", "Unknown error")])
    return r


# ── 5. Retaining wall analysis ────────────────────────────────────────────────

def run_wall_analysis(params: dict) -> dict:
    """
    Rankine/Coulomb earth pressure + EC7 DA1 retaining wall checks.

    Required: gamma, phi_k, H_wall (m), B_base (m), B_toe (m)
    Optional: soil_name, c_k, t_stem_base, t_stem_top, t_base,
              surcharge_kpa, gamma_found, phi_k_found, c_k_found

    Returns (schema v1.1):
        ok, version, analysis_type, errors,
        soil (backfill), foundation_soil, wall,
        Ka, Kp, comb1, comb2, passes, warnings

    Each comb includes:
        label, ka, Pa, sliding {H_drive, R_slide, fos_d, passes},
        overturn {MR, MO, fos_d, e, e_limit, passes},
        base_press {N_total, e, B_eff, q_max, q_min, middle_third},
        bearing {B_eff, Df, q_applied, q_ult, utilisation, passes},
        passes

    References:
        EC7 §9, Tables A.3/A.4. Craig §11.4. Bond & Harris Ch.14.
    """
    def _run():
        backfill = Soil(params.get("soil_name", "Backfill"),
                        float(params["gamma"]),
                        float(params["phi_k"]),
                        float(params.get("c_k", 0.0)))
        # B-06 FIX (applied in Sprint 1): foundation soil read from dedicated fields.
        found_s = Soil("Foundation",
                       float(params.get("gamma_found") or params["gamma"]),
                       float(params.get("phi_k_found") or params["phi_k"]),
                       float(params.get("c_k_found")   or params.get("c_k", 0.0)))
        # Sprint 6: wall_type, shear key, counterfort geometry
        wall = RetainingWall(
            h_wall               = float(params["H_wall"]),
            b_base               = float(params["B_base"]),
            b_toe                = float(params["B_toe"]),
            t_stem_base          = float(params.get("t_stem_base", 0.3)),
            t_stem_top           = float(params.get("t_stem_top",  0.3)),
            t_base               = float(params.get("t_base",      0.4)),
            delta_wall           = float(params.get("delta_wall",  0.0)),
            alpha_wall           = float(params.get("alpha_wall",  90.0)),
            beta_backfill        = float(params.get("beta_backfill", 0.0)),
            wall_type            = str(params.get("wall_type", "cantilever")),
            shear_key_depth      = float(params.get("shear_key_depth", 0.0)),
            shear_key_width      = float(params.get("shear_key_width", 0.0)),
            counterfort_spacing  = float(params.get("counterfort_spacing", 0.0)),
            counterfort_thickness= float(params.get("counterfort_thickness", 0.0)),
        )
        q         = float(params.get("surcharge_kpa", 0.0))
        surcharge = UniformSurcharge(q=q) if q > 0 else None

        res = analyse_wall_da1(wall, backfill, found_s, surcharge=surcharge)

        def _sl(s):
            return dict(H_drive=round(s.H_drive, 2),
                        R_slide=round(s.R_slide, 2),
                        fos_d=round(s.fos_d, 3),
                        passes=s.passes)

        def _ov(o):
            return dict(MR=round(o.MR, 2), MO=round(o.MO, 2),
                        fos_d=round(o.fos_d, 3),
                        e=round(o.e, 4), e_limit=round(o.e_limit, 4),
                        passes=o.passes)

        def _bp(b):
            # B-05 FIX: base_press now a separate object (BasePressureResult)
            return dict(N_total=round(b.N_total, 2),
                        e=round(b.e, 4), B_eff=round(b.B_eff, 4),
                        q_max=round(b.q_max, 2), q_min=round(b.q_min, 2),
                        middle_third=b.middle_third)

        def _br(b):
            # B-05 FIX: full EC7 Annex D bearing check now returned
            return dict(B_eff=round(b.B_eff, 4), Df=round(b.Df, 3),
                        q_applied=round(b.q_applied, 2),
                        q_ult=round(b.q_ult, 2),
                        utilisation=round(b.utilisation, 4),
                        passes=b.passes)

        def _c(c):
            return dict(label=c.label,
                        ka=round(c.ka, 4), Pa=round(c.Pa, 2),
                        sliding=_sl(c.sliding),
                        overturn=_ov(c.overturn),
                        base_press=_bp(c.base_press),
                        bearing=_br(c.bearing),
                        passes=c.passes)

        # Sprint 6: EQU overturning serialisation
        eq = res.equ_overturn
        equ_dict = dict(
            MR_perm_char = round(eq.MR_perm_char, 2),
            MO_perm_char = round(eq.MO_perm_char, 2),
            MO_var_char  = round(eq.MO_var_char,  2),
            MR_equ       = round(eq.MR_equ,       2),
            MO_equ       = round(eq.MO_equ,       2),
            N_equ        = round(eq.N_equ,        2),
            fos_d        = round(eq.fos_d,        3),
            e            = round(eq.e,            4),
            e_limit      = round(eq.e_limit,      4),
            passes       = eq.passes,
        ) if eq is not None else None

        return dict(
            ok            = True,
            version       = _VERSION,
            analysis_type = "wall",
            errors        = [],
            soil          = dict(name=backfill.name, gamma=backfill.gamma,
                                 phi_k=backfill.phi_k, c_k=backfill.c_k),
            foundation_soil = dict(name=found_s.name, gamma=found_s.gamma,
                                   phi_k=found_s.phi_k, c_k=found_s.c_k),
            wall          = dict(H_wall=wall.h_wall, B_base=wall.b_base,
                                 B_toe=wall.b_toe, b_heel=round(wall.b_heel, 3),
                                 t_stem_base=wall.t_stem_base,
                                 t_stem_top=wall.t_stem_top,
                                 t_base=wall.t_base,
                                 wall_type=wall.wall_type,
                                 shear_key_depth=wall.shear_key_depth,
                                 counterfort_spacing=wall.counterfort_spacing),
            Ka            = round(ka_rankine(backfill.phi_k), 4),
            Kp            = round(kp_rankine(backfill.phi_k), 4),
            comb1         = _c(res.comb1),
            comb2         = _c(res.comb2),
            equ_overturn  = equ_dict,
            stem          = dict(
                ka      = round(res.stem.ka,    4),
                phi_d   = round(res.stem.phi_d, 3),
                q_sur   = round(res.stem.q_sur, 2),
                M_max   = round(res.stem.M_max, 3),
                V_max   = round(res.stem.V_max, 3),
                z_M_max = round(res.stem.z_M_max, 3),
                diagram = [
                    dict(z=round(p.z, 3), M=round(p.M, 3), V=round(p.V, 3))
                    for p in res.stem.diagram
                ],
            ) if res.stem is not None else None,
            passes        = res.passes,
            warnings      = list(res.warnings),
        )

    r = _safe(_run)
    if "error" in r and "ok" not in r:
        r.update(ok=False, version=_VERSION,
                 analysis_type="wall",
                 errors=[r.get("error", "Unknown error")])
    return r


# ── 6. Foundation + Wall export helpers  (B-07) ──────────────────────────────

def export_foundation_pdf(analysis: dict, out_path: str,
                          project="DesignApp", job_ref="",
                          calc_by="", checked_by="") -> str:
    """
    Generate PDF calculation sheet for foundation bearing capacity → out_path.

    Delegates to exporters/report_pdf.py::generate_foundation_report().

    :param analysis:   Result dict from run_foundation_analysis().
    :param out_path:   Filesystem path for the output PDF.
    :param project:    Project name for the header.
    :param job_ref:    Job reference.
    :param calc_by:    Initials of the person who ran the analysis.
    :param checked_by: Initials of the checker.
    :return:           out_path.
    """
    from exporters.report_pdf import generate_foundation_report
    generate_foundation_report(out_path, analysis,
                               project=project, job_ref=job_ref,
                               calc_by=calc_by, checked_by=checked_by)
    return out_path


def export_foundation_docx(analysis: dict, out_path: str,
                           project="DesignApp", job_ref="",
                           calc_by="", checked_by="") -> str:
    """Generate Word calculation sheet for foundation → out_path."""
    from exporters.report_docx import generate_foundation_report_docx
    generate_foundation_report_docx(out_path, analysis,
                                    project=project, job_ref=job_ref,
                                    calc_by=calc_by, checked_by=checked_by)
    return out_path


def export_wall_pdf(analysis: dict, out_path: str,
                    project="DesignApp", job_ref="",
                    calc_by="", checked_by="") -> str:
    """Generate PDF calculation sheet for retaining wall → out_path."""
    from exporters.report_pdf import generate_wall_report
    generate_wall_report(out_path, analysis,
                         project=project, job_ref=job_ref,
                         calc_by=calc_by, checked_by=checked_by)
    return out_path


def export_wall_docx(analysis: dict, out_path: str,
                     project="DesignApp", job_ref="",
                     calc_by="", checked_by="") -> str:
    """Generate Word calculation sheet for retaining wall → out_path."""
    from exporters.report_docx import generate_wall_report_docx
    generate_wall_report_docx(out_path, analysis,
                              project=project, job_ref=job_ref,
                              calc_by=calc_by, checked_by=checked_by)
    return out_path


def export_sheet_pile_pdf(analysis: dict, out_path: str,
                          project="DesignApp", job_ref="",
                          calc_by="", checked_by="") -> str:
    """Generate PDF calculation sheet for sheet pile analysis → out_path."""
    from exporters.report_pdf import generate_sheet_pile_report
    generate_sheet_pile_report(out_path, analysis,
                               project=project, job_ref=job_ref,
                               calc_by=calc_by, checked_by=checked_by)
    return out_path


def export_sheet_pile_docx(analysis: dict, out_path: str,
                           project="DesignApp", job_ref="",
                           calc_by="", checked_by="") -> str:
    """Generate Word calculation sheet for sheet pile analysis → out_path."""
    from exporters.report_docx import generate_sheet_pile_report_docx
    generate_sheet_pile_report_docx(out_path, analysis,
                                    project=project, job_ref=job_ref,
                                    calc_by=calc_by, checked_by=checked_by)
    return out_path


def export_wall_plot_png(analysis: dict, dpi: int = 150) -> bytes:
    """
    Retaining wall cross-section with earth pressure diagram → PNG bytes.

    Delegates to plot_wall.plot_retaining_wall().
    Returns raw PNG bytes so the Flask route can stream them directly.

    :param analysis: Result dict from run_wall_analysis().
    :param dpi:      Output resolution (default 150).
    :return:         PNG bytes.
    """
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from exporters.plot_wall import plot_retaining_wall
    w   = analysis.get("wall", {})
    lbl = w.get("label", "")
    fig = plot_retaining_wall(
        analysis,
        title=f"Retaining Wall Cross-Section — {lbl}" if lbl else "Retaining Wall",
    )
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight")
    plt.close(fig); buf.seek(0)
    return buf.read()


def export_foundation_plot_png(analysis: dict, dpi: int = 150) -> bytes:
    """
    Foundation cross-section with stress bulb → PNG bytes.

    Delegates to plot_foundation.plot_foundation_bearing().
    Returns raw PNG bytes so the Flask route can stream them directly.

    :param analysis: Result dict from run_foundation_analysis().
    :param dpi:      Output resolution (default 150).
    :return:         PNG bytes.
    """
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from exporters.plot_foundation import plot_foundation_bearing
    s   = analysis.get("soil", {})
    lbl = s.get("name", "")
    fig = plot_foundation_bearing(
        analysis,
        title=f"Foundation Bearing Capacity — {lbl}" if lbl else "Foundation",
    )
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight")
    plt.close(fig); buf.seek(0)
    return buf.read()


def export_project_pdf(
    analyses  : list,
    out_path  : str,
    project   : str = "DesignApp Project",
    job_ref   : str = "—",
    calc_by   : str = "DesignApp",
    checked_by: str = "—",
) -> str:
    """
    Unified multi-section PDF combining all completed analyses.

    Delegates to report_pdf.generate_project_report().
    The report contains: cover page, table of contents, and one section
    per analysis (slope, foundation, wall, sheet pile) with sequential
    page numbers.

    :param analyses:   List of result dicts from any run_*_analysis().
    :param out_path:   Output PDF file path.
    :param project:    Project name for cover page / header.
    :param job_ref:    Job reference.
    :param calc_by:    Initials of person who ran the analyses.
    :param checked_by: Initials of checker.
    :return:           out_path.
    """
    from exporters.report_pdf import generate_project_report
    generate_project_report(
        analyses=analyses, out_path=out_path,
        project=project, job_ref=job_ref,
        calc_by=calc_by, checked_by=checked_by,
    )
    return out_path


# ── 6b. Pile analysis  ────────────────────────────────────────────────────────

def run_pile_analysis(params: dict) -> dict:
    """
    EC7 §7 axial pile capacity + DA1 ULS verification.

    Required
    --------
    layers : list of layer dicts (at least one), each containing:
        thickness    : float (m)
        gamma        : float (kN/m³)
        phi_k        : float (degrees) — set 0 for clay
        c_k          : float (kPa)    — set 0 for sand
        soil_type    : 'clay' | 'sand'
        K_s          : float (optional — overrides pile-type default)
        delta_factor : float (optional — interface friction ratio, default 2/3)
        label        : str   (optional)
    diameter   : float (m)
    length     : float (m)  — must equal sum of layer thicknesses
    Gk         : float (kN) — characteristic permanent action (compression +ve)
    Qk         : float (kN) — characteristic variable action (default 0)

    Optional
    --------
    pile_type      : 'driven' | 'bored' | 'CFA'   (default 'driven')
    material       : 'concrete' | 'steel'          (default 'concrete')
    gamma_concrete : float (kN/m³, default 24.0)

    Returns (schema v1.1)
    ---------------------
    ok, version, analysis_type, errors, warnings,
    pile  : {pile_type, diameter, length, material, perimeter, area_base,
             self_weight, slenderness},
    R_b_k, R_s_k, R_c_k, q_b_k,
    layer_results : [{label, soil_type, thickness, z_top, z_bot,
                      sigma_v_mid, alpha, q_s_k, A_s, R_s_k}],
    comb1, comb2  : {label, gamma_G, gamma_Q, gamma_phi,
                     gamma_b, gamma_s, F_c_d, R_b_d, R_s_d, R_c_d,
                     utilisation, passes},
    governing     : str ('DA1-C1' | 'DA1-C2'),
    passes        : bool

    References
    ----------
    EC7 EN 1997-1:2004, §7.6.2; Tables A.6/A.7.
    Craig's Soil Mechanics, 9th ed., §11.
    Tomlinson (1970); Meyerhof (1976); Skempton (1951).
    """
    def _run():
        pile = Pile(
            pile_type      = str(params.get("pile_type",      "driven")),
            diameter       = float(params["diameter"]),
            length         = float(params["length"]),
            gamma_concrete = float(params.get("gamma_concrete", 24.0)),
            material       = str(params.get("material",       "concrete")),
        )
        raw_layers = params.get("layers") or []
        if not raw_layers:
            raise ValueError("'layers' is required and must be a non-empty list.")
        layers = []
        for i, ld in enumerate(raw_layers):
            lbl = ld.get("label", f"Layer {i+1}")
            kw = dict(
                thickness    = float(ld["thickness"]),
                gamma        = float(ld["gamma"]),
                phi_k        = float(ld.get("phi_k", 0.0)),
                c_k          = float(ld.get("c_k",   0.0)),
                soil_type    = str(ld["soil_type"]),
                label        = lbl,
            )
            if ld.get("K_s") not in (None, ""):
                kw["K_s"] = float(ld["K_s"])
            if ld.get("delta_factor") not in (None, ""):
                kw["delta_factor"] = float(ld["delta_factor"])
            layers.append(PileSoilLayer(**kw))

        Gk = float(params["Gk"])
        Qk = float(params.get("Qk", 0.0))
        res = verify_pile_da1(pile, layers, Gk=Gk, Qk=Qk)

        def _lr(lr):
            return dict(
                label=lr.label, soil_type=lr.soil_type,
                thickness=round(lr.thickness, 3),
                z_top=round(lr.z_top, 3), z_bot=round(lr.z_bot, 3),
                sigma_v_mid=round(lr.sigma_v_mid, 2),
                alpha=round(lr.alpha, 4),
                q_s_k=round(lr.q_s_k, 3),
                A_s=round(lr.A_s, 4),
                R_s_k=round(lr.R_s_k, 2),
            )

        def _comb(c):
            return dict(
                label=c.label, gamma_G=c.gamma_G, gamma_Q=c.gamma_Q,
                gamma_phi=c.gamma_phi, gamma_b=c.gamma_b, gamma_s=c.gamma_s,
                F_c_d=round(c.F_c_d, 2), R_b_d=round(c.R_b_d, 2),
                R_s_d=round(c.R_s_d, 2), R_c_d=round(c.R_c_d, 2),
                utilisation=round(c.utilisation, 4), passes=c.passes,
            )

        return dict(
            ok=True, version=_VERSION, analysis_type="pile", errors=[],
            pile=dict(
                pile_type=pile.pile_type, diameter=pile.diameter,
                length=pile.length, material=pile.material,
                perimeter=round(pile.perimeter, 4),
                area_base=round(pile.area_base, 5),
                self_weight=round(pile.self_weight, 2),
                slenderness=round(pile.slenderness, 2),
            ),
            R_b_k=round(res.R_b_k, 2), R_s_k=round(res.R_s_k, 2),
            R_c_k=round(res.R_c_k, 2), q_b_k=round(res.q_b_k, 2),
            layer_results=[_lr(lr) for lr in res.layer_results],
            comb1=_comb(res.comb1), comb2=_comb(res.comb2),
            governing=res.governing.label,
            passes=res.passes,
            warnings=list(res.warnings),
        )

    r = _safe(_run)
    if "error" in r and "ok" not in r:
        r.update(ok=False, version=_VERSION, analysis_type="pile",
                 errors=[r.get("error", "Unknown error")])
    return r



# ── 7. Input validation ───────────────────────────────────────────────────────

def validate_slope_params(params: dict) -> list:
    errs = []
    for f in ("gamma","phi_k","slope_points"):
        if params.get(f) is None or params.get(f) == "":
            errs.append(f"'{f}' is required.")
    try:
        g = float(params.get("gamma",0))
        if not (10 <= g <= 25): errs.append("γ should be 10–25 kN/m³.")
    except: errs.append("γ must be a number.")
    try:
        p = float(params.get("phi_k",-1))
        if not (0 <= p < 90): errs.append("φ'k must be 0–90°.")
    except: errs.append("φ'k must be a number.")
    pts = params.get("slope_points",[])
    if isinstance(pts, list) and len(pts) < 2:
        errs.append("Slope requires ≥ 2 points.")
    return errs


def validate_foundation_params(params: dict) -> list:
    errs = []
    for f in ("gamma","phi_k","B","Df","Gk"):
        if params.get(f) is None or params.get(f) == "":
            errs.append(f"'{f}' is required.")
    return errs


def validate_wall_params(params: dict) -> list:
    errs = []
    for f in ("gamma","phi_k","H_wall","B_base","B_toe"):
        if params.get(f) is None or params.get(f) == "":
            errs.append(f"'{f}' is required.")
    return errs


def validate_pile_params(params: dict) -> list:
    """
    Validate run_pile_analysis() input dict.

    Returns a list of error strings (empty = valid).
    """
    errs = []
    for f in ("diameter", "length", "Gk", "layers"):
        if params.get(f) is None or params.get(f) == "":
            errs.append(f"'{f}' is required.")
    try:
        d = float(params.get("diameter", 0))
        if d <= 0:
            errs.append("diameter must be > 0.")
    except (TypeError, ValueError):
        errs.append("diameter must be a number.")
    try:
        L = float(params.get("length", 0))
        if L <= 0:
            errs.append("length must be > 0.")
    except (TypeError, ValueError):
        errs.append("length must be a number.")
    try:
        gk = float(params.get("Gk", -1))
        if gk < 0:
            errs.append("Gk must be >= 0.")
    except (TypeError, ValueError):
        errs.append("Gk must be a number.")
    pt = params.get("pile_type", "driven")
    if pt not in ("driven", "bored", "CFA"):
        errs.append(f"pile_type must be 'driven', 'bored', or 'CFA', got {pt!r}.")
    layers = params.get("layers")
    if isinstance(layers, list):
        for i, ld in enumerate(layers):
            for k in ("thickness", "gamma", "soil_type"):
                if ld.get(k) is None or ld.get(k) == "":
                    errs.append(f"Layer {i+1}: '{k}' is required.")
            st = ld.get("soil_type")
            if st not in ("clay", "sand", None, ""):
                errs.append(f"Layer {i+1}: soil_type must be 'clay' or 'sand'.")
    return errs


# ─────────────────────────────────────────────────────────────────────────────
#  Sprint 10 — Sheet Pile Free-Earth Support
# ─────────────────────────────────────────────────────────────────────────────

def run_sheet_pile_analysis(params: dict) -> dict:
    """
    Run a free-earth support sheet pile analysis (EC7 DA1).

    Input dict keys
    ───────────────
    Required:
        h_retained   float  Retained height above excavation (m)
        phi_k        float  Characteristic friction angle (degrees)
        gamma        float  Soil unit weight (kN/m³)

    Optional:
        z_prop       float  Prop depth from excavation datum (m).
                            Negative = above excavation (default = −h_retained,
                            i.e. prop at top of retained soil).
        q            float  Uniform surcharge on retained surface (kPa, default 0).
        z_w          float  Depth to water table from top of retained soil (m).
                            None / omitted = dry analysis.
        label        str    Human-readable label for the wall (default 'Sheet Pile').
        n_diagram    int    Number of embedded-zone points in pressure diagram
                            (default 20).

    Output schema v1.1
    ──────────────────
        ok              bool
        version         '1.1'
        analysis_type   'sheet_pile'
        errors          list[str]  — empty on success
        warnings        list[str]
        wall            dict  — geometry sub-dict
        Ka_k, Kp_k      float
        comb1, comb2    dict  — per-combination results
        governing       str   — 'DA1-C1' or 'DA1-C2'
        d_design        float
        T_design        float  prop force (kN/m)
        M_max_design    float  max bending moment (kN·m/m)
        z_Mmax_design   float  depth of M_max below prop (m)
        pressure_diagram list[dict]  — [{z, z_datum, p_a, p_p, u, p_net}, …]
        passes          bool

    Never raises — errors are returned in the 'errors' list.

    Reference:
        Craig §12.2; EC7 §9.7.4; Blum (1931).
    """
    params = _normalise_sheet_pile_params(params)
    errs = validate_sheet_pile_params(params)
    if errs:
        return {"ok": False, "version": "1.1", "analysis_type": "sheet_pile",
                "errors": errs, "warnings": []}

    try:
        h        = float(params["h_retained"])
        phi_k    = float(params["phi_k"])
        gamma    = float(params["gamma"])
        q        = float(params.get("q", 0.0))
        z_w_raw  = params.get("z_w")
        z_w      = float(z_w_raw) if z_w_raw is not None else None
        label    = str(params.get("label", "Sheet Pile"))
        support  = str(params.get("support", "propped"))

        # z_prop: stored in SheetPile as depth from top of pile (dredge datum is 0)
        # API input: depth from excavation level, negative = above excavation
        # Default: prop at top of retained soil = -h_retained
        if support == "propped":
            z_prop_api = float(params.get("z_prop", -h))
        else:
            z_prop_api = None

        pile = SheetPile(
            h_retained=h,
            support=support,
            z_prop=z_prop_api,
            label=label,
        )
        soil = Soil(label, gamma, phi_k, 0.0)

        res = analyse_sheet_pile_da1(pile, soil, q=q, z_w=z_w)

        def _comb_dict(c):
            return {
                "label":     c.label,
                "gamma_phi": c.gamma_phi,
                "phi_d_deg": round(c.phi_d_deg, 4),
                "Ka_d":      round(c.Ka_d, 6),
                "Kp_d":      round(c.Kp_d, 6),
                "d_min":     round(c.d_min, 4),
                "T_k":       round(c.T_k, 4),
                "z_Mmax":    round(c.z_Mmax, 4),
                "M_max":     round(c.M_max, 4),
                "converged": c.converged,
            }

        diagram = [
            {
                "z":       p.z,
                "z_datum": p.z_datum,
                "p_a":     p.p_a,
                "p_p":     p.p_p,
                "u":       p.u,
                "p_net":   p.p_net,
            }
            for p in res.pressure_diagram
        ]

        return {
            "ok":            True,
            "version":       "1.1",
            "analysis_type": "sheet_pile",
            "errors":        [],
            "warnings":      res.warnings,
            "wall": {
                "label":        label,
                "h_retained":   h,
                "z_prop":       z_prop_api,
                "support":      support,
                "d_design":     round(res.d_design, 4),
                "total_length": round(h + res.d_design, 4),
            },
            "Ka_k":           round(res.Ka_k, 6),
            "Kp_k":           round(res.Kp_k, 6),
            "comb1":          _comb_dict(res.comb1),
            "comb2":          _comb_dict(res.comb2),
            "governing":      res.governing.label,
            "governing_combination": res.governing.label,
            "d_design":       round(res.d_design, 4),
            "T_design":       round(res.T_design, 4),
            "M_max_design":   round(res.M_max_design, 4),
            "z_Mmax_design":  round(res.governing.z_Mmax, 4),
            "pressure_diagram": diagram,
            "passes":         res.passes,
        }

    except Exception as exc:
        return {
            "ok": False, "version": "1.1", "analysis_type": "sheet_pile",
            "errors": [f"Unexpected error: {exc}"], "warnings": [],
        }


def validate_sheet_pile_params(params: dict) -> list:
    """
    Validate run_sheet_pile_analysis() input dict.

    Returns a list of error strings (empty = valid).
    """
    params = _normalise_sheet_pile_params(params)
    errs = []
    for f in ("h_retained", "phi_k", "gamma"):
        if params.get(f) is None or params.get(f) == "":
            errs.append(f"'{f}' is required.")
    try:
        h = float(params.get("h_retained", 0))
        if h <= 0:
            errs.append("h_retained must be > 0.")
    except (TypeError, ValueError):
        errs.append("h_retained must be a number.")
    try:
        phi = float(params.get("phi_k", -1))
        if not (0 < phi < 90):
            errs.append("phi_k must be in (0, 90) degrees.")
    except (TypeError, ValueError):
        errs.append("phi_k must be a number.")
    try:
        g = float(params.get("gamma", 0))
        if g <= 0:
            errs.append("gamma must be > 0.")
    except (TypeError, ValueError):
        errs.append("gamma must be a number.")
    try:
        q = float(params.get("q", 0))
        if q < 0:
            errs.append("q (surcharge) must be >= 0.")
    except (TypeError, ValueError):
        errs.append("q must be a number.")
    z_w_raw = params.get("z_w")
    if z_w_raw is not None and z_w_raw != "":
        try:
            z_w = float(z_w_raw)
            if z_w < 0:
                errs.append("z_w must be >= 0.")
        except (TypeError, ValueError):
            errs.append("z_w must be a number.")
    return errs


def _normalise_sheet_pile_params(params: dict | None) -> dict:
    """
    Accept legacy UI field names and map them to the canonical API schema.

    This keeps the legacy Jinja form, the React SPA, and api.py aligned while
    Phase 6 stabilisation is still in progress.
    """
    if not params:
        return {}

    norm = dict(params)

    if norm.get("h_retained") in (None, "") and norm.get("h_retain") not in (None, ""):
        norm["h_retained"] = norm.get("h_retain")
    if norm.get("q") in (None, "") and norm.get("surcharge_kpa") not in (None, ""):
        norm["q"] = norm.get("surcharge_kpa")

    prop_type = norm.get("prop_type")
    if prop_type and norm.get("support") in (None, ""):
        norm["support"] = "free" if prop_type == "cantilever" else "propped"

    if prop_type and norm.get("z_prop") in (None, ""):
        try:
            h = float(norm["h_retained"])
        except (KeyError, TypeError, ValueError):
            return norm

        if prop_type == "cantilever":
            norm["z_prop"] = None
        elif prop_type == "propped_mid":
            norm["z_prop"] = -h / 2.0
        else:
            norm["z_prop"] = -h

    return norm
