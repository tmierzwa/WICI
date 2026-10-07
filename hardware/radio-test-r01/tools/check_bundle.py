# SPDX-License-Identifier: MIT
"""Record actual CAD check results and bind them to file hashes.

This is an artifact audit, not independent electrical review or a bench test.
It does not change the manufacturing HOLD state when software checks pass.
"""
from pathlib import Path
import hashlib
import json
import argparse
from pack_fabrication import fabrication_files, verify_archive

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Verify without rewriting evidence")
    args = parser.parse_args()
    erc = json.loads((ROOT / 'checks/erc-controller.json').read_text())
    drc = json.loads((ROOT / 'checks/drc-controller.json').read_text())
    rf = json.loads((ROOT / 'checks/drc-ti-reference.json').read_text())
    erc_count = sum(len(s['violations']) for s in erc['sheets'])
    if not (erc_count == 0):
        raise ValueError('Artifact check failed: erc_count == 0')
    if not (not drc['violations'] and not drc['unconnected_items'] and not drc['schematic_parity']):
        raise ValueError("Artifact check failed: not drc['violations'] and not drc['unconnected_items'] and not drc['schematic_parity']")
    audit = json.loads((ROOT / 'checks/ti-source-net-comparison.json').read_text())
    expected = {('U1', str(p)) for p in range(34, 47)}
    if not ({tuple(d['pin']) for d in audit['differences']} == expected):
        raise ValueError("Artifact check failed: {tuple(d['pin']) for d in audit['differences']} == expected")
    if not (all(not d['schematic'] for d in audit['differences'])):
        raise ValueError("Artifact check failed: all(not d['schematic'] for d in audit['differences'])")
    groups = [frozenset([tuple(d['pin']), *map(tuple, d['pcb'])]) for d in audit['differences']]
    if not (len(set(groups)) == 1 and ('P1', '1') in groups[0] and ('P2', '2') in groups[0]):
        raise ValueError("Artifact check failed: len(set(groups)) == 1 and ('P1', '1') in groups[0] and ('P2', '2') in groups[0]")
    summary = {
        'source': 'original TI CSA and CPA connection-group comparison',
        'common_connected_pins': audit['connected_pin_count_schematic'],
        'common_connection_mismatches': 0,
        'expected_pcb_only_ground_lands': sorted(expected),
        'scope': 'Logical connection groups only; does not verify physical RF geometry or performance.',
    }
    if not args.check:
        (ROOT / 'checks/ti-net-summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    revision = json.loads((ROOT / 'checks/controller-revision.json').read_text())
    if not (revision['internal_layer_tracks'] == 0 and revision['USB_routes_unchanged']):
        raise ValueError("Artifact check failed: revision['internal_layer_tracks'] == 0 and revision['USB_routes_unchanged']")
    if not (len(revision['mounting_holes']) == 4 and len(revision['capacitors']) == 14):
        raise ValueError("Artifact check failed: len(revision['mounting_holes']) == 4 and len(revision['capacitors']) == 14")
    replay = json.loads((ROOT / 'checks/replay-verification.json').read_text())
    if not (replay['geometry_identical'] and replay['schematic_BOM_connections_identical']):
        raise ValueError("Artifact check failed: replay['geometry_identical'] and replay['schematic_BOM_connections_identical']")
    if not (replay['candidate_pcb_sha256'] == sha(ROOT / 'cad/radio-usb-controller.kicad_pcb')):
        raise ValueError("Artifact check failed: replay['candidate_pcb_sha256'] == sha(ROOT / 'cad/radio-usb-controller.kicad_pcb')")
    if not (replay['candidate_schematic_sha256'] == sha(ROOT / 'cad/radio-usb-controller.kicad_sch')):
        raise ValueError("Artifact check failed: replay['candidate_schematic_sha256'] == sha(ROOT / 'cad/radio-usb-controller.kicad_sch')")
    fab = json.loads((ROOT / 'checks/fabrication-verification.json').read_text())
    if not (fab['source_pcb_sha256'] == sha(ROOT / 'cad/radio-usb-controller.kicad_pcb')):
        raise ValueError("Artifact check failed: fab['source_pcb_sha256'] == sha(ROOT / 'cad/radio-usb-controller.kicad_pcb')")
    if not (fab['BOM_components'] == 39 and fab['placements_SMT'] == 34):
        raise ValueError("Artifact check failed: fab['BOM_components'] == 39 and fab['placements_SMT'] == 34")
    for path, digest in fab['file_sha256'].items():
        if not (sha(ROOT / 'fabrication/R01.3' / path) == digest):
            raise ValueError("Artifact check failed: sha(ROOT / 'fabrication/R01.3' / path) == digest")
    files = fabrication_files(ROOT)
    if set(fab['file_sha256']) != set(files):
        raise ValueError('Fabrication report does not cover the complete file set')
    verify_archive(ROOT / 'fabrication/wici-controller-R01.3.zip', files)
    bound = ['cad/radio-usb-controller.kicad_sch', 'cad/radio-usb-controller.kicad_pcb',
             'cad/radio-usb-controller.kicad_pro', 'cad/radio-usb-controller.kicad_dru',
             'checks/erc-controller.json', 'checks/drc-controller.json',
             'checks/controller-revision.json', 'checks/mechanical-geometry.json',
             'checks/replay-verification.json', 'checks/fabrication-verification.json',
             'checks/stackup.json', 'assembly-parts.json', 'fabrication/wici-controller-R01.3.zip',
             'mechanika-1-do-1.pdf', 'connections.json', 'bom.csv']
    status = {
        'project': 'WICI',
        'revision': 'R01.3-controller-fabrication-2026-10-06',
        'manufacturing_release': 'HOLD',
        'scope': 'USB controller candidate plus private TI RF reference audit; not a complete working radio modem.',
        'controller': {
            'tool': 'KiCad 10.0.6', 'erc_date': erc['date'], 'drc_date': drc['date'],
            'erc_violations': erc_count, 'drc_violations': len(drc['violations']),
            'unconnected_items': len(drc['unconnected_items']), 'schematic_parity_issues': len(drc['schematic_parity']),
            'zone_refill': True, 'explicit_excluded_violations': 0,
            'erc_default_ignored_checks': erc['ignored_checks'],
            'drc_default_ignored_checks': drc['ignored_checks'],
            'review': 'Schematic, copper, assembly, actual exported Gerber copper/silkscreen/planes and 1:1 PDF rendered and inspected; no independent reviewer or physical specimen.',
            'requested_changes_report': 'checks/controller-revision.json',
            'replay_verification': 'checks/replay-verification.json',
            'fabrication_outputs': 'fabrication/wici-controller-R01.3.zip',
            'fabrication_verification': 'checks/fabrication-verification.json',
            'reference_stackup': 'JLC04161H-7628, nominal 1.6 mm',
            'power_bus_width_mm': 0.5,
            'inner_layer_track_count': 0,
            'mounting_holes': 4,
            'known_design_blockers': [
                'Y1 standby pin is tied to V3; oscillator alone can exceed the complete USB suspend budget. New electrical revision and full-modem qualification required.',
            ],
            'mechanical_fit': 'NOT TESTED',
            'mechanical_print': 'mechanika-1-do-1.pdf',
        },
        'rf_reference': {
            'source_connection_audit': summary,
            'imported_kicad_drc_violations': len(rf['violations']),
            'imported_kicad_unconnected_items': len(rf['unconnected_items']),
            'manufacturing_release': 'HOLD',
        },
        'not_verified': ['USB differential impedance and physical operation', 'complete modem USB power lifecycle and inrush', 'connector/switch mechanical fit',
                         'RF layout conversion', 'RF clock selection and full error budget',
                         'firmware', 'thermal behavior', 'transmitter spectrum', 'receiver sensitivity',
                         'range', 'qualified second-vendor implementation', 'PPTC voltage drop and thermal derating'],
        'sha256': {p: sha(ROOT / p) for p in bound},
    }
    if args.check:
        if json.loads((ROOT / 'checks/status.json').read_text()) != json.loads(json.dumps(status)):
            raise ValueError('Status hashes or findings are stale')
    else:
        (ROOT / 'checks/status.json').write_text(json.dumps(status, indent=2, ensure_ascii=False) + '\n')
    manifest = {str(p.relative_to(ROOT)): sha(p) for p in sorted(ROOT.rglob('*'))
                if p.is_file() and p.name != 'manifest.sha256.json' and 'reference-private' not in p.parts and p.name != '.DS_Store'
                and '__pycache__' not in p.parts and p.suffix not in ('.pyc', '.kicad_prl') and not p.name.endswith('.lck')}
    if args.check:
        if json.loads((ROOT / 'manifest.sha256.json').read_text()) != manifest:
            raise ValueError('Hardware manifest is stale')
    else:
        (ROOT / 'manifest.sha256.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(f'CAD checks passed; manufacturing HOLD retained; {len(manifest)} files hashed.')


if __name__ == '__main__':
    main()
