"""Reproduce design estimates; assumed efficiencies are not measured results."""

import json
import math
from pathlib import Path

from reference import fragment, encode_message


def hata_urban_loss_db(f_mhz: float, base_m: float, mobile_m: float, km: float) -> float:
    """Okumura-Hata, small or medium city; indicative outside its 30-200 m base height range."""
    mobile = (1.1 * math.log10(f_mhz) - 0.7) * mobile_m - (1.56 * math.log10(f_mhz) - 0.8)
    return (69.55 + 26.16 * math.log10(f_mhz) - 13.82 * math.log10(base_m) - mobile
            + (44.9 - 6.55 * math.log10(base_m)) * math.log10(km))


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
    request = [1, 0, "0" * 32, 65535, 4, 65535, "\\" * 64, '"' * 96, 2]
    f_mhz, tx_dbm, antenna_dbi, cable_db, sensitivity_dbm = 869.525, 13.0, 2.15, 1.0, -110.0
    link_gain_db = tx_dbm + 2 * antenna_dbi - 2 * cable_db
    urban = {f"base_{b:g}m_mobile_{m:g}m": hata_urban_loss_db(f_mhz, b, m, 1.0) for b, m in ((30, 1.5), (10, 1.5), (10, 3))}
    smallest_cycle_s = 13 * len(fragment(b"x", b"12345678")[0]) * 8 / 4800
    eeprom_pages, eeprom_endurance = 8192 // 32, 1_000_000
    result = {
        "assumptions": {"station_ac_w": ac_w, "conversion_efficiency_excluding_idle": efficiency,
                        "inverter_idle_w": idle_w, "diode_loss_w": diode_w,
                        "phone_count": 50, "phone_energy_each_wh": 5,
                        "phone_path_efficiency": 0.80, "battery_v": 12,
                        "battery_ah": 60, "usable_fraction_assumed": 0.50,
                        "reserve_fraction": 0.20, "mosfet_hot_resistance_factor": 1.7,
                        "hotplug_loop_resistance_assumed_ohm": loop_r},
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
                  "fresnel_radius_midpoint_1km_m": 17.32 * math.sqrt(0.5 * 0.5 / (f_mhz / 1000)),
                  "eeprom_writes_per_day_worst": 86400 / smallest_cycle_s,
                  "eeprom_years_worst_1m_cycles_256_pages": eeprom_pages * eeprom_endurance / (86400 / smallest_cycle_s) / 365,
                  "worst_request_content_bytes": len(encode_message(request))},
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
        "limits": ["No radio range measurement; Hata is used below its 30 m base height range", "No transformer leakage or PSU inrush model",
                   "No switching, magnetic or reactive current losses in voltage margin",
                   "No battery capacity measurement", "No thermal or electrical safety verification"],
    }
    if available_low_v <= required_low_v:
        raise ValueError("Insufficient estimated transformer headroom")
    if result["radio"]["worst_request_content_bytes"] > 480:
        raise ValueError("Application content limit exceeded")
    return result


if __name__ == "__main__":
    result = calculate()
    Path(__file__).with_name("wyniki.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
