"""Reproduce design estimates; assumed efficiencies are not measured results."""

import json
import math
from pathlib import Path

from reference import MAX_CONTENT, fragment, encode_message


def hata_urban_loss_db(f_mhz: float, base_m: float, mobile_m: float, km: float) -> float:
    """Okumura-Hata, small or medium city; indicative outside its 30-200 m base height range."""
    mobile = (1.1 * math.log10(f_mhz) - 0.7) * mobile_m - (1.56 * math.log10(f_mhz) - 0.8)
    return (69.55 + 26.16 * math.log10(f_mhz) - 13.82 * math.log10(base_m) - mobile
            + (44.9 - 6.55 * math.log10(base_m)) * math.log10(km))


def p1_tx_seconds(datagram_bytes: int, bit_rate: float = 4800, ramp_ms: float = 0.0) -> float:
    """P1 airtime of one datagram burst plus ramp/turnaround per fragment; excludes CCA and retries."""
    fragments = math.ceil(datagram_bytes / 86)
    return 8 * (datagram_bytes + 29 * fragments) / bit_rate + fragments * ramp_ms / 1000


def lxmf_packet_bytes(content_bytes: int) -> int:
    """Reticulum packet on the last hop for an opportunistic LXMF message (reference versions)."""
    plaintext = 80 + 19 + content_bytes
    return 19 + 32 + 16 + 16 * math.ceil((plaintext + 1) / 16) + 32


STATION = {"rail_v": 3.3, "rx_ma": 22.0, "tcxo_ma": 2.0, "tx_ma_13dbm": 45.0,
           "tx_fraction": 1 / 13, "lcd_5v_rail_ma": 0.5, "fram_buttons_supervisor_ma": 0.5,
           "front_light_ma": 15.0, "front_light_duty": 0.5 / 24,
           "alarm_led_ma": 5.0, "alarm_led_duty": 0.01, "buzzer_ma": 20.0, "buzzer_duty": 0.0025,
           "aa_vsys_v": 6.0, "aa_rail_efficiency": 0.85,
           "battery_vsys_v": 12.8, "battery_rail_efficiency": 0.80}
# Input-side quiescent currents per source; the converter Iq is inside its efficiency and is not added again.
INPUT_SIDE_MA = {"aa": {"ltc4412": 0.011, "tps3710": 0.006, "ltc2954": 0.006, "dividers": 0.01},
                 "12v": {"lm74800": 0.4, "uv_latch": 0.02, "tps3710": 0.006, "ltc2954": 0.006, "dividers": 0.01}}
SOURCES = {"aa": ("aa_vsys_v", "aa_rail_efficiency"), "12v": ("battery_vsys_v", "battery_rail_efficiency")}


def station_rail_ma(mcu_ma: float) -> float:
    """Average 3V3 rail current: always-on RX with TCXO, TX at the 1/13 debt limit, LCD, FRAM, light, alarm LED, buzzer."""
    c = STATION
    return (mcu_ma + c["rx_ma"] + c["tcxo_ma"] + c["tx_fraction"] * c["tx_ma_13dbm"] + c["lcd_5v_rail_ma"]
            + c["fram_buttons_supervisor_ma"] + c["front_light_ma"] * c["front_light_duty"]
            + c["alarm_led_ma"] * c["alarm_led_duty"] + c["buzzer_ma"] * c["buzzer_duty"])


def station_power_w(mcu_ma: float, source: str = "aa") -> float:
    """Station input power from one source: 3V3 rail through the converter plus that source's input-side currents."""
    c = STATION
    vsys_key, efficiency_key = SOURCES[source]
    return (c["rail_v"] * station_rail_ma(mcu_ma) / 1000 / c[efficiency_key]
            + c[vsys_key] * sum(INPUT_SIDE_MA[source].values()) / 1000)


def calculate() -> dict:
    """Calculate prototype margins with explicit inputs from the design."""
    ac_w, efficiency, idle_w, diode_w = 35.0, 0.85, 8.0, 1.7
    station_wh = 24 * (ac_w / efficiency + idle_w + diode_w)
    phones_wh = 50 * 5 / 0.80
    usable_battery_wh = 12 * 60 * 0.50
    frames = fragment(b"x" * 600, b"12345678")
    tx_s = sum(len(f) * 8 / 4800 for f in frames)
    primary_r, secondary_r, turns_ratio = 0.012, 25.0, 42
    high_i = 150 / 230
    low_i = high_i * turns_ratio
    mosfet_hot_r = 0.00305 * 1.7
    required_low_v = 230 / turns_ratio + low_i * primary_r + high_i * secondary_r / turns_ratio + low_i * 2 * mosfet_hot_r
    bus_v, modulation_max = 10.6, 0.9
    available_low_v = bus_v * modulation_max / math.sqrt(2)
    c_bus, delta_v, loop_r = 0.0176, 5.5, 0.04
    request = [1, 0, "0" * 32, 65535, 4, 65535, "x" * 64, "x" * 96, 2]
    f_mhz, tx_dbm, antenna_dbi, cable_db, sensitivity_dbm = 869.525, 13.0, 2.15, 1.0, -110.0
    fixed_cable_db = 2.5  # fixed installation: outdoor cable, GDT, gland, adapters and indoor cable (e.g. 6 m LMR-240)
    frontend_loss_db, ramp_ms_assumed = 3.0, 2.0
    link_gain_db = tx_dbm + 2 * antenna_dbi - 2 * cable_db
    urban = {f"base_{b:g}m_mobile_{m:g}m": hata_urban_loss_db(f_mhz, b, m, 1.0) for b, m in ((30, 1.5), (10, 1.5), (10, 3))}
    smallest_cycle_s = 13 * len(fragment(b"x", b"12345678")[0]) * 8 / 4800
    eeprom_pages, eeprom_endurance = 8192 // 32, 1_000_000
    reserve, aa_set_wh, battery_wh = 1.2, 4 * 4.5 * 0.8, usable_battery_wh
    level1 = {}
    for name, mcu_ma in (("nrf52840", 3.0), ("esp32_s3_30ma", 30.0), ("esp32_s3_45ma", 45.0), ("esp32_s3_60ma", 60.0)):
        power_w = station_power_w(mcu_ma)
        day_wh = 24 * power_w * reserve
        power_12v_w = station_power_w(mcu_ma, "12v")
        day_12v_wh = 24 * power_12v_w * reserve
        level1[name] = {"mcu_ma_assumed": mcu_ma, "rail_ma": station_rail_ma(mcu_ma), "input_w": power_w,
                        "wh_24h_with_reserve": day_wh, "aa_set_hours": aa_set_wh / day_wh * 24,
                        "input_w_12v": power_12v_w, "wh_24h_with_reserve_12v": day_12v_wh,
                        "battery_12v_days": battery_wh / day_12v_wh,
                        "battery_12v_hours": battery_wh / day_12v_wh * 24}
    # Highest average 3V3 current that still meets W23 (48 h on the AA set, with reserve).
    w23_input_w = aa_set_wh / 48 / reserve
    w23_rail_ma = ((w23_input_w - STATION["aa_vsys_v"] * sum(INPUT_SIDE_MA["aa"].values()) / 1000)
                   * STATION["aa_rail_efficiency"] / STATION["rail_v"] * 1000)
    # Hold-up after the VSYS comparator (3.4 V) until the converter stops (2.7 V): C >= 2 P t / (V1^2 - V2^2).
    # Load: TX 13 dBm, active MCU (worst variant), TCXO, LCD and FRAM; light, LED and buzzer are switched off first.
    holdup_v1, holdup_v2, holdup_t_s, holdup_selected_uf = 3.4, 2.7, 0.002, 470.0
    holdup_rail_ma = STATION["tx_ma_13dbm"] + 60.0 + STATION["tcxo_ma"] + STATION["lcd_5v_rail_ma"] + STATION["fram_buttons_supervisor_ma"]
    holdup_w = STATION["rail_v"] * holdup_rail_ma / 1000 / STATION["aa_rail_efficiency"]
    holdup_c_uf = 2 * holdup_w * holdup_t_s / (holdup_v1**2 - holdup_v2**2) * 1e6
    # TCXO budget until the next yearly check (ppm), linear sum against the P1 limit of 2.5 ppm.
    tcxo_ppm = {"temperature": 0.5, "calibration": 0.3, "supply_and_load": 0.2, "ageing_to_next_check": 1.0}
    host = {}
    for host_ac_w in (15.0, 35.0, 60.0):
        input_w = host_ac_w / efficiency + idle_w + diode_w
        host[f"{host_ac_w:g}w_ac"] = {"input_w": input_w, "wh_24h_with_reserve": 24 * input_w * reserve,
                                      "battery_equivalents": math.ceil(24 * input_w * reserve / battery_wh)}
    laptop_relay_wh = (host["15w_ac"]["wh_24h_with_reserve"], host["60w_ac"]["wh_24h_with_reserve"])
    mid = "0" * 32
    location = "ul. Kasztanowa 17A, wejście od podwórza, piwnica"
    sa1 = {
        "typical_request": [1, 0, mid, 0, 2, 8, location, "Brak wody pitnej i leków na nadciśnienie, dwie osoby starsze, dzieci", 1],
        "max_fields_request": [1, 0, mid, 65535, 4, 65535, "x" * 64, "x" * 96, 2],
        "button_request": [1, 0, mid, 0, 2, 999, location, "", 2],
        "worst_button_request": [1, 0, mid, 65535, 4, 999, "x" * 64, "x" * 96, 2],  # preset phrase <= 96 B
        "received": [1, 1, mid, 65535, 1, 1],
        "max_status": [1, 2, mid, 65535, 2147483647, 6],
        "max_bulletin": [1, 4, mid, 2147483647, "x" * 192],
        "worst_reply": [1, 3, mid, 65535, 2147483647, "x" * 96],
    }
    opportunistic_content_estimate, link_content_estimate = 284, 316
    sizes = {k: len(encode_message(v)) for k, v in sa1.items()}
    relay_packets = {"typical_request": lxmf_packet_bytes(sizes["typical_request"]),
                     "max_fields_request": lxmf_packet_bytes(sizes["max_fields_request"]),
                     "received": lxmf_packet_bytes(sizes["received"]), "packet_proof": 83}
    relay_cycle = {k: 13 * p1_tx_seconds(v) for k, v in relay_packets.items()}
    per_request = [relay_cycle[r] + relay_cycle["received"] + 2 * relay_cycle["packet_proof"]
                   for r in ("typical_request", "max_fields_request")]
    slow_per_request = [13 * (p1_tx_seconds(relay_packets[r], 1200) + p1_tx_seconds(relay_packets["received"], 1200)
                              + 2 * p1_tx_seconds(83, 1200)) for r in ("typical_request", "max_fields_request")]
    collinear_dbi = 5.5
    # Network capacity without losses at the P1 debt limit (cycle 13t per datagram and node). A station reaches the
    # OSP through the relay next to it; packets sent by the OSP towards the relay carry a 16 B transport id.
    transport_id = 16
    status_packet = lxmf_packet_bytes(sizes["max_status"])
    capacity = {}
    for r in ("max_fields_request", "typical_request"):
        osp_tx = [83, relay_packets["received"] + transport_id] + 2 * [status_packet + transport_id]
        relay_tx = [relay_packets[r], 83, relay_packets["received"]] + 2 * [status_packet] + 3 * [83]
        osp_s = sum(13 * p1_tx_seconds(b) for b in osp_tx)
        relay_s = sum(13 * p1_tx_seconds(b) for b in relay_tx)
        capacity[r] = {"osp_tx_packets_bytes": osp_tx, "osp_s_per_request": osp_s, "osp_requests_per_h": 3600 / osp_s,
                       "relay_tx_packets_bytes": relay_tx, "relay_s_per_request": relay_s,
                       "relay_requests_per_h": 3600 / relay_s}
    bulletin_packet = lxmf_packet_bytes(sizes["max_bulletin"]) + transport_id
    bulletin_s = 13 * p1_tx_seconds(bulletin_packet)
    # LXMF retry spacing for opportunistic messages (A2): max(60 s, 2 x hops x 13 x TX of the largest datagram
    # + current silence debt + P1 queue drain). Largest own datagram: SA1 limit 256 B on the first hop.
    largest_own_datagram = lxmf_packet_bytes(MAX_CONTENT) + transport_id
    largest_cycle_s = 13 * p1_tx_seconds(largest_own_datagram)
    worst_debt_s = 12 * p1_tx_seconds(600)
    full_queue_s = 4 * 13 * p1_tx_seconds(600)
    retry = {"largest_own_datagram_bytes": largest_own_datagram, "largest_datagram_cycle_s": largest_cycle_s,
             "floor_s": 60.0, "worst_debt_s": worst_debt_s, "full_p1_queue_4x600b_s": full_queue_s}
    for hops in (1, 2):
        retry[f"{hops}_hop_round_trip_s"] = 2 * hops * largest_cycle_s
        retry[f"{hops}_hop_min_interval_empty_network_s"] = max(60.0, 2 * hops * largest_cycle_s)
        retry[f"{hops}_hop_min_interval_worst_debt_full_queue_s"] = max(60.0, 2 * hops * largest_cycle_s
                                                                        + worst_debt_s + full_queue_s)
    fixed_gain_db = tx_dbm + 2 * antenna_dbi - 2 * fixed_cable_db
    # FRAM occupancy by role (oprogramowanie.md, "Pamięć FRAM według roli"); conservative fixed-size slots.
    # Every record: header 16 B (number, type, length, version) + AEAD tag 16 B. Sizes are assumptions, not a layout.
    fram_record_overhead = 16 + 16
    fram_b = {"intent_slot": MAX_CONTENT + 40 + fram_record_overhead,  # + destination, id/revision/event, state, timers
              "mailbox_slot": MAX_CONTENT + 32 + fram_record_overhead,  # + sender, receive time, state
              "route_identity_entry": 64 + 16 + 32 + 170 + fram_record_overhead,  # key, hash, path, cached announce
              "receipt_key_entry": 48, "event_log": 32 * 1024, "uptime_and_silence_debt": 1024,
              "station_card_entry": 64 + 16 + 16 + 24 + fram_record_overhead}  # key, address hash, name, state/time
    fram_counts = {"station": {"intents": 128, "mailbox": 128, "incoming": 0, "routes": 256, "receipt_keys": 256,
                               "station_cards": 0},
                   "osp": {"intents": 512, "mailbox": 0, "incoming": 128, "routes": 256, "receipt_keys": 1024,
                           "station_cards": 256}}
    fram_size_kib = 512  # 4 Mbit in every station (oprogramowanie.md)
    fram_kib = {}
    for role, n in fram_counts.items():
        parts = {"outgoing_queue": n["intents"] * fram_b["intent_slot"],
                 "mailbox": n["mailbox"] * fram_b["mailbox_slot"],
                 "incoming": n["incoming"] * fram_b["intent_slot"],
                 "routes_identities_announces": n["routes"] * fram_b["route_identity_entry"],
                 "highest_event_and_receipt_keys": n["receipt_keys"] * fram_b["receipt_key_entry"],
                 "station_cards": n["station_cards"] * fram_b["station_card_entry"],
                 "event_log": fram_b["event_log"], "uptime_and_silence_debt": fram_b["uptime_and_silence_debt"]}
        total = sum(parts.values())
        fram_kib[role] = {"parts_kib": {k: v / 1024 for k, v in parts.items()}, "total_kib": total / 1024,
                          "fits_256_kib": total <= 256 * 1024, "fits_fram": total <= fram_size_kib * 1024,
                          "occupancy_of_fram": total / (fram_size_kib * 1024),
                          "occupancy_of_256_kib": total / (256 * 1024)}
    # Station RAM for the stack tables (oprogramowanie.md, "Pojemności stosu"): reference layout keeps full 32 B
    # packet hashes and whole route entries in RAM; the specified layout keeps 8 B hashes and a route index.
    ram_kib = {"nrf52840_total": 256,
               "hashlist_4096_full_32b": 4096 * 32 / 1024, "hashlist_4096_truncated_8b": 4096 * 8 / 1024,
               "routes_256_full_in_ram": 256 * fram_b["route_identity_entry"] / 1024,
               "route_index_256x16b": 256 * 16 / 1024}
    ram_kib["reference_layout_kib"] = ram_kib["hashlist_4096_full_32b"] + ram_kib["routes_256_full_in_ram"]
    ram_kib["specified_layout_kib"] = ram_kib["hashlist_4096_truncated_8b"] + ram_kib["route_index_256x16b"]
    ram_kib["reference_layout_share_of_nrf52840"] = ram_kib["reference_layout_kib"] / 256
    ram_kib["specified_layout_share_of_nrf52840"] = ram_kib["specified_layout_kib"] / 256
    # Cold network start: every transport station rebroadcasts each announce once (no losses), and the P1
    # interface limits announces to a share of TX time. Announce = 19 B header + cached announce, +16 B transport id.
    announce_cap = 0.02
    announce_bytes = 19 + 170 + transport_id
    announce_tx_s = p1_tx_seconds(announce_bytes)
    cold_start = {"announce_bytes": announce_bytes, "announce_tx_s": announce_tx_s,
                  "announce_cap_share_of_tx": announce_cap}
    for n in (10, 30, 50):
        cold_start[f"{n}_stations"] = {
            "network_announce_transmissions": n * n,
            "channel_airtime_min_single_collision_domain": n * n * announce_tx_s / 60,
            "per_station_tx_plus_quiet_min": n * 13 * announce_tx_s / 60,
            "per_hop_drain_at_cap_min": n * announce_tx_s / announce_cap / 60}
    result = {
        "assumptions": {"station_ac_w": ac_w, "conversion_efficiency_excluding_idle": efficiency,
                        "inverter_idle_w": idle_w, "diode_loss_w": diode_w,
                        "phone_count": 50, "phone_energy_each_wh": 5,
                        "phone_path_efficiency": 0.80, "battery_v": 12,
                        "battery_ah": 60, "usable_fraction_assumed": 0.50,
                        "reserve_fraction": 0.20, "mosfet_hot_resistance_factor": 1.7,
                        "hotplug_loop_resistance_assumed_ohm": loop_r},
        "station_level1": {"assumptions": {**STATION, "input_side_ma": INPUT_SIDE_MA,
                                           "input_side_ma_total": {k: sum(v.values()) for k, v in INPUT_SIDE_MA.items()},
                                           "reserve_fraction": 0.20,
                                           "aa_set_usable_wh": aa_set_wh, "aa_cell_wh": 4.5, "aa_usable_fraction": 0.8},
                           "wh_24h_with_reserve_range": [min(min(v["wh_24h_with_reserve"], v["wh_24h_with_reserve_12v"])
                                                             for v in level1.values()),
                                                         max(max(v["wh_24h_with_reserve"], v["wh_24h_with_reserve_12v"])
                                                             for v in level1.values())],
                           "holdup": {"comparator_v": holdup_v1, "converter_stop_v": holdup_v2, "hold_s": holdup_t_s,
                                      "load_rail_ma": holdup_rail_ma, "load_w": holdup_w,
                                      "required_uf": holdup_c_uf, "selected_uf": holdup_selected_uf,
                                      "selected_to_required_ratio": holdup_selected_uf / holdup_c_uf},
                           "variants": level1,
                           "fixed_relay_buffer_psu_13_8v": {
                               "note": "Mains failure: station runs from the buffer battery through the 12 V input",
                               "battery_v": 12, "usable_fraction_assumed": 0.5,
                               "hours": {f"{ah}ah": {name: ah * 12 * 0.5 / level1[name]["wh_24h_with_reserve_12v"] * 24
                                                     for name in ("nrf52840", "esp32_s3_60ma")} for ah in (7, 17)}},
                           "w23_max_rail_ma_on_aa": w23_rail_ma,
                           "w23_max_mcu_ma_on_aa": w23_rail_ma - station_rail_ma(0.0),
                           "laptop_relay_wh_24h_with_reserve": list(laptop_relay_wh),
                           "laptop_relay_to_station_ratio": [laptop_relay_wh[0] / level1["esp32_s3_60ma"]["wh_24h_with_reserve"],
                                                             laptop_relay_wh[1] / level1["nrf52840"]["wh_24h_with_reserve"]]},
        "level3_pools": {"laptop_router_wh_with_reserve": station_wh * reserve,
                         "laptop_router_batteries": math.ceil(station_wh * reserve / battery_wh),
                         "phones_wh_with_reserve": phones_wh * reserve,
                         "phones_batteries": math.ceil(phones_wh * reserve / battery_wh),
                         "separate_pool_batteries": math.ceil(station_wh * reserve / battery_wh) + math.ceil(phones_wh * reserve / battery_wh),
                         "lead_acid_capacity_factor_0c_assumed": 0.8,
                         "batteries_at_0c_combined": math.ceil((station_wh + phones_wh) * reserve / (battery_wh * 0.8)),
                         "host_sweep": host},
        "sa1_sizes": {"content_bytes": sizes, "opportunistic_content_estimate": opportunistic_content_estimate,
                      "link_content_estimate": link_content_estimate,
                      "fits_one_opportunistic_packet": {k: v <= opportunistic_content_estimate for k, v in sizes.items()}},
        "relay_w10": {"packets_bytes": relay_packets, "tx_plus_quiet_s": relay_cycle,
                      "per_request_s": per_request, "fifty_requests_min": [50 * t / 60 for t in per_request],
                      "per_retry_s": [relay_cycle["typical_request"], relay_cycle["max_fields_request"]],
                      "fifty_requests_min_at_1200_bit_s": [50 * t / 60 for t in slow_per_request],
                      "status_packet_bytes": status_packet,
                      "fifty_requests_with_two_status_min": 50 * capacity["max_fields_request"]["relay_s_per_request"] / 60,
                      "quiet_10t_throughput_gain": 13 / 11 - 1,
                      "p1_tx_plus_quiet_s": {f"{b}b": 13 * p1_tx_seconds(b) for b in (100, 250, 500, 600)},
                      "ramp_ms_per_fragment_assumed": ramp_ms_assumed,
                      "p1_tx_plus_quiet_s_with_ramp": {f"{b}b": 13 * p1_tx_seconds(b, ramp_ms=ramp_ms_assumed)
                                                       for b in (100, 250, 500, 600)}},
        "network_capacity": {"note": "No losses, collisions, CCA, cold routes or retries; per node at the P1 debt limit",
                             "per_request": capacity,
                             "osp_requests_per_h": capacity["max_fields_request"]["osp_requests_per_h"],
                             "relay_before_osp_requests_per_h": capacity["max_fields_request"]["relay_requests_per_h"],
                             "bulletin_packet_bytes": bulletin_packet, "bulletin_s_per_station": bulletin_s,
                             "bulletin_osp_tx_min": {f"{n}_stations": n * bulletin_s / 60 for n in (10, 30, 50)},
                             "test_window_s_per_station": 50,
                             "test_window_min": {f"{n}_stations": 50 * n / 60 for n in (10, 30, 50)}},
        "lxmf_retry": retry,
        "fram_by_role": {"record_bytes_assumed": fram_b, "counts": fram_counts, "roles": fram_kib,
                         "fram_stacja_kib": fram_kib["station"]["total_kib"], "fram_osp_kib": fram_kib["osp"]["total_kib"],
                         "fram_size_kib": fram_size_kib},
        "station_ram_kib": ram_kib,
        "cold_start_announces": cold_start,
        "tcxo_budget_ppm": {**tcxo_ppm, "linear_sum": sum(tcxo_ppm.values()),
                            "root_sum_square": math.sqrt(sum(v**2 for v in tcxo_ppm.values())),
                            "p1_limit": 2.5, "linear_sum_hz_at_carrier": sum(tcxo_ppm.values()) * f_mhz,
                            "p1_limit_hz_at_carrier": 2.5 * f_mhz,
                            "mutual_offset_both_at_limit_hz": 2 * 2.5 * f_mhz},
        "energy": {"station_24h_wh": station_wh, "phones_wh": phones_wh,
                   "total_wh": station_wh + phones_wh,
                   "total_with_reserve_wh": (station_wh + phones_wh) * 1.2,
                   "usable_wh_per_assumed_battery": usable_battery_wh,
                   "battery_equivalents_rounded_up": math.ceil((station_wh + phones_wh) * 1.2 / usable_battery_wh)},
        "radio": {"max_fragments": len(frames), "max_datagram_air_bytes": sum(map(len, frames)),
                  "tx_seconds_excluding_ramp": tx_s, "quiet_seconds": 12 * tx_s,
                  "cycle_seconds": 13 * tx_s, "steady_tx_fraction": 1 / 13,
                  "ideal_payload_bytes_hour_for_600b_datagrams": 600 * 3600 / (13 * tx_s),
                  "free_space_loss_1km_db": 32.44 + 20 * math.log10(869.525),
                  "link_gain_excluding_path_db": link_gain_db,
                  "free_space_margin_1km_db": link_gain_db - (32.44 + 20 * math.log10(f_mhz)) - sensitivity_dbm,
                  "hata_urban_loss_1km_db": urban,
                  "hata_urban_margin_1km_db": {k: link_gain_db - v - sensitivity_dbm for k, v in urban.items()},
                  "sensitivity_target_at_connector_dbm": sensitivity_dbm,
                  "frontend_loss_assumed_db": frontend_loss_db,
                  "chip_sensitivity_needed_for_target_dbm": sensitivity_dbm - frontend_loss_db,
                  "hata_urban_margin_1km_if_chip_meets_target_only_db": {
                      k: link_gain_db - v - sensitivity_dbm - frontend_loss_db for k, v in urban.items()},
                  "fresnel_radius_midpoint_1km_m": 17.32 * math.sqrt(0.5 * 0.5 / (f_mhz / 1000)),
                  "eeprom_writes_per_day_worst": 86400 / smallest_cycle_s,
                  "eeprom_years_worst_1m_cycles_256_pages": eeprom_pages * eeprom_endurance / (86400 / smallest_cycle_s) / 365,
                  "worst_request_content_bytes": len(encode_message(request)),
                  "erp_dipole_dbm": tx_dbm - cable_db + antenna_dbi - 2.15,
                  "erp_collinear_dbm": tx_dbm - cable_db + collinear_dbi - 2.15,
                  "erp_limit_dbm": 27.0,
                  "collinear_gain_both_ends_db": 2 * (collinear_dbi - antenna_dbi),
                  "hata_urban_margin_1km_collinear_db": {k: link_gain_db + 2 * (collinear_dbi - antenna_dbi) - v - sensitivity_dbm
                                                         for k, v in urban.items()},
                  "fade_margin_for_99_of_100_assumed_db": 10.0,
                  "fram_years_worst_1e13_cycles": 1e13 / (86400 / smallest_cycle_s) / 365,
                  "fixed_installation": {
                      "cable_and_fittings_loss_each_end_db": fixed_cable_db,
                      "link_gain_excluding_path_db": fixed_gain_db,
                      "free_space_margin_1km_db": fixed_gain_db - (32.44 + 20 * math.log10(f_mhz)) - sensitivity_dbm,
                      "hata_urban_margin_1km_db": {k: fixed_gain_db - v - sensitivity_dbm for k, v in urban.items()},
                      "hata_urban_margin_1km_if_chip_meets_target_only_db": {
                          k: fixed_gain_db - v - sensitivity_dbm - frontend_loss_db for k, v in urban.items()},
                      "hata_urban_margin_1km_collinear_db": {
                          k: fixed_gain_db + 2 * (collinear_dbi - antenna_dbi) - v - sensitivity_dbm for k, v in urban.items()},
                      "erp_dipole_dbm": tx_dbm - fixed_cable_db + antenna_dbi - 2.15,
                      "erp_collinear_dbm": tx_dbm - fixed_cable_db + collinear_dbi - 2.15}},
        "charger": {"nominal_feedback_v": 1.23 * (1 + 3.16),
                    "nominal_crowbar_v": 2.495 * (1 + 9.31 / 8.20),
                    "untrimmed_max_output_v": 1.267 * (1 + 3.16),
                    "crowbar_min_minus_untrimmed_max_v": 5.30 - 1.267 * (1 + 3.16),
                    "input_current_at_60w_80percent_11_5v_a": 60 / 0.8 / 11.5,
                    "inductor_ripple_at_16v_min_frequency_a": (16 - 5.1168) * (5.1168 / 16) / (68e-6 * 127e3)},
        "inverter": {"secondary_current_150w_resistive_a": high_i,
                     "primary_current_ideal_a": low_i,
                     "required_primary_rms_v_resistive_estimate": required_low_v,
                     "available_primary_rms_v": available_low_v,
                     "rms_voltage_margin_v": available_low_v - required_low_v,
                     "transformer_copper_loss_w_estimate": low_i**2 * primary_r + high_i**2 * secondary_r,
                     "bridge_conduction_loss_w_estimate": low_i**2 * 2 * mosfet_hot_r,
                     "core_flux_at_230v_t": 230 / (4.44 * 50 * 840 * 0.0014),
                     "filter_undamped_resonance_hz": 1 / (2 * math.pi * math.sqrt(0.01 * 1e-6)),
                     "bleeder_325v_to_50v_seconds": 300e3 * 1.47e-6 * math.log(325 / 50)},
        "hotplug": {"initial_current_a_model": delta_v / loop_r,
                    "decay_time_constant_s": loop_r * c_bus,
                    "i_squared_t_a2s_model": (delta_v / loop_r)**2 * loop_r * c_bus / 2},
        "limits": ["No radio range measurement; Hata is used below its 30 m base height range",
                   "Station currents are catalogue assumptions, not measurements; AA capacity depends on load and temperature",
                   "AA hours assume Li-FeS2 cells; alkaline and NiMH lose much of their capacity at -10 to -20 C",
                   "Receiver front-end loss and per-fragment ramp time are assumptions until measured in T4",
                   "LXMF packet sizes follow the reference Reticulum e40191b and LXMF c3ff2d6 structure, not captured traffic",
                   "No transformer leakage or PSU inrush model",
                   "No switching, magnetic or reactive current losses in voltage margin",
                   "No battery capacity measurement",
                   "Network capacity is per node at the debt limit; shared channel, hidden nodes and retries reduce it",
            "Cold-start announces: one rebroadcast per announce and station, no path requests, losses or announce suppression",
                   "Fixed installation loss of 2.5 dB per end is an assumption until the installed cable is measured", "No thermal or electrical safety verification"],
    }
    if available_low_v <= required_low_v:
        raise ValueError("Insufficient estimated transformer headroom")
    if max(sizes.values()) > MAX_CONTENT:
        raise ValueError("Application content limit exceeded")
    return result


if __name__ == "__main__":
    result = calculate()
    Path(__file__).with_name("wyniki.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
