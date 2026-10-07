# SPDX-License-Identifier: MIT
"""Package controller exports with their licenses; retain manufacturing HOLD."""

from pathlib import Path
import hashlib
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parents[1]))
from tools.archives import verify_archive, write_archive

REQUIRED = {
    "README.md", "NOTICE.md", "LICENSES/CERN-OHL-P-2.0.txt",
    "LICENSES/CC-BY-4.0.txt", "stackup.json", "mechanika-1-do-1.pdf",
    "assembly/assembly-drawing.pdf", "assembly/positions-all.csv",
    "assembly/positions-smt.csv", "assembly/bom.csv",
    "assembly/radio-usb-controller-F_Paste.gtp",
    "drill/radio-usb-controller-PTH.drl", "drill/radio-usb-controller-NPTH.drl",
    "drill/radio-usb-controller-PTH-drl_map.pdf",
    "drill/radio-usb-controller-NPTH-drl_map.pdf", "drill/drill-report.txt",
    "gerbers/radio-usb-controller-job.gbrjob",
    "assembly/radio-usb-controller-job.gbrjob",
    *{f"gerbers/radio-usb-controller-{layer}.{ext}" for layer, ext in (
        ("F_Cu", "gtl"), ("In1_Cu", "g1"), ("In2_Cu", "g2"), ("B_Cu", "gbl"),
        ("F_Mask", "gts"), ("B_Mask", "gbs"), ("F_Silkscreen", "gto"),
        ("B_Silkscreen", "gbo"), ("Edge_Cuts", "gm1"))},
}


def fabrication_files(root: Path = ROOT) -> dict[str, Path]:
    """Require the complete controller package, including notices and drawings."""
    base = root / "fabrication/R01.3"
    files = {p.relative_to(base).as_posix(): p for p in base.rglob("*") if p.is_file()}
    if set(files) != REQUIRED:
        raise ValueError(f"Fabrication file set mismatch; missing={sorted(REQUIRED - files.keys())}, extra={sorted(files.keys() - REQUIRED)}")
    if "HOLD" not in files["NOTICE.md"].read_text(encoding="utf-8"):
        raise ValueError("Fabrication notice must retain HOLD")
    return files


def prepare_notices() -> None:
    """Copy complete license texts and attribution into the standalone package."""
    base = ROOT / "fabrication/R01.3"
    (base / "LICENSES").mkdir(exist_ok=True)
    for name in ("CERN-OHL-P-2.0", "CC-BY-4.0"):
        (base / f"LICENSES/{name}.txt").write_bytes((ROOT.parents[1] / f"LICENSES/{name}.txt").read_bytes())
    (base / "NOTICE.md").write_text(
        "# WICI controller R01.3 — HOLD\n\n"
        "WICI contributors. Source and editable KiCad project: https://github.com/tmierzwa/WICI\n\n"
        "Source PCB SHA-256: " + hashlib.sha256((ROOT / "cad/radio-usb-controller.kicad_pcb").read_bytes()).hexdigest() + "\n\n"
        "Source schematic SHA-256: " + hashlib.sha256((ROOT / "cad/radio-usb-controller.kicad_sch").read_bytes()).hexdigest() + "\n\n"
        "Gerbers, drills, BOM, placements, stackup and drawings: CERN-OHL-P-2.0. "
        "README and this notice: CC-BY-4.0. Full texts are in LICENSES/.\n\n"
        "KiCad library content was used in the design under CC-BY-SA-4.0 with the "
        "KiCad design exception. That exception permits distribution of design outputs "
        "under the chosen design license. Library source, attribution and the complete "
        "exception are in hardware/radio-test-r01/cad/KICAD-LIBRARY-LICENSE.md in the source repository. "
        "Library files are not bundled here. Reticulum is a separate upstream project.\n\n"
        "Manufacturing status: HOLD. Physical connector fit, USB electrical operation, "
        "firmware and circuit qualification have not been tested. This is a controller "
        "candidate, not a working radio or a shelter deployment release.\n",
        encoding="utf-8",
    )


def main() -> None:
    """Package the already exported candidate without regenerating geometry."""
    prepare_notices()
    files = fabrication_files()
    archive = ROOT / "fabrication/wici-controller-R01.3.zip"
    write_archive(archive, files)
    verify_archive(archive, files)
    print(f"Controller package verified: {len(files)} files; HOLD")


if __name__ == "__main__":
    main()
