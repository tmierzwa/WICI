# WICI — R01.3 USB controller — fabrication candidate

Project: WICI.

This package contains only the 70 x 55 mm USB controller. It does not contain the CC1120 RF module.

Status: HOLD. Physical connector fit, USB operation and circuit qualification are pending. These files are not a tested hardware release.

## PCB specification

- Four-layer FR-4, nominal finished thickness 1.6 mm.
- Standard reference construction: JLCPCB JLC04161H-7628. Any fabricator may use an explicitly confirmed equivalent construction. Do not substitute an unspecified four-layer stack.
- Layer order: F.Cu / In1.Cu GND / In2.Cu 3.3 V / B.Cu.
- Copper: 35 / 15.2 / 15.2 / 35 micrometres.
- Dielectrics: 0.2104 mm 7628 prepreg / 1.065 mm core / 0.2104 mm 7628 prepreg. Dk: 4.4 / 4.6 / 4.4.
- The laminate dimensions sum to 1.5862 mm before coating. 1.6 mm is the manufacturer's nominal board thickness. Soldermask is nonuniform; its CAD thickness is a model, not a separate exact finished-thickness requirement.
- Green soldermask, white silkscreen, lead-free HASL.
- KiCad serializes a default dielectric loss tangent of 0.02. This is not a measured or qualified material value.
- No controlled-impedance qualification is claimed. USB geometry still requires assessment for this construction.
- Four unplated mounting holes: 3.2 mm. Do not plate NPTH holes.
- Minimum copper clearance 0.2 mm, minimum track width 0.18 mm. Vias 0.6/0.3 mm.
- Do not mirror any file. Origin is the board lower-left corner; +X right and +Y up; coordinates are millimetres.

## Files

`gerbers/`: four copper layers, two mask layers, two silkscreen layers, board outline and Gerber job metadata.

`drill/`: separate PTH and NPTH Excellon files, drill maps and a report. There are 97 plated and 4 unplated drill hits. Excellon coordinates have 1 micrometre resolution.

`assembly/`: grouped BOM with manufacturer part numbers, 39 full placements, 34 SMT placements and front-side stencil Gerber. All components are on the front side. The five THT components are J1, J2, J3, J4 and SW1. Do not place test points TP1-TP7 or mounting features H1-H4.

The position file uses KiCad footprint origins and rotations. It is not a universal machine program. The assembler must map the selected component packaging to those rotations and confirm pin 1 and LED polarity. The X2 pad coordinates were checked against PCB data.

D1: Kingbright APT2012LSECK/J3-PRV; pad 1 = cathode/GND, pad 2 = anode.

SW1: Omron B3F-1000; KiCad pad group 1 corresponds to Omron terminals 3 and 4; pad group 2 to Omron terminals 1 and 2. Use the top-view datasheet orientation. Pin pairs in each row are internally common; pressing connects the rows.

J2: Wurth 61201021621, keyed 2x5 IDC. The finished pin holes are 1.1 mm. Confirm notch and pin 1 against the assembly drawing and actual cable.

`mechanika-1-do-1.pdf`: print at actual size, 100%, no fit-to-page. Check the 50 mm calibration line, then fit the real USB-B, switch and IDC connector. Record the result before ordering.

Manufacturer data: https://jlcpcb.com/impedance

## Source and licenses

Editable source: https://github.com/tmierzwa/WICI. Construction outputs: CERN-OHL-P-2.0. README: CC-BY-4.0. See NOTICE.md and LICENSES/ for full terms. `assembly/assembly-drawing.pdf` is a top-side assembly drawing at 2:1; use the separate mechanical PDF for the 1:1 fit check.
