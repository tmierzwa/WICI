# SPDX-License-Identifier: MIT
"""Export controller-only fabrication and assembly files with one common origin.

These are R01.3 candidate outputs. Exporting does not approve connector fit,
USB operation, firmware or the separate RF module.
"""
from pathlib import Path
import argparse
import csv
import json
import shutil
import subprocess

from pack_fabrication import main as pack

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    """Generate fabrication outputs, the assembly PDF and the licensed ZIP."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--kicad-cli", default="kicad-cli")
    args = parser.parse_args()
    version = subprocess.check_output([args.kicad_cli, "version"], text=True).strip()
    if version != "10.0.6":
        raise ValueError(f"Expected KiCad 10.0.6; found {version}")
    base = ROOT / "fabrication/R01.3"
    g, d, a = (base / name for name in ("gerbers", "drill", "assembly"))
    for folder in (g, d, a):
        folder.mkdir(parents=True, exist_ok=True)
    board = ROOT / "cad/radio-usb-controller.kicad_pcb"

    def run(*command: object) -> None:
        subprocess.run([args.kicad_cli, "pcb", "export", *map(str, command), str(board)], check=True)

    run("gerbers", "--layers", "F.Cu,In1.Cu,In2.Cu,B.Cu,F.Mask,B.Mask,F.SilkS,B.SilkS,Edge.Cuts",
        "--subtract-soldermask", "--use-drill-file-origin", "--check-zones", "--output", str(g) + "/")
    run("drill", "--format", "excellon", "--excellon-units", "mm", "--excellon-zeros-format", "decimal",
        "--excellon-separate-th", "--drill-origin", "plot", "--generate-map", "--map-format", "pdf",
        "--generate-report", "--report-path", d / "drill-report.txt", "--output", str(d) + "/")
    run("pos", "--format", "csv", "--units", "mm", "--side", "front", "--use-drill-file-origin",
        "--exclude-dnp", "--output", a / "positions-all.csv")
    run("pos", "--format", "csv", "--units", "mm", "--side", "front", "--use-drill-file-origin",
        "--smd-only", "--exclude-dnp", "--output", a / "positions-smt.csv")
    run("gerbers", "--layers", "F.Paste", "--use-drill-file-origin", "--output", str(a) + "/")
    run("pdf", "--layers", "F.Fab,F.SilkS,Edge.Cuts", "--mode-single", "--black-and-white",
        "--sketch-pads-on-fab-layers", "--scale", "2", "--output", a / "assembly-drawing.pdf")
    subprocess.run([args.kicad_cli, "sch", "export", "pdf", "--output", str(ROOT / "schemat.pdf"),
                    str(ROOT / "cad/radio-usb-controller.kicad_sch")], check=True)
    with (ROOT / "bom.csv").open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    groups = {}
    for row in rows:
        key = (row["manufacturer"], row["mpn"], row["footprint"])
        groups.setdefault(key, []).append(row)
    with (a / "bom.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Designators", "Quantity", "Manufacturer", "MPN", "Value", "Footprint",
                         "Assembly", "Specification", "Datasheet"])
        for (manufacturer, mpn, footprint), items in groups.items():
            row = items[0]
            writer.writerow([",".join(item["reference"] for item in items), len(items), manufacturer, mpn,
                             row["value_or_MPN"], footprint, row["assembly"], row["specification"], row["datasheet"]])
    shutil.copyfile(ROOT / "mechanika-1-do-1.pdf", base / "mechanika-1-do-1.pdf")
    stack = json.loads((ROOT / "checks/stackup.json").read_text(encoding="utf-8"))
    (base / "stackup.json").write_text(json.dumps(stack, indent=2) + "\n")
    pack()
    print("Exports complete. Run verify_fabrication.py and check_bundle.py before using the candidate.")


if __name__ == "__main__":
    main()
