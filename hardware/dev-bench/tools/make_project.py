# SPDX-License-Identifier: MIT
"""Write the KiCad project file and the explicit design rules of the carrier.

Rules are within common two-layer prototype capability (0.2 mm spacing,
0.25 mm tracks, 0.8/0.4 mm vias, 0.4 mm minimum hole); the fabricator's limits are confirmed in
przed-produkcja.md before an order.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME = 'plytka-nosna'
POWER = ['+3V3', '+3V3_RF', '+5V', '+3V3_DEVKIT', '+5V_DEVKIT', 'GND', 'BZ_P', 'BZ_N', '+5V_LCD', 'BST_SW']


def netclass(name, track, priority):
    return {'bus_width': 12, 'clearance': 0.2, 'diff_pair_gap': 0.25, 'diff_pair_via_gap': 0.25,
            'diff_pair_width': 0.2, 'line_style': 0, 'microvia_diameter': 0.3, 'microvia_drill': 0.1,
            'name': name, 'pcb_color': 'rgba(0, 0, 0, 0.000)', 'priority': priority,
            'schematic_color': 'rgba(0, 0, 0, 0.000)', 'track_width': track, 'tuning_profile': '',
            'via_diameter': 0.8, 'via_drill': 0.4, 'wire_width': 6}


def main():
    pro = {
        'board': {'design_settings': {
            'defaults': {'board_outline_line_width': 0.05, 'copper_line_width': 0.2,
                         'silk_line_width': 0.12, 'silk_text_size_h': 1.0, 'silk_text_size_v': 1.0,
                         'silk_text_thickness': 0.15},
            'rules': {'min_clearance': 0.2, 'min_copper_edge_clearance': 0.5, 'min_hole_clearance': 0.3,
                      'min_hole_to_hole': 0.25, 'min_through_hole_diameter': 0.4, 'min_track_width': 0.18,
                      'min_via_annular_width': 0.15, 'min_via_diameter': 0.8, 'min_silk_clearance': 0.0,
                      'min_text_height': 0.8, 'min_text_thickness': 0.12},
            # KiCad ignores a missing courtyard by default; mechanics drives this board.
            'rule_severities': {'missing_courtyard': 'error'},
            'track_widths': [0.0, 0.25, 0.4, 0.6], 'via_dimensions': [{'diameter': 0.0, 'drill': 0.0},
                                                                    {'diameter': 0.8, 'drill': 0.4}]}},
        'boards': [], 'libraries': {'pinned_footprint_libs': [], 'pinned_symbol_libs': []},
        'meta': {'filename': NAME + '.kicad_pro', 'version': 3},
        'net_settings': {'classes': [netclass('Default', 0.25, 2147483647), netclass('Power', 0.4, 0)],
                         'meta': {'version': 5}, 'net_colors': None, 'netclass_assignments': None,
                         'netclass_patterns': [{'netclass': 'Power', 'pattern': '/' + n} for n in POWER]},
        'pcbnew': {'page_layout_descr_file': ''},
        'schematic': {'page_layout_descr_file': ''},
        'sheets': [], 'text_variables': {},
    }
    (ROOT / 'cad' / (NAME + '.kicad_pro')).write_text(json.dumps(pro, indent=2) + '\n')
    (ROOT / 'cad' / (NAME + '.kicad_dru')).write_text('''(version 1)
(rule "N1 copper spacing" (constraint clearance (min 0.2mm)))
(rule "N1 track width" (constraint track_width (min 0.18mm)))
(rule "N1 via diameter" (constraint via_diameter (min 0.8mm)))
(rule "N1 finished hole" (constraint hole_size (min 0.4mm)))
(rule "N1 annular ring" (constraint annular_width (min 0.15mm)))
(rule "N1 copper to edge" (constraint edge_clearance (min 0.5mm)))
(rule "N1 copper to hole" (constraint hole_clearance (min 0.3mm)))
(rule "N1 thermal spokes" (constraint min_resolved_spokes 1))
(rule "N1 power tracks" (condition "A.NetClass == 'Power' && A.Type == 'track' && !A.intersectsCourtyard('J7')") (constraint track_width (min 0.3mm)))
(rule "N1 power tracks at J7" (condition "A.NetClass == 'Power' && A.Type == 'track' && A.intersectsCourtyard('J7')") (constraint track_width (min 0.24mm)))
''')
    print('project and rules written')


if __name__ == '__main__':
    main()
