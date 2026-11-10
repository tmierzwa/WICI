# SPDX-License-Identifier: MIT
"""Single source of the preliminary v2 schematic: parts, physical pins and nets.

v2 = the v1.1 carrier (hardware/dev-bench) without the TI, ST and Nordic sockets, with the Wio SX1262 on
headers, a USB-C socket without VBUS and the power path from the AA cells and 12 V of
docs/spec/elektronika.md ("Zasilanie stacji") with values from hardware/r02/zasilanie.md. Parts kept
from v1.1 keep their references. No placement yet: the outline waits for the enclosure.
"""

R0805 = 'Resistor_SMD:R_0805_2012Metric'
C0805 = 'Capacitor_SMD:C_0805_2012Metric'
C1210 = 'Capacitor_SMD:C_1210_3225Metric'
SOT23 = 'Package_TO_SOT_SMD:SOT-23'
XH2 = 'Connector_JST:JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical'

PARTS = []

# Part in the JLC/LCSC catalogue for each design part: design MPN -> (LCSC number, manufacturer, MPN); None keeps the
# design manufacturer and MPN. Checked in the JLC parts catalogue on 2026-11-10 (class and stock in the comments).
# Rule: a Basic or Preferred part in stock where one has the same value, tolerance, voltage, dielectric and
# package; otherwise the design part itself as Extended. Generic passives take the Basic part, so that a larger
# batch does not hang on one manufacturer; the parts whose data-sheet figures the design relies on (leakage,
# 0.1% dividers, 100 V, pulse rating) stay with the named manufacturer.
JLC = {
    # 0805 1% thick film, 125 mW
    'RC0805FR-0733RL': ('C17634', 'UNI-ROYAL', '0805W8F330JT5E'),       # Basic, 1.2 M
    'RC0805FR-0710KL': ('C17414', 'UNI-ROYAL', '0805W8F1002T5E'),       # Basic, 49 M
    'RC0805FR-071KL': ('C17513', 'UNI-ROYAL', '0805W8F1001T5E'),        # Basic, 40 M
    'RC0805FR-075K1L': ('C27834', 'UNI-ROYAL', '0805W8F5101T5E'),       # Basic, 2.5 M
    'RC0805FR-07100KL': ('C149504', 'UNI-ROYAL', '0805W8F1003T5E'),     # Basic, 2.5 M
    'RC0805FR-071ML': ('C17514', 'UNI-ROYAL', '0805W8F1004T5E'),        # Basic, 1.6 M
    'RC0805FR-07470KL': ('C17709', 'UNI-ROYAL', '0805W8F4703T5E'),      # Basic, 330 k
    'RC0805FR-07220KL': ('C17556', 'UNI-ROYAL', '0805W8F2203T5E'),      # Basic, 490 k
    'RC0805FR-0720KL': ('C4328', 'UNI-ROYAL', '0805W8F2002T5E'),        # Basic, 2.0 M
    'RC0805FR-07309KL': ('C57148', 'UNI-ROYAL', '0805W8F3093T5E'),      # Extended, 10 k (Yageo: 681)
    'RC0805FR-07432KL': ('C17693', 'UNI-ROYAL', '0805W8F4323T5E'),      # Extended, 236 (Yageo: 34); no 432k in quantity
    'RC0805FR-0747K5L': ('C137519', None, None),                        # Extended, 5.4 k
    'RC1206FR-0722RL': ('C17958', 'UNI-ROYAL', '1206W4F220JT5E'),       # Basic, 590 k; 1206 250 mW
    'RC2512FK-071RL': ('C181756', None, None),                          # Extended, 5.2 k
    'RC2512FK-071KL': ('C189504', None, None),                          # Extended, 11 k
    # 0805 0.1% 25 ppm/K thin film (dividers of the thresholds and of the ADC)
    'RT0805BRD07102KL': ('C865126', None, None),                        # Extended, 8.2 k
    'RT0805BRD078K06L': ('C865685', None, None),                        # Extended, 5.2 k
    'RT0805BRD07221KL': ('C2984388', 'Viking Tech', 'AR05BTCW2213'),    # Extended, 4.1 k (Yageo: 0); 0.1% 25 ppm/K
    'RT0805BRD0710KL': ('C110775', None, None),                         # Extended, 670 k
    'RT0805BRD0715K4L': ('C865207', None, None),                        # Extended, 3.7 k
    'RT0805BRD0739KL': ('C2828718', 'Viking Tech', 'ARG05BTC3902'),     # Extended, 14 k (Yageo: 0); 0.1% 25 ppm/K
    'RT0805BRD07280KL': ('C865351', None, None),                        # Extended, 4.4 k
    'RT0805BRD0730K1L': ('C865392', None, None),                        # Extended, 3.3 k
    # ceramic capacitors
    'CL21A106KAYNNNG': ('C15850', 'Samsung Electro-Mechanics', 'CL21A106KAYNNNE'),   # Basic, 8.5 M; 10 uF 25 V X5R
    'CL21A106KAYNNNE': ('C15850', None, None),
    'CL21B104KBCNNNC': ('C49678', 'Yageo', 'CC0805KRX7R9BB104'),        # Basic, 26 M; 100 nF 50 V X7R
    'CL21B104KCFNNNE': ('C28233', None, None),                          # Basic, 3.1 M; 100 nF 100 V X7R
    'CL21B103KBANNNC': ('C1710', None, None),                           # Basic, 2.0 M
    'CL21B105KBFNNNE': ('C28323', None, None),                          # Basic, 3.9 M
    'CL21B474KBFNNNE': ('C13967', None, None),                          # Basic, 820 k
    'CL21C101JBANNNC': ('C1790', None, None),                           # Basic, 740 k
    'CL21B225KAFNNNE': ('C19110', None, None),                          # Extended, 460 k
    'CL21B102KBANNNC': ('C94121', 'Yageo', 'CC0805KRX7R9BB102'),        # Extended, 2.0 M (Samsung: 4.8 k)
    'CL21B273KBANNNC': ('C113860', 'Yageo', 'CC0805KRX7R9BB273'),       # Extended, 9.1 k (Samsung: not listed)
    'CL21B392KBANNNC': ('C113861', 'Yageo', 'CC0805KRX7R9BB392'),       # Extended, 3.2 k (Samsung: not listed)
    'CL21C820JBANNNC': ('C113833', 'Yageo', 'CC0805JRNPO9BN820'),       # Extended, 14 k (Samsung: 0); 82 pF 50 V NP0 5%
    'LMK325ABJ107MM-P': ('C386065', None, None),                        # Extended, 411; 100 uF 10 V X5R 1210
    'CC1210KKX7R9BB106': ('C596319', None, None),                       # Extended, 100 k
    'CS3225X5R226K160NRL': ('C2918506', None, None),                    # Extended, 28 k
    # semiconductors and the rest of the SMT parts
    '1N4148W-7-F': ('C81598', 'ST (Semtech)', '1N4148W'),               # Basic, 3.5 M; clamp diode of the buzzer
    'MMBT3904LT1G': ('C20526', 'Jiangsu Changjing', 'MMBT3904'),        # Basic, 4.3 M; buzzer switch
    'BZT52C5V1-7-F': ('C19077401', 'Hongjiacheng', 'BZT52C5V1'),        # Preferred, 2.2 M (Diodes Inc.: 3)
    'TPS3840PH27DBVR': ('C1849503', 'Texas Instruments', 'TPS3840PH27DBVRQ1'),   # Extended, 45 (DBVR: 6); same part, AEC-Q100
    'SN74LVC1G32DBVR': ('C10096', None, None),                          # Extended, 150 k
    'MCP1640T-I/CHY': ('C44365', None, None),                           # Extended, 516
    '744031004': ('C2649331', None, None),                              # Extended, 899
    'LTC2955ITS8-2#TRPBF': ('C683797', None, None),                     # Extended, 33
    'FH12-10S-0.5SH(55)': ('C506791', None, None),                      # Extended, 1.9 k
    # no stock at JLC on 2026-11-10: fitted by hand or supplied to the assembler (README, fab outputs)
    'CY15B104QN-50SXI': ('C1349451', None, None),                       # Extended, 0; the RAMXEED equivalent C42742723: 11
    # through-hole parts, soldered by hand; the numbers are for buying only
    '61300211121': ('C2915055', None, None), 'B5B-XH-A(LF)(SN)': ('C157991', None, None),
    'B2B-XH-A(LF)(SN)': ('C158012', None, None), 'B3F-1000': ('C93157', None, None),
    'WP7113ID': ('C6926004', None, None), 'CEM-1203(42)': ('C3812098', None, None),
}
# Fitted by hand, not by the SMT assembler: every through-hole part, and the SMT parts listed here.
HAND_SMT = {'U1': 'brak w magazynie JLC (2026-11-10); SOIC-8, lutowana ręcznie albo dostarczona do montażu'}
THT_LIBS = ('Connector_PinSocket', 'Connector_PinHeader', 'Connector_JST', 'Button_Switch_THT', 'LED_THT',
            'Buzzer_Beeper', 'Fuse', 'Capacitor_THT', 'MountingHole')


def part(ref, lib_id, value, footprint, nets, *, mpn='', manufacturer='', spec='', note='', lcsc='', qty=1, bom=True, dnp=False):
    """Record one board item; nets maps pin number to net name, lcsc is the LCSC/JLC part number and qty the
    number of pieces bought for this item (two clips for one fuse holder). dnp: footprint and symbol only, the
    part is not fitted and not in the BOM."""
    if mpn in JLC:
        number, maker, model = JLC[mpn]
        assert not lcsc or lcsc == number, (ref, lcsc, number)
        lcsc, manufacturer, mpn = number, maker or manufacturer, model or mpn
    hand = footprint.split(':')[0].startswith(THT_LIBS) or ref in HAND_SMT
    PARTS.append(dict(ref=ref, lib_id=lib_id, value=value, footprint=footprint,
                      nets={str(k): v for k, v in nets.items()}, mpn=mpn, manufacturer=manufacturer,
                      spec=spec, note=note, lcsc=lcsc, qty=qty, bom=bom and not dnp, dnp=dnp, hand=hand))


def res(ref, value, a, b, note, mpn='', spec='', footprint=R0805, lcsc=''):
    part(ref, 'Device:R', value, footprint, {1: a, 2: b}, mpn=mpn, manufacturer='Yageo' if mpn else '',
         spec=spec or f'{value} 1% 0805', note=note, lcsc=lcsc)


def cap(ref, value, a, b, note, mpn='', manufacturer='Samsung Electro-Mechanics', spec='', footprint=C0805):
    part(ref, 'Device:C', value, footprint, {1: a, 2: b}, mpn=mpn, manufacturer=manufacturer if mpn else '',
         spec=spec, note=note)


def zener15(ref, cathode, anode, note):
    part(ref, 'Device:D_Zener', 'BZT52C15', 'Diode_SMD:D_SOD-123', {1: cathode, 2: anode}, mpn='BZT52C15-7-F',
         manufacturer='Diodes Incorporated', spec='Zener 15 V, SOD-123', note=note, lcsc='C177014')


def precise(value, mpn):
    return dict(mpn=mpn, spec=f'{value} 0,1% 25 ppm/K 0805')


# --- MCU board: ESP32-S3-DevKitC-1 v1.1 in J5/J6, powered through its 3V3 pins ------------------------
# DevKitC user guide v1.1 allows 3V3/G as one of three exclusive supply options; its 5V pin stays open.
# New signals use GPIO45/46 (strapping, held low by pull-downs, which is their default boot level) and
# GPIO47/48 (3.3 V on WROOM-1 N8R8; RGB LED of v1.1 is on GPIO38).
DEVKIT = dict(mpn='PPTC221LFBN-RC', manufacturer='Sullins', spec='gniazdo żeńskie 1x22, 2,54 mm, proste, THT',
              note='ESP32-S3-DevKitC-1 v1.1 (N8R8) wpina się od góry; pin 1 od strony anteny')
part('J5', 'Connector_Generic:Conn_01x22', 'DEVKITC J1',
     'Connector_PinSocket_2.54mm:PinSocket_1x22_P2.54mm_Vertical',
     {1: '+3V3', 2: '+3V3', 4: 'V_AA_ADC', 5: 'V_12_ADC', 6: 'BTN_PREP', 7: 'LCD_CS', 8: 'BUZZER',
      9: 'LCD_DISP', 10: 'LCD_EXTCOMIN', 11: 'LED_ALARM', 12: 'FRAM_CS', 13: 'USB_LAPTOP', 14: 'DIV_EN', 15: 'RF_RESET',
      16: 'RF_CS', 17: 'SPI_MOSI', 18: 'SPI_SCK_DEVKIT', 19: 'SPI_MISO', 20: 'RF_GPIO0', 22: 'GND'}, **DEVKIT)
part('J6', 'Connector_Generic:Conn_01x22', 'DEVKITC J3',
     'Connector_PinSocket_2.54mm:PinSocket_1x22_P2.54mm_Vertical',
     {1: 'GND', 4: 'SW_CISZA', 5: 'BTN_BACK', 6: 'RF_GPIO3', 7: 'BTN_UP', 8: 'BTN_DOWN', 9: 'BTN_OK',
      15: 'PWM_SYNC', 16: 'PWR_INT', 17: 'KILL_MCU', 18: 'RF_GPIO1', 19: 'USB_DP', 20: 'USB_DN',
      21: 'GND', 22: 'GND'}, **DEVKIT)
res('R18', '33R', 'SPI_SCK_DEVKIT', 'SPI_SCK', 'szeregowy SCK przy GPIO12 DevKitC', 'RC0805FR-0733RL')

# --- Radio: Seeed Wio SX1262 for XIAO on two 1x7 sockets ------------------------------------------------
# Pin names after the L0 wiring (hardware/l0-diagnostic/ZLECENIE.md), confirmed on the Seeed schematic
# "Wio-SX1262 for XIAO V1.0": J1.6, J1.7 and J2.7 are not connected on the Wio (pass-through D5-D7 of the XIAO),
# J2.1 is VIN and stays open. Row spacing 15.24 mm (Seeed STEP model). SCK joins the bus after R18.
WIO = dict(mpn='PPTC071LFBN-RC', manufacturer='Sullins', spec='gniazdo żeńskie 1x7, 2,54 mm, proste, THT',
           note='Wio SX1262 (z zestawu 102010611) na listwach 1x7, rozstaw rzędów 15,24 mm (model Seeed)')
part('J8', 'Connector_Generic:Conn_01x07', 'WIO J1', 'Connector_PinSocket_2.54mm:PinSocket_1x07_P2.54mm_Vertical',
     {1: 'RF_GPIO1', 2: 'RF_GPIO0', 3: 'RF_RESET', 4: 'RF_CS', 5: 'RF_GPIO3'}, **WIO)
part('J9', 'Connector_Generic:Conn_01x07', 'WIO J2', 'Connector_PinSocket_2.54mm:PinSocket_1x07_P2.54mm_Vertical',
     {2: 'GND', 3: '+3V3_RF', 4: 'SPI_MOSI', 5: 'SPI_MISO', 6: 'SPI_SCK'}, **WIO)
part('JP3', 'Connector_Generic:Conn_01x02', '3V3 RADIO', 'Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical',
     {1: '+3V3', 2: '+3V3_RF'}, mpn='61300211121', manufacturer='Würth Elektronik',
     spec='listwa męska 1x2, 2,54 mm, ze zworką', note='punkt pomiaru prądu radia (elektronika.md, wiersz „radio”)')
cap('C1', '10u', '+3V3_RF', 'GND', '3,3 V przy Wio', 'CL21A106KAYNNNG', spec='10 µF 25 V X5R 0805')
cap('C2', '100n', '+3V3_RF', 'GND', '3,3 V przy Wio', 'CL21B104KBCNNNC', spec='100 nF 50 V X7R 0805')
res('R11', '10k', '+3V3', 'RF_CS', 'radio niewybrane przed startem MCU', 'RC0805FR-0710KL')
res('R12', '1k', 'RF_RESET', 'GND', 'radio w resecie do startu MCU; 1 kΩ wobec podciągnięcia na Wio (poprawka L0)',
    'RC0805FR-071KL')
res('R64', '10k', 'RF_GPIO3', 'GND', 'RXEN Wio w stanie niskim do startu MCU', 'RC0805FR-0710KL')

# --- USB-C to the laptop, data only (elektronika.md, "Gniazdo USB do laptopa") --------------------------
part('J4', 'Connector:USB_C_Receptacle_USB2.0_16P', 'USB-C DANE',
     'Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12',
     {'A1': 'GND', 'A12': 'GND', 'B1': 'GND', 'B12': 'GND', 'A5': 'USB_CC1', 'B5': 'USB_CC2',
      'A6': 'USB_DP', 'B6': 'USB_DP', 'A7': 'USB_DN', 'B7': 'USB_DN', 'SH': 'GND',
      'A4': 'USB_VBUS', 'B4': 'USB_VBUS', 'A9': 'USB_VBUS', 'B9': 'USB_VBUS'},
     mpn='TYPE-C-31-M-12', manufacturer='Korean Hroparts Elec',
     spec='gniazdo USB-C 16-pin, USB 2.0, SMD, nóżki obudowy przewlekane',
     note='VBUS tylko na bramkę Q12: laptop nigdy nie zasila stacji', lcsc='C165948')
res('R65', '5k1', 'USB_CC1', 'GND', 'CC1: urządzenie USB-C (bez tego laptop z USB-C nie wykryje stacji)',
    'RC0805FR-075K1L')
res('R66', '5k1', 'USB_CC2', 'GND', 'CC2: jak R65', 'RC0805FR-075K1L')
# Laptop detection for the standby relay (concept 06, "Czuwanie przekaźnika"): the sleeping MCU cannot serve USB,
# so it wakes on USB_LAPTOP going low and does not sleep while it stays low. VBUS reaches only the gate of Q12, so
# no current flows from the laptop into the station, also when it is off (4.5 uA into R73/R74 at 5 V).
res('R73', '100k', 'USB_VBUS', 'Q12_G', 'VBUS laptopa na bramkę Q12', 'RC0805FR-07100KL')
res('R74', '1M', 'Q12_G', 'GND', 'Q12 wyłączony bez laptopa', 'RC0805FR-071ML')
zener15('D17', 'Q12_G', 'GND', 'VGS Q12 ≤15 V przy VBUS do 20 V (zasilacz z PD)')
part('Q12', 'Transistor_FET:BSS138', 'BSS138', SOT23, {1: 'Q12_G', 2: 'GND', 3: 'USB_LAPTOP'},
     mpn='BSS138LT1G', manufacturer='onsemi', spec='N-MOSFET 50 V, IDSS ≤0,5 µA, SOT-23',
     note='wykrywanie laptopa: stan niski przy VBUS od około 2 V (próg bramki do 1,5 V)', lcsc='C82045')
res('R75', '100k', '+3V3', 'USB_LAPTOP', 'stan wysoki bez laptopa', 'RC0805FR-07100KL')
part('U8', 'Power_Protection:USBLC6-2SC6', 'USBLC6-2SC6', 'Package_TO_SOT_SMD:SOT-23-6',
     {1: 'USB_DP', 2: 'GND', 3: 'USB_DN', 4: 'USB_DN', 5: '+3V3', 6: 'USB_DP'},
     mpn='USBLC6-2SC6', manufacturer='STMicroelectronics', spec='ochrona ESD 2 linii danych USB, SOT-23-6',
     note='pin VBUS do +3V3: VBUS gniazda idzie tylko do bramki Q12, nie do szyny', lcsc='C7519')

# --- Panel, FRAM, buttons, alarm: as v1.1 --------------------------------------------------------------
part('J7', 'Connector_Generic_MountingPin:Conn_01x10_MountingPin', 'SHARP LS027B7DH01A',
     'Connector_FFC-FPC:Hirose_FH12-10S-0.5SH_1x10-1MP_P0.50mm_Horizontal',
     {1: 'SPI_SCK', 2: 'SPI_MOSI', 3: 'LCD_CS', 4: 'LCD_EXTCOMIN', 5: 'LCD_DISP', 6: '+5V', 7: '+5V',
      8: '+5V', 9: 'GND', 10: 'GND', 'MP': 'GND'},
     mpn='FH12-10S-0.5SH(55)', manufacturer='Hirose', spec='złącze FPC 10-pin, 0,5 mm, styki od dołu, SMD',
     note='panel Sharp LS027B7DH01A ekranem do góry; styk 1 panelu (SCLK) na padzie 1')
res('R13', '10k', 'LCD_CS', 'GND', 'CS ekranu aktywny stanem wysokim', 'RC0805FR-0710KL')
res('R19', '10k', 'LCD_DISP', 'GND', 'DISP = L do startu MCU', 'RC0805FR-0710KL')
cap('C4', '10u', '+5V', 'GND', 'VDD panelu', 'CL21A106KAYNNNG', spec='10 µF 25 V X5R 0805')
cap('C6', '100n', '+5V', 'GND', 'VDDA panelu', 'CL21B104KBCNNNC', spec='100 nF 50 V X7R 0805')
cap('C7', '100n', 'LCD_DISP', 'GND', 'DISP panelu (zalecenie Sharp)', 'CL21B104KBCNNNC', spec='100 nF 50 V X7R 0805')

part('U1', 'Memory_NVRAM:MB85RS2MT', 'CY15B104QN-50SXI', 'Package_SO:SOIC-8_5.3x5.3mm_P1.27mm',
     {1: 'FRAM_CS_U1', 2: 'SPI_MISO', 3: '+3V3', 4: 'GND', 5: 'SPI_MOSI', 6: 'SPI_SCK', 7: '+3V3', 8: '+3V3'},
     mpn='CY15B104QN-50SXI', manufacturer='Infineon', spec='FRAM 4 Mbit SPI, 1,8–3,6 V, SOIC-8 208 mil',
     note='zamiennik: RAMXEED MB85RS4MTPF-G-BCERE1 (LCSC C42742723); ' + HAND_SMT['U1'])
part('U3', 'WICI:TPS3840PH', 'TPS3840PH27', 'Package_TO_SOT_SMD:SOT-23-5',
     {1: 'FRAM_GUARD', 2: '+3V3', 3: 'GND'}, mpn='TPS3840PH27DBVR', manufacturer='Texas Instruments',
     spec='nadzorca napięcia 2,7 V, wyjście aktywne stanem wysokim, SOT-23-5', note='ochrona CS FRAM jak w v1.1')
part('U4', '74xGxx:74LVC1G32', '74LVC1G32', 'Package_TO_SOT_SMD:SOT-23-5',
     {1: 'FRAM_CS', 2: 'FRAM_GUARD', 3: 'GND', 4: 'FRAM_CS_U1', 5: '+3V3'},
     mpn='SN74LVC1G32DBVR', manufacturer='Texas Instruments', spec='bramka OR, SOT-23-5',
     note='CS FRAM = CS z MCU lub RESET z U3')
res('R20', '10k', '+3V3', 'FRAM_CS', 'FRAM niewybrana przed startem MCU', 'RC0805FR-0710KL')
cap('C3', '100n', '+3V3', 'GND', 'przy FRAM U1', 'CL21B104KBCNNNC', spec='100 nF 50 V X7R 0805')
cap('C11', '100n', '+3V3', 'GND', 'przy bramce U4', 'CL21B104KBCNNNC', spec='100 nF 50 V X7R 0805')
cap('C12', '100n', '+3V3', 'GND', 'przy nadzorcy U3', 'CL21B104KBCNNNC', spec='100 nF 50 V X7R 0805')
cap('C13', '100u', '+3V3', 'GND', 'podtrzymanie +3V3 przez czas reakcji U3 (budżet z v1.1)', 'LMK325ABJ107MM-P',
    manufacturer='Taiyo Yuden', spec='100 µF 10 V X5R 1210', footprint=C1210)

# Panel (front variant 2, 2026-11-09): GÓRA, DÓŁ, OK, WSTECZ are E-Switch PV6 in the front, like the main switch,
# wired to J10; CISZA is a panel toggle under the GT-4R guard, wired to J11. Every line from a panel wire has its ESD
# protection, 1 kOhm in series and a capacitor to ground within 10 mm of its connector (obudowa.md): U9 with
# R80-R83 and C60-C63 at J10, D19 with R16 and C64 at J11, D18 with R84 and C65 at J3. With the 10 kOhm pull-up the
# button filter has 0.1 ms on press and 1.1 ms on release; pressed, the line sits at 0.3 V.
BUTTONS = [('GÓRA', 'BTN_UP'), ('DÓŁ', 'BTN_DOWN'), ('OK', 'BTN_OK'), ('WSTECZ', 'BTN_BACK')]
part('J10', 'Connector_Generic:Conn_01x05', 'PRZYCISKI', 'Connector_JST:JST_XH_B5B-XH-A_1x05_P2.50mm_Vertical',
     {**{i + 1: net + '_IN' for i, (_, net) in enumerate(BUTTONS)}, 5: 'GND'}, mpn='B5B-XH-A(LF)(SN)',
     manufacturer='JST', spec='złącze 5-pin, 2,5 mm, THT',
     note='wiązka do czterech przycisków PV6 w panelu: 1 GÓRA, 2 DÓŁ, 3 OK, 4 WSTECZ, 5 masa wspólna')
part('J11', 'Connector_Generic:Conn_01x02', 'CISZA', XH2, {1: 'SW_COM', 2: 'GND'}, mpn='B2B-XH-A(LF)(SN)',
     manufacturer='JST', spec='złącze 2-pin, 2,5 mm, THT',
     note='przewód do przełącznika CISZA: 1 końcówka środkowa (wspólna), 2 masa na końcówkę najdalej od zawiasu GT-4R; '
          'dźwignia do zawiasu = cisza (SW_CISZA = L)')
# TPD4E1U06 (TI SLVSBQ9): 1 D1+, 2 GND, 3 D2+, 4 D2-, 5 NC, 6 D1-, four lines to ground; KiCad has no symbol for it,
# so the ESDA6V1-5SC6 symbol with the same pins 1-4 and 6 stands in, pin 5 (NC) left open.
part('U9', 'Power_Protection:ESDA6V1-5SC6', 'TPD4E1U06DCKR', 'Package_TO_SOT_SMD:SOT-363_SC-70-6',
     {1: 'BTN_UP_IN', 2: 'GND', 3: 'BTN_DOWN_IN', 4: 'BTN_OK_IN', 6: 'BTN_BACK_IN'},
     mpn='TPD4E1U06DCKR', manufacturer='Texas Instruments',
     spec='ochrona ESD 4 linii, SC-70-6, VRWM 5,5 V, upływ ≤10 nA przy 2,5 V, IEC 61000-4-2 ±15 kV',
     note='przy J10; symbol ESDA6V1-5SC6 (te same piny 1-4 i 6), pin 5 NC wolny; '
          'zamiennik TECH PUBLIC TPD4E1U06DCKR (LCSC C2987062)', lcsc='C194628')
for (label, net), r, c in zip(BUTTONS, ('R80', 'R81', 'R82', 'R83'), ('C60', 'C61', 'C62', 'C63')):
    res(r, '1k', net + '_IN', net, f'{label}: filtr RC i ograniczenie prądu od ESD', 'RC0805FR-071KL')
    cap(c, '100n', net, 'GND', f'{label}: filtr RC przy J10', 'CL21B104KBCNNNC', spec='100 nF 50 V X7R 0805')
TVS_1LINE = dict(mpn='TPD1E10B09DPYR', manufacturer='Texas Instruments', lcsc='C88031',
                 spec='ochrona ESD 1 linii, dwukierunkowa, VRWM ±9 V, upływ ≤100 nA przy 5 V, IEC 61000-4-2 ±20 kV')
part('D19', 'Power_Protection:TPD1E05U06DPY', 'TPD1E10B09', 'Package_SON:Texas_DPY0002A_0.6x1mm_P0.65mm',
     {1: 'SW_COM', 2: 'GND'}, note='przy J11', **TVS_1LINE)
cap('C64', '100n', 'SW_CISZA', 'GND', 'CISZA: filtr RC z R16 przy J11', 'CL21B104KBCNNNC',
    spec='100 nF 50 V X7R 0805')
part('SW6', 'Switch:SW_Push', 'PRZYGOTOWANIE', 'Button_Switch_THT:SW_TH_Tactile_Omron_B3F-100x',
     {1: 'BTN_PREP', 2: 'GND'}, mpn='B3F-1000', manufacturer='Omron', spec='przycisk 6x6 mm',
     note='pod naklejką serwisową')
for ref, net in (('R5', 'BTN_UP'), ('R6', 'BTN_DOWN'), ('R7', 'BTN_OK'), ('R8', 'BTN_BACK'),
                 ('R9', 'SW_CISZA'), ('R10', 'BTN_PREP')):
    res(ref, '10k', '+3V3', net, 'podciągnięcie wejścia', 'RC0805FR-0710KL')
res('R16', '1k', 'SW_COM', 'SW_CISZA', 'CISZA: filtr RC i ograniczenie prądu od ESD, przy J11', 'RC0805FR-071KL')

part('D1', 'Device:LED', 'ALARM', 'LED_THT:LED_D5.0mm', {1: 'GND', 2: 'LED_A'}, mpn='WP7113ID',
     manufacturer='Kingbright', spec='LED 5 mm czerwona, rozproszona',
     note='katoda do masy; kołnierzem do płytki (najwyżej 9,55 mm), świeci przez otwór Ø5,5 we froncie')
res('R1', '1k', 'LED_ALARM', 'LED_A', 'prąd diody około 1 mA', 'RC0805FR-071KL')
# Buzzer from the panel 5 V rail: the DevKitC 5V pin is dead when the board is fed through 3V3.
part('BZ1', 'Device:Buzzer', 'CEM-1203(42)', 'Buzzer_Beeper:MagneticBuzzer_ProSignal_ABT-410-RC',
     {1: 'BZ_P', 2: 'BZ_N'}, mpn='CEM-1203(42)', manufacturer='Same Sky (CUI Devices)',
     spec='brzęczyk magnetyczny 12 mm, 2048 Hz, cewka 42 Ω', note='pad 1 = "+"')
res('R2', '22R', '+5V', 'BZ_P', 'brzęczyk z szyny 5 V ekranu (U2); tętnienia VDD panelu sprawdza oscyloskop',
    'RC1206FR-0722RL', spec='22 Ω 1% 1206, 0,25 W', footprint='Resistor_SMD:R_1206_3216Metric')
part('D2', 'Device:D', '1N4148W', 'Diode_SMD:D_SOD-123', {1: 'BZ_P', 2: 'BZ_N'}, mpn='1N4148W-7-F',
     manufacturer='Diodes Incorporated', spec='dioda 75 V, SOD-123', note='dioda gasząca cewki brzęczyka')
part('Q1', 'Transistor_BJT:MMBT3904', 'MMBT3904', SOT23, {1: 'Q1_B', 2: 'GND', 3: 'BZ_N'},
     mpn='MMBT3904LT1G', manufacturer='onsemi', spec='NPN 40 V 200 mA, SOT-23', note='klucz brzęczyka')
res('R3', '1k', 'BUZZER', 'Q1_B', 'rezystor bazy Q1', 'RC0805FR-071KL')
res('R4', '100k', 'Q1_B', 'GND', 'Q1 wyłączony bez sterowania', 'RC0805FR-07100KL')

# --- Panel 5 V rail: MCP1640 from +3V3, as v1.1 (also feeds the buzzer now) -------------------------------
part('U2', 'Regulator_Switching:MCP1640x-xCHY', 'MCP1640', 'Package_TO_SOT_SMD:SOT-23-6',
     {1: 'BST_SW', 2: 'GND', 3: '+3V3', 4: 'BST_FB', 5: '+5V', 6: '+3V3'},
     mpn='MCP1640T-I/CHY', manufacturer='Microchip', spec='przetwornica podwyższająca, SOT-23-6',
     note='5,13 V z +3V3; EN na stałe do VIN')
part('L1', 'Device:L', '4u7', 'Inductor_SMD:L_Wuerth_WE-TPC-3816', {1: '+3V3', 2: 'BST_SW'},
     mpn='744031004', manufacturer='Würth Elektronik', spec='4,7 µH, Isat 0,9 A', note='cewka U2')
cap('C8', '10u', '+3V3', 'GND', 'wejście U2', 'CL21A106KAYNNNG', spec='10 µF 25 V X5R 0805')
cap('C9', '10u', '+5V', 'GND', 'wyjście U2', 'CL21A106KAYNNNG', spec='10 µF 25 V X5R 0805')
res('R21', '1M', '+5V', 'BST_FB', 'RTOP dzielnika U2', 'RC0805FR-071ML')
res('R22', '309k', 'BST_FB', 'GND', 'RBOT dzielnika U2', 'RC0805FR-07309KL')
cap('C10', '100p', '+5V', 'BST_FB', 'równolegle do R21', 'CL21C101JBANNNC', spec='100 pF 50 V C0G 0805')

# --- 12 V input (elektronika.md point 3): fuse, TVS, LM74800-Q1 with two 100 V MOSFETs ----------------------
# Common drain (TI application figure): Q2 is the ideal diode (source at A), Q3 the switch to VSYS. With the
# input reversed and clamped at -53.3 V the common drain stays near VSYS - 0.6 V (Q3 body diode, VSYS held by the
# cells or C50), so Q2 sees VSYS + 53.3 V: about 59.7 V on fresh cells, and about 70 V when the pulse comes while
# 12 V ran the station just below the OVP threshold (VSYS up to 17.3 V); with +53.3 V and the switch open Q3 sees
# about 53 V. Hence 100 V parts (AO4292E: VGS +-20 V for the 10-13 V DGATE/HGATE drive, Ciss 1.2 nF like the
# 60 V AO4264E). The same corner exceeds the LM74800 limit for OUT, C and VSNS (data sheet 7.1: <= 70 V + V(A),
# 16.7 V at V(A) = -53.3 V) by up to 0.6 V on OUT; at VSYS <= 16.7 V it holds (README, open points). The
# common drain V12_MID is fed through the Q2 body diode even in shutdown, so it powers the button
# controller from 12 V alone (no cells) and is where the 12 V is measured.
part('J2', 'Connector_Generic:Conn_01x02', '12V', XH2, {1: '12V_IN', 2: 'GND'}, mpn='B2B-XH-A(LF)(SN)',
     manufacturer='JST', spec='złącze 2-pin, 2,5 mm, THT', note='przewód do gniazda 12 V w ściance obudowy')
part('F1', 'Device:Fuse', 'T1A', 'Fuse:Fuseholder_Clip-5x20mm_Bel_FC-203-22_Lateral_P17.80x5.00mm_D1.17mm_Horizontal',
     {1: '12V_IN', 2: 'V12_F'}, mpn='01110501Z', manufacturer='Littelfuse',
     spec='zacisk bezpiecznika 5x20 mm do druku (seria 111 501), 10 A, około 7 mm nad płytką',
     note='2 zaciski na F1; od spodu płytki, lutowane ręcznie; bezpiecznik T1A osobno (poniżej)', lcsc='C151075',
     qty=2)
part('D4', 'Device:D_TVS', 'SMBJ33CA', 'Diode_SMD:D_SMB', {1: 'V12_F', 2: 'GND'}, mpn='SMBJ33CA',
     manufacturer='Hongjiacheng (R+O)', spec='TVS dwukierunkowy 33 V, ograniczenie 53,3 V, SMB',
     note='pula promocyjna JLC; zapasowo Littelfuse SMBJ33CA (LCSC C83325)', lcsc='C19077587')
# Place for a second TVS at the sources of Q2, not fitted (decided after the second review, 2026-11-10): D4 stands 105 mm away at
# the input. It is fitted only if the peak measured at C38 on the first units is above 65 V (README, input
# protection at the switch).
part('D20', 'Device:D_TVS', 'SMBJ33CA', 'Diode_SMD:D_SMB', {1: 'V12_F', 2: 'GND'}, mpn='SMBJ33CA',
     manufacturer='Hongjiacheng (R+O)', spec='TVS dwukierunkowy 33 V, ograniczenie 53,3 V, SMB',
     note='NIE MONTOWAĆ: miejsce na drugi TVS przy łączniku; montaż po pomiarze na pierwszych sztukach',
     lcsc='C19077587', dnp=True)
part('U5', 'WICI:LM74800-Q1', 'LM74800-Q1', 'Package_SON:WSON-12-1EP_3x3mm_P0.5mm_EP1.5x2.5mm',
     {1: 'S12_DGATE', 2: 'V12_F', 3: 'V12_MID', 4: 'S12_SW', 5: 'S12_OV', 6: 'S12_EN', 7: 'GND',
      8: 'S12_HGATE', 9: 'VSYS', 10: 'V12_MID', 11: 'S12_CAP', 12: 'V12_MID'},
     mpn='LM74800QDRRRQ1', manufacturer='Texas Instruments',
     spec='sterownik idealnej diody i łącznika 3–65 V, do −65 V, WSON-12 3 × 3 mm',
     note='pad termiczny RTN zostaje niepodłączony (karta, tabela 6-1)', lcsc='C3215600')
NMOS100 = dict(mpn='AO4292E', manufacturer='Alpha & Omega', spec='N-MOSFET 100 V, 23 mΩ, VGS ±20 V, SOIC-8')
part('Q2', 'WICI:NMOS_SO8', 'AO4292E', 'Package_SO:SOIC-8_3.9x4.9mm_P1.27mm',
     {1: 'V12_F', 2: 'V12_F', 3: 'V12_F', 4: 'S12_DGATE', 5: 'V12_MID', 6: 'V12_MID', 7: 'V12_MID',
      8: 'V12_MID'}, note='idealna dioda (DGATE); przy odwrotnym impulsie do około 70 V', lcsc='C176743', **NMOS100)
part('Q3', 'WICI:NMOS_SO8', 'AO4292E', 'Package_SO:SOIC-8_3.9x4.9mm_P1.27mm',
     {1: 'VSYS', 2: 'VSYS', 3: 'VSYS', 4: 'S12_HGATE', 5: 'V12_MID', 6: 'V12_MID', 7: 'V12_MID',
      8: 'V12_MID'}, note='łącznik do VSYS (HGATE), odcina przy OVP i UV', lcsc='C176743', **NMOS100)
cap('C30', '100n', 'V12_MID', 'GND', 'VS U5 (karta: 100 nF)', 'CL21B104KCFNNNE', spec='100 nF 100 V X7R 0805')
# Input capacitor at the switch (LM7480-Q1 SNOSD95C: 7.3 "A to GND" 0.1 uF minimum, 10.2.3.3, 11.1): the TVS D4
# stands at the connector, about 105 mm of track away, so the capacitor takes the spike of that track when the
# MOSFETs open: V = I x sqrt(L / C), under 1 V at 1 A with 0.1 uH (README, "Ścieżki").
cap('C38', '100n', 'V12_F', 'GND', 'kondensator wejściowy U5 przy źródle Q2 (karta: min. 100 nF na A)', 'CL21B104KCFNNNE',
    spec='100 nF 100 V X7R 0805')
cap('C31', '100n', 'S12_CAP', 'V12_MID', 'pompa ładunkowa U5, CAP–VS (karta: 100 nF)', 'CL21B104KBCNNNC',
    spec='100 nF 50 V X7R 0805')
# OVP 102k / 8.06k: 1.231 V x 13.66 = 16.81 V rising (16.32-17.30 V), 15.4 V falling. Below 120 kOhm in total
# as the data sheet asks (OV leakage up to 1 uA: 7.5 mV, 0.1 V at the input). The ladder hangs on SW, which
# U5 disconnects in shutdown.
res('R30', '102k', 'S12_SW', 'S12_OV', 'górny rezystor progu OVP (16,8 V)', **precise('102 kΩ', 'RT0805BRD07102KL'))
res('R31', '8k06', 'S12_OV', 'GND', 'dolny rezystor progu OVP', **precise('8,06 kΩ', 'RT0805BRD078K06L'))
# Inrush (data sheet equation 2): 55 uA / 250 mA x about 120 uF on VSYS = 26 nF.
cap('C32', '27n', 'S12_DVDT', 'GND', 'C_dVdT: prąd włączania około 250 mA przy około 120 µF na VSYS',
    'CL21B273KBANNNC', spec='27 nF 50 V X7R 0805')
# R32 (R1 of data sheet figure 9-3, faster turn-off): with 1 kOhm C32 adds at most 14.5 mA (14.5 V gate drive)
# to what HGATE must sink, and the 39-75 uA source drops only 75 mV on it; tau 27 us. The data sheet (7.5) gives
# the HGATE sink only for overvoltage (>= 168 mA); for turn-off through EN/UVLO it gives no current. TI EVM-CD
# uses 100 Ohm with 10 nF; 100 Ohm here would let C32 add up to 145 mA.
res('R32', '1k', 'S12_HGATE', 'S12_DVDT', 'R1 z rysunku 9-3 karty (szybsze wyłączenie): C32 dokłada ≤14,5 mA do prądu HGATE',
    'RC0805FR-071KL')

# UV with hysteresis from the U5 EN/UVLO comparator (1.231 V rising, 1.132 V falling), on a ladder that is
# connected only while the station is on (Q4), so U5 sits in its 2.87 uA shutdown when the station is off.
# The ladder hangs on the input side of Q2: the common drain is back-fed from VSYS through the Q3 body
# diode when running on cells, and would hold EN/UVLO between its shutdown and UVLO thresholds (U5 then
# draws about 0.4 mA from the cells). 246 kOhm in total keeps the EN/UVLO leakage (up to 200 nA) at 0.04 V
# on the input and the ladder at 49 uA from 12 V. Rising 11.94 V (11.59-12.29 V), falling 10.98 V
# (10.58-11.24 V). The same ladder gives the ADC tap: 0.0625 x V12, 36 V -> 2.25 V.
part('Q4', 'Transistor_FET:BSS84', 'SI2309CDS', SOT23, {1: 'Q4_G', 2: 'V12_F', 3: 'V12_SW'},
     mpn='SI2309CDS-T1-GE3', manufacturer='Vishay', spec='P-MOSFET −60 V, SOT-23',
     note='podłącza dzielnik 12 V tylko przy włączonej stacji; impuls 53,3 V wymaga ≥60 V', lcsc='C10493')
res('R33', '100k', 'V12_F', 'Q4_G', 'bramka Q4 do źródła', 'RC0805FR-07100KL')
part('D5', 'Device:D_Zener', 'BZT52C15', 'Diode_SMD:D_SOD-123', {1: 'V12_F', 2: 'Q4_G'},
     mpn='BZT52C15-7-F', manufacturer='Diodes Incorporated', spec='Zener 15 V, SOD-123',
     note='|VGS| Q4 ≤15 V przy 33 V ciągle i impulsie', lcsc='C177014')
res('R34', '100k', 'Q4_G', 'Q5_D', 'bramka Q4 do klucza Q5', 'RC0805FR-07100KL')
part('Q5', 'Transistor_FET:2N7002', '2N7002', SOT23, {1: 'Q5_G', 2: 'GND', 3: 'Q5_D'},
     mpn='2N7002,215', manufacturer='Nexperia', spec='N-MOSFET 60 V, IDSS ≤1 µA (≤10 µA w 150 °C), SOT-23',
     note='klucz Q4 z szyny ON; dren do 53,3 V przy wyłączonej stacji, więc 60 V', lcsc='C65189')
res('R35', '100k', 'ON', 'Q5_G', 'ON na bramkę Q5', 'RC0805FR-07100KL')
res('R36', '1M', 'Q5_G', 'GND', 'Q5 wyłączony bez ON; 91% ON na bramce także przy ogniwach około 4 V', 'RC0805FR-071ML')
zener15('D15', 'Q5_G', 'GND', 'VGS Q5 ≤15 V przy ON do około 35 V')
res('R37', '221k', 'V12_SW', 'S12_EN', 'dzielnik UV: włączenie 11,94 V (11,59–12,29 V), wyłączenie 10,98 V (10,58–11,24 V)',
    **precise('221 kΩ', 'RT0805BRD07221KL'))
# The divider stands about 110 mm from U5, so EN/UVLO gets a capacitor at its pin: 10 nF with the 22.8 kOhm of
# the ladder is 0.23 ms, which does not move the thresholds.
cap('C39', '10n', 'S12_EN', 'GND', 'filtr EN/UVLO przy U5 (dzielnik jest około 110 mm dalej); 0,23 ms z dzielnikiem',
    'CL21B103KBANNNC', spec='10 nF 50 V X7R 0805')
res('R38', '10k', 'S12_EN', 'V_12_DIV', 'dzielnik UV i pomiaru 12 V', **precise('10,0 kΩ', 'RT0805BRD0710KL'))
res('R39', '15k4', 'V_12_DIV', 'GND', 'pomiar 12 V: 0,0625 × V12', **precise('15,4 kΩ', 'RT0805BRD0715K4L'))
cap('C33', '100n', 'V_12_ADC', 'GND', 'filtr wejścia ADC 12 V za R76 (karta ESP32-S3, 5.5: 100 nF przy ADC)', 'CL21B104KBCNNNC', spec='100 nF 50 V X7R 0805')
# BAV199 instead of BAT54S: <= 80 nA up to 150 C, so leakage moves the ADC 12 V reading by <= 0.02 V (BAT54S:
# no hot maximum; about 0.7 uA per diode at 60 C typical). Same SOT-23 pins (1 A1, 2 K2, 3 K1/A2). The negative
# clamp is about -0.6...-0.9 V instead of -0.3 V, at most 0.23 mA with 12 V reversed (to be measured).
# KiCad 10 has no BAV199 symbol; the BAT54S symbol has the same pins (1 A, 2 K, 3 COM).
BAV199 = dict(mpn='BAV199,215', manufacturer='Nexperia', spec='podwójna dioda o małym upływie 75 V (szczyt 85 V), ≤5 nA, SOT-23',
              lcsc='C40919')
part('D6', 'Diode:BAT54S', 'BAV199', SOT23, {1: 'GND', 2: '+3V3', 3: 'V_12_DIV'},
     note='ogranicza wejście ADC przy odwrotnym 12 V; upływ nie zmienia pomiaru 12 V', **BAV199)
# R76/R77 between the divider node (clamped by BAV199) and the ADC side: with 12 V or the cells reversed the
# divider pulls the node down (0.137 mA at -33 V, 0.224 mA at the -53.3 V pulse through 231 kOhm, also with the
# station off, through the Q4 body diode; cells -7.2 V: about 0.15 mA through 39 kOhm and the Q6 body diode).
# BAV199 clamps only at about -0.6...-0.9 V, so without R76/R77 the ESP32-S3 protection diodes (about -0.5 V;
# current not specified in the data sheet) would carry most of it. Through 10 kOhm at most (0.9 - 0.5) V /
# 10 kOhm = 40 uA reaches the pin. C33/C34 sit after the resistors, at the ADC side, as in the data sheet ADC
# characterisation (5.5: 100 nF at the ADC), so sampling draws its charge from 100 nF and not through 10 kOhm.
# Pin input current <= 50 nA at 25 C (5.4; no hot value) x 10 kOhm = 0.5 mV at the pin. Cells: Q6 switches the divider only for a
# measurement, and the filter now settles with (7.96 + 10) kOhm x 100 nF = 1.8 ms, so the program waits >= 20 ms
# after DIV_EN (12 bits need 8.3 tau = 15 ms).
res('R76', '10k', 'V_12_DIV', 'V_12_ADC', 'szeregowo do GPIO5 (przed C33): prąd do pinu przy odwrotnym 12 V ≤40 µA',
    'RC0805FR-0710KL')

# --- AA cells: 1 Ohm pulse resistor and Schottky diode to VSYS (decision Z7) -------------------------------
part('J1', 'Connector_Generic:Conn_01x02', 'OGNIWA 4xAA', XH2, {1: 'BAT_IN', 2: 'GND'}, mpn='B2B-XH-A(LF)(SN)',
     manufacturer='JST', spec='złącze 2-pin, 2,5 mm, THT', note='przewód do koszyka 4 × AA z kluczowaniem')
res('R40', '1R', 'BAT_IN', 'BAT_R', 'ogranicza udar przy wkładaniu ogniw do ≤5 A (Z13); napięcie mierzone przed nim',
    'RC2512FK-071RL', spec='1 Ω 1% 2512, 1 W, impulsowy', footprint='Resistor_SMD:R_2512_6332Metric')
# D7 reverse current flows into the primary lithium cells while 12 V runs the station: the Energizer L91 data
# sheet (EBC-8915AP-D9X) allows 2 uA, acceptance asks <= 1 uA. RB168MM-40 (ROHM "super low IR"): 0.55 uA max
# at 40 V and 25 C; from the VR-IR curves about 0.02 uA at 25 C, 0.1 uA at 45 C, 0.4 uA at 60 C (15 V, typical).
# No hot maximum in the data sheet: 0.55 uA (25 C, 40 V) scaled by the curves gives for the worst unit at 15 V
# about 0.8 uA at 40 C, 1.8 uA at 50 C and 4.1 uA at 60 C, so 2 uA holds to about 50 C (station indoors).
# Forward drop about 0.43 V at 120 mA (0.5 V at -25 C), IFSM 40 A. A standard 1 A Schottky leaks 20-500 uA
# at 25 C; a silicon diode (0.8-1 V) would cut the cell runtime below 48 h.
part('D7', 'Device:D_Schottky', 'RB168MM-40', 'Diode_SMD:D_SOD-123F', {1: 'VSYS', 2: 'BAT_R'},
     mpn='RB168MM-40TR', manufacturer='ROHM', spec='Schottky 40 V 1 A, IR ≤0,55 µA przy 40 V, PMDU (SOD-123FL)',
     note='prąd wsteczny do ogniw L91 ≤2 µA (karta L91): typowo około 0,4 µA w 60 °C', lcsc='C509936')
part('Q6', 'Transistor_FET:BSS84', 'BSS84AK', SOT23, {1: 'Q6_G', 2: 'BAT_IN', 3: 'VAA_SW'},
     mpn='BSS84AK,215', manufacturer='Nexperia', spec='P-MOSFET −50 V, SOT-23',
     note='podłącza dzielnik ogniw tylko na czas pomiaru (DIV_EN)', lcsc='C127273')
res('R41', '100k', 'BAT_IN', 'Q6_G', 'Q6 wyłączony bez sterowania', 'RC0805FR-07100KL')
part('Q7', 'Transistor_FET:BSS138', 'BSS138', SOT23, {1: 'DIV_EN', 2: 'GND', 3: 'Q6_G'},
     mpn='BSS138LT1G', manufacturer='onsemi', spec='N-MOSFET 50 V, IDSS ≤0,5 µA, SOT-23', note='klucz Q6 z MCU', lcsc='C82045')
res('R43', '100k', 'DIV_EN', 'GND', 'DIV_EN niski do startu MCU; GPIO46 musi być niski przy resecie',
    'RC0805FR-07100KL')
res('R44', '39k', 'VAA_SW', 'V_AA_DIV', 'pomiar ogniw: 7,3 V → 1,49 V (zakres ATTEN2)', **precise('39,0 kΩ', 'RT0805BRD0739KL'))
res('R45', '10k', 'V_AA_DIV', 'GND', 'pomiar ogniw', **precise('10,0 kΩ', 'RT0805BRD0710KL'))
cap('C34', '100n', 'V_AA_ADC', 'GND', 'filtr wejścia ADC ogniw za R77 (jak C33)', 'CL21B104KBCNNNC', spec='100 nF 50 V X7R 0805')
part('D11', 'Diode:BAT54S', 'BAV199', SOT23, {1: 'GND', 2: '+3V3', 3: 'V_AA_DIV'},
     note='ogranicza wejście ADC przy ogniwach odwrotnie', **BAV199)
res('R77', '10k', 'V_AA_DIV', 'V_AA_ADC', 'szeregowo do GPIO4 (przed C34): prąd do pinu przy ogniwach odwrotnie ≤40 µA; pomiar ≥20 ms po DIV_EN',
    'RC0805FR-0710KL')

# --- Power button controller: LTC2955-2 on the diode sum of the cells and 12 V --------------------------
# 12 V side through 1 kOhm / 1 uF (data sheet: VIN > 20 V through 1 kOhm) and a 33 V Zener, because the
# common drain follows the input up to 33 V and the TVS clamp (53.3 V); LTC2955 works to 36 V.
part('D8', 'Device:D', 'BAS116H', 'Diode_SMD:D_SOD-123F', {1: 'VCTL', 2: 'BAT_R'}, mpn='BAS116H,115',
     manufacturer='Nexperia', spec='dioda 75 V, ≤5 nA, SOD-123F', note='suma diodowa od strony ogniw', lcsc='C74210')
part('D9', 'Device:D', 'BAS116H', 'Diode_SMD:D_SOD-123F', {1: 'VCTL', 2: 'V12_FLT'}, mpn='BAS116H,115',
     manufacturer='Nexperia', spec='dioda 75 V, ≤5 nA, SOD-123F', note='suma diodowa od strony 12 V', lcsc='C74210')
res('R46', '1k', 'V12_MID', 'V12_FLT', 'filtr 12 V przed sumą (Z14); ze wspólnego drenu, więc działa z samego 12 V; '
    '2512, bo przy ograniczeniu 53,3 V traci około 0,4 W', 'RC2512FK-071KL', spec='1 kΩ 1% 2512, 1 W',
    footprint='Resistor_SMD:R_2512_6332Metric')
cap('C35', '1u', 'V12_FLT', 'GND', 'filtr 12 V przed sumą (Z14)', 'CL21B105KBFNNNE', spec='1 µF 50 V X7R 0805')
part('D10', 'Device:D_Zener', 'BZT52C33', 'Diode_SMD:D_SOD-123', {1: 'V12_FLT', 2: 'GND'},
     mpn='BZT52C33-7-F', manufacturer='Diodes Incorporated', spec='Zener 33 V (31–35 V), SOD-123',
     note='VIN LTC2955 ≤35 V (praca do 36 V); przy 24–28,8 V nie przewodzi', lcsc='C260938')
cap('C36', '100n', 'VCTL', 'GND', 'VIN U6', 'CL21B104KBCNNNC', spec='100 nF 50 V X7R 0805')
part('U6', 'WICI:LTC2955-2', 'LTC2955ITS8-2', 'Package_TO_SOT_SMD:TSOT-23-8',
     {1: 'PWR_ON', 2: 'PWR_KILL', 3: 'PWR_TMR', 4: 'GND', 5: 'PWR_PB', 6: 'VCTL', 7: 'PWR_ENB', 8: 'PWR_INT'},
     mpn='LTC2955ITS8-2#TRPBF', manufacturer='Analog Devices', spec='sterownik przycisku zasilania 1,5–36 V, TSOT-23-8',
     note='włączenie przyciskiem albo zboczem narastającym ON (powrót 12 V); pinout TS8 z karty rew. A, s. 3')
# Automatic start from 12 V (elektronika.md, "Stany zasilania 12 V"): a rising edge on ON (0.76-0.84 V)
# turns the station on; in TS8 the falling edge does nothing, and a steady high ON does not restart it
# after a manual off. D13 (BAS116H) in series blocks the reversed input, so ON stays at about 0 V (leakage
# <= 80 nA on 30 kOhm) instead of the Schottky clamp at -0.3 V, the data sheet limit, which had no margin when
# cold. 280k / 30.1k at 0.1 %: 0.76-0.84 V x 10.30 = 7.83-8.65 V plus D13 at about 27 uA (0.5 V hot to about
# 0.85 V cold, data sheet curve and 0.9 V max at 1 mA), about 8.3-9.5 V, below any working 12 V source, so every
# connection or return of 12 V crosses it. The threshold may lie under the UV rising threshold: the controller
# stays on (KILL from VCTL) and U5 joins 12 V once it rises above about 11.9 V. About 37 uA from 12 V while
# connected; no Schottky leakage on the node any more. Filter 27.1 kOhm x 470 nF = 12.8 ms.
part('D13', 'Device:D', 'BAS116H', 'Diode_SMD:D_SOD-123F', {1: 'ON_DIV', 2: 'V12_F'}, mpn='BAS116H,115',
     manufacturer='Nexperia', spec='dioda 75 V, ≤5 nA, SOD-123F',
     note='blokuje odwrotne 12 V na wejściu ON (zamiast zacisku BAT54H)', lcsc='C74210')
res('R70', '280k', 'ON_DIV', 'PWR_ON', 'samoczynne włączenie przy podłączeniu i powrocie 12 V: około 8,2–9,6 V (szacunek)',
    lcsc='C865351', **precise('280 kΩ', 'RT0805BRD07280KL'))
res('R71', '30k1', 'PWR_ON', 'GND', 'dolny rezystor dzielnika ON', **precise('30,1 kΩ', 'RT0805BRD0730K1L'))
cap('C53', '470n', 'PWR_ON', 'GND', 'filtr ON (około 13 ms) przeciw zakłóceniom z przewodu 12 V', 'CL21B474KBFNNNE',
    spec='470 nF 50 V X7R 0805')
cap('C37', '2u2', 'PWR_TMR', 'GND', 'wymuszone wyłączenie po 5,2–19 s przytrzymania', 'CL21B225KAFNNNE',
    spec='2,2 µF 25 V X7R 0805')
part('J3', 'Connector_Generic:Conn_01x02', 'WYLACZNIK', XH2, {1: 'PWR_PB_IN', 2: 'GND'}, mpn='B2B-XH-A(LF)(SN)',
     manufacturer='JST', spec='złącze 2-pin, 2,5 mm, THT', note='przewód do przycisku zasilania w panelu')
# PB of U6 (LTC2955 rev. A): 900 kOhm pull-up to its LDO, open circuit 3.0-5.5 V, threshold 0.6-1.0 V, range -36...36 V,
# ESD +-25 kV HBM only. A 9 V TVS stays off at 5.5 V (<=100 nA, 0.09 V on 900 kOhm); 1 kOhm and 10 nF at J3 cut the
# fast edge of a discharge (the data sheet uses the same pair at VIN against transients); pressed, PB sees 5 mV more.
part('D18', 'Power_Protection:TPD1E05U06DPY', 'TPD1E10B09', 'Package_SON:Texas_DPY0002A_0.6x1mm_P0.65mm',
     {1: 'PWR_PB_IN', 2: 'GND'}, note='przy J3', **TVS_1LINE)
res('R84', '1k', 'PWR_PB_IN', 'PWR_PB', 'wyłącznik: filtr RC i ograniczenie prądu od ESD, przy J3', 'RC0805FR-071KL')
cap('C65', '10n', 'PWR_PB', 'GND', 'wyłącznik: filtr RC przy J3', 'CL21B103KBANNNC', spec='10 nF 50 V X7R 0805')
res('R47', '10k', '+3V3', 'PWR_INT', 'podciągnięcie INT (otwarty dren)', 'RC0805FR-0710KL')
part('Q8', 'Transistor_FET:BSS84', 'BSS84AK', SOT23, {1: 'Q8_G', 2: 'VCTL', 3: 'ON'},
     mpn='BSS84AK,215', manufacturer='Nexperia', spec='P-MOSFET −50 V, SOT-23', note='szyna ON z sumy diodowej', lcsc='C127273')
res('R49', '1M', 'VCTL', 'Q8_G', 'bramka Q8 do źródła; wyłączony EN̄ i tak wisi na VIN przez 900 kΩ w U6', 'RC0805FR-071ML')
res('R50', '100k', 'Q8_G', 'PWR_ENB', 'EN̄ do bramki Q8: |VGS| = 91% VCTL, około 3 V przy ogniwach 4 V', 'RC0805FR-07100KL')
# R78 holds the ON rail down while the station is off. Without it only the gate dividers load the rail
# (1.1 MOhm || 1.1 MOhm = 550 kOhm), and the drain leakage of Q8 (BSS84AK: <= 1 uA at 25 C, <= 2 uA at 150 C,
# about 1.2 uA at 60 C estimated) would lift ON to about 0.66 V and the gates of Q5 and Q10 to about 0.6 V, close
# to the BSS138 threshold (0.5-1.5 V at 1 mA in data sheet rev. 8, about 70 mV lower at 60 C): Q10 could then pull
# Q9 on and start the converter of a station that is off. With 100 kOhm (85 kOhm in total) ON stays <= 0.1 V.
# Costs 60 uA from the cells and about 0.13 mA from 12 V (up to 0.33 mA at the 33 V clamp) only while ON is high.
res('R78', '100k', 'ON', 'GND', 'szyna ON przy wyłączonej stacji ≤0,1 V mimo upływu Q8 na gorąco', 'RC0805FR-07100KL')
zener15('D12', 'VCTL', 'Q8_G', '|VGS| Q8 ≤15 V przy VCTL do około 35 V')
# KILL is held high from VCTL, the supply of U6, and not from 3V3 or the ON rail: when 3V3 is lost (12 V below
# the UV threshold without cells), the controller stays on and the station starts by itself as soon as 12 V is
# usable again. Only the MCU (through Q11) or a long press turns it off. KILL follows VCTL down to about 0.8 V,
# so after a 12 V loss without cells U6 drops its state through VIN undervoltage (0.8-1.3 V) and not through
# KILL; on return it powers up with ON high and turns on after about 1 s (data sheet, ON pin initial turn-on).
# With KILL from the ON rail a loss of 0.2-1.6 s would end inside the 0.6-1.4 s EN lockout and the ON edge
# would be ignored. D16 keeps KILL below its 6 V maximum; at about 3.6 V on VCTL (weak cells) KILL stays
# above 2 V with 2 uA Zener and 1 uA Q11 leakage (25 C; to be measured hot). Costs about 15 uA from 12 V
# and up to about 5 uA from the cells while the station is off.
res('R48', '470k', 'VCTL', 'PWR_KILL', 'KILL wysoki z VCTL, niezależnie od 3V3, szyny ON i MCU', 'RC0805FR-07470KL')
part('D16', 'Device:D_Zener', 'BZT52C5V1', 'Diode_SMD:D_SOD-123', {1: 'PWR_KILL', 2: 'GND'}, mpn='BZT52C5V1-7-F',
     manufacturer='Diodes Incorporated', spec='Zener 5,1 V, SOD-123', note='KILL ≤6 V (karta) przy VCTL do około 35 V; pierwotnie Diodes Inc. BZT52C5V1-7-F (LCSC C151588, 3 szt. w magazynie)')
part('Q11', 'Transistor_FET:BSS138', 'BSS138', SOT23, {1: 'KILL_MCU', 2: 'GND', 3: 'PWR_KILL'},
     mpn='BSS138LT1G', manufacturer='onsemi', spec='N-MOSFET 50 V, IDSS ≤0,5 µA, SOT-23',
     note='MCU wyłącza stację; GPIO nie widzi napięcia KILL; upływ w 60 °C około 1 µA wobec granicy KILL 5,8 µA',
     lcsc='C82045')
res('R72', '100k', 'KILL_MCU', 'GND', 'Q11 wyłączony przy resecie i bez zasilania MCU', 'RC0805FR-07100KL')

# RUN of the 3V3 converter must stay <= VIN + 0.3 V, so it is switched from VSYS (Q9) and not taken
# from ON, which follows the 12 V side even when the switch is open. The 0.5 uA RUN hysteresis current
# times R55 gives 0.11 V, below the RUN threshold, so the converter does switch off.
part('Q9', 'Transistor_FET:BSS84', 'BSS84AK', SOT23, {1: 'Q9_G', 2: 'VSYS', 3: 'RUN'},
     mpn='BSS84AK,215', manufacturer='Nexperia', spec='P-MOSFET −50 V, SOT-23', note='RUN przetwornicy z VSYS', lcsc='C127273')
# R51 220k (not 1M): the off-state leakage of Q10 (BSS138LT1G, <= 0.5 uA at 25 C, about 1 uA at 60 C estimated)
# gives at most about 0.22 V on the gate of Q9 against its 1.1 V minimum threshold (BSS84AK, 25 C). Costs up to
# 80 uA (17.3 V) only while the station is on.
res('R51', '220k', 'VSYS', 'Q9_G', 'Q9 wyłączony bez sterowania; upływ Q10 w 60 °C daje ≤0,22 V na bramce Q9',
    'RC0805FR-07220KL')
part('Q10', 'Transistor_FET:BSS138', 'BSS138', SOT23, {1: 'Q10_G', 2: 'GND', 3: 'Q9_G'},
     mpn='BSS138LT1G', manufacturer='onsemi', spec='N-MOSFET 50 V, IDSS ≤0,5 µA, SOT-23', note='klucz Q9 z szyny ON', lcsc='C82045')
res('R53', '100k', 'ON', 'Q10_G', 'ON na bramkę Q10', 'RC0805FR-07100KL')
res('R54', '1M', 'Q10_G', 'GND', 'Q10 wyłączony bez ON; przy ogniwach około 4 V ON ≈ 3,3 V, więc VGS ≈ 3 V (próg BSS138 do 1,5 V)',
    'RC0805FR-071ML')
zener15('D14', 'Q10_G', 'GND', 'VGS Q10 ≤15 V przy ON do około 35 V')
res('R55', '220k', 'RUN', 'GND', 'RUN niski przy wyłączonym Q9', 'RC0805FR-07220KL')
cap('C52', '1n', 'RUN', 'GND', 'filtr RUN (karta LTC3115-1: 1000 pF, nie więcej)', 'CL21B102KBANNNC',
    spec='1 nF 50 V X7R 0805')

# --- VSYS and the 3V3 converter: LTC3115-1, values of the JLC test board (hardware/przetwornica-3v3) ---------
part('C50', 'Device:C_Polarized', '100u 25V', 'Capacitor_THT:CP_Radial_D8.0mm_P3.50mm', {1: 'VSYS', 2: 'GND'},
     mpn='UKL1E101MPD', manufacturer='Nichicon',
     spec='elektrolit o małym upływie 100 µF 25 V ±20%, 8 × 11,5 mm, raster 3,5 mm, −40…+85 °C, 2000 h w 85 °C, '
          'upływ ≤5 µA przy 25 V, tętnienia 280 mA',
     note='kondensator szyny: przełączenie 12 V ↔ ogniwa bez restartu; pojemność do potwierdzenia w próbie toru ogniw; '
          'brak w magazynie JLC, kupowany u dystrybutora i lutowany ręcznie')
part('U7', 'WICI:LTC3115-1', 'LTC3115-1', 'WICI:LTC3115-1_FE20_CA',
     {1: 'GND', 2: 'RUN', 3: 'CONV_SW2', 4: '+3V3', 5: 'GND', 6: 'GND', 7: 'CONV_VC', 8: 'CONV_FB', 9: 'CONV_RT',
      10: 'GND', 11: 'GND', 12: 'CONV_VCC', 13: 'VSYS', 14: 'CONV_VCC', 15: 'CONV_BST2', 16: 'CONV_BST1',
      17: 'VSYS', 18: 'CONV_SW1', 19: 'PWM_SYNC', 20: 'GND', 21: 'GND'},
     mpn='LTC3115EFE-1#PBF', manufacturer='Analog Devices', spec='przetwornica podwyższająco-obniżająca 2,7–40 V, TSSOP-20 EP',
     note='footprint z generatora płytki testowej; czeka na pomiar sprawności (Z11)', lcsc='C580689')
part('L2', 'Device:L', '15u', 'WICI:L_Bourns_SRP1038A', {1: 'CONV_SW2', 2: 'CONV_SW1'}, mpn='SRP1038A-150M',
     manufacturer='Bourns', spec='15 µH, Isat ≥2 A, 40/45 mΩ', lcsc='C780183')
for ref in ('C40', 'C41'):
    cap(ref, '10u', 'VSYS', 'GND', 'wejście U7', 'CC1210KKX7R9BB106', manufacturer='Yageo',
        spec='10 µF 50 V X7R 1210', footprint=C1210)
for ref in ('C42', 'C43'):
    cap(ref, '22u', '+3V3', 'GND', 'wyjście U7', 'CS3225X5R226K160NRL', manufacturer='Samwha',
        spec='22 µF 16 V X5R 1210', footprint=C1210)
cap('C44', '100n', 'CONV_BST1', 'CONV_SW1', 'bootstrap BST1', 'CL21B104KBCNNNC', spec='100 nF 50 V X7R 0805')
cap('C45', '100n', 'CONV_BST2', 'CONV_SW2', 'bootstrap BST2', 'CL21B104KBCNNNC', spec='100 nF 50 V X7R 0805')
cap('C46', '100n', 'VSYS', 'GND', 'pin VIN (13) U7', 'CL21B104KBCNNNC', spec='100 nF 50 V X7R 0805')
cap('C47', '10u', 'CONV_VCC', 'GND', 'VCC U7 (karta: ≥4,7 µF skutecznie)', 'CL21A106KAYNNNE', spec='10 µF 25 V X5R 0805')
res('R60', '47k5', 'CONV_RT', 'GND', 'R_T: 750 kHz', 'RC0805FR-0747K5L')
res('R61', '1M', '+3V3', 'CONV_FB', 'dzielnik FB: 3,31 V', 'RC0805FR-071ML')
res('R62', '432k', 'CONV_FB', 'GND', 'dzielnik FB', 'RC0805FR-07432KL')
cap('C48', '82p', 'CONV_FB', 'CONV_VC', 'kompensacja typ III: C_POLE', 'CL21C820JBANNNC', spec='82 pF 50 V C0G 0805')
cap('C49', '3n9', 'CONV_FB', 'CONV_CMP1', 'kompensacja: C_FB', 'CL21B392KBANNNC', spec='3,9 nF 50 V X7R 0805')
res('R67', '20k', 'CONV_CMP1', 'CONV_VC', 'kompensacja: R_FB', 'RC0805FR-0720KL')
cap('C51', '82p', 'CONV_FB', 'CONV_CMP2', 'kompensacja: C_FF', 'CL21C820JBANNNC', spec='82 pF 50 V C0G 0805')
res('R68', '20k', 'CONV_CMP2', '+3V3', 'kompensacja: R_FF', 'RC0805FR-0720KL')
res('R63', '100k', 'PWM_SYNC', 'GND', 'Burst Mode do startu MCU; GPIO45 musi być niski przy resecie', 'RC0805FR-07100KL')

HOLES = ['H1', 'H2', 'H3', 'H4', 'H5', 'H6']
for ref in HOLES:
    part(ref, 'Mechanical:MountingHole', '#4', 'MountingHole:MountingHole_3.5mm', {}, bom=False,
         note='na słupku skrzynki Hammond 1599KBAT (model STEP), tulejka 6 mm, wkręt 3 × 12 do tworzyw z podkładką 1 mm (EXTRAS)')

EXTRAS = [
    ('JP3', 1, 'Würth Elektronik', '60900213421', 'zworka 2,54 mm', 'założona w pracy; zdjęta przy pomiarze prądu radia'),
    ('H1-H6', 6, 'Harwin', 'R30-6700694', 'tulejka dystansowa nylonowa 6,00 mm, otwór 3,2 mm, średnica 5,0 mm',
     'na słupku skrzynki pod płytką; nie calowa 1/4" (6,35 mm)'),
    ('H1-H6', 6, 'Bossard', 'BN 82428 3 × 12 (3034086)', 'wkręt do tworzyw ecosyn-plast 3 × 12 mm, łeb walcowy '
     'Ø5,6 × 2,4 mm, Pozidriv PZ1, stal ocynkowana', 'TME B3X12/BN82428; od spodu, przez podkładkę'),
    ('H1-H6', 6, 'Essentra', '1340107', 'podkładka poliamidowa M3: 1,0 mm, otwór 3,1 mm, średnica 6 mm',
     'TME 1340107; pod łbem wkrętu, skraca wejście wkrętu w słupek o 1 mm'),
    ('J10', 4, 'E-Switch', 'PV6F240SS', 'przycisk panelowy GÓRA, DÓŁ, OK, WSTECZ: Ø16 mm, SPST-NO, IP65, bez podświetlenia',
     'we froncie, przewody do wtyku JST XHP-5'),
    ('J3', 1, 'E-Switch', 'PV6F240SS', 'wyłącznik główny, panelowy: Ø16 mm, SPST-NO, IP65', 'we froncie, przewody do wtyku XHP-2'),
    ('J11', 1, 'E-Switch', '100SP1T8B13M1QEH', 'przełącznik CISZA: SPDT ON-ON, tulejka 15/32-32, końcówki lutowane',
     'we froncie pod osłoną GT-4R, przewody do wtyku XHP-2'),
    ('J11', 1, 'CW Industries', 'GT-4R', 'osłona przełącznika, czerwona', 'na tulei przełącznika CISZA'),
    ('J10', 1, 'JST', 'XHP-5', 'obudowa wtyku 5-pin', 'wiązka przycisków'),
    ('J1, J2, J3, J11', 4, 'JST', 'XHP-2', 'obudowa wtyku 2-pin', 'koszyk, 12 V, wyłącznik, CISZA'),
    ('J1-J3, J10, J11', 13, 'JST', 'SXH-001T-P0.6', 'styk zaciskany do XHP, 28-22 AWG', ''),
    ('koszyk ogniw', 1, '', 'taśma dwustronna ≤0,3 mm', 'taśma dwustronna cienka, około 60 × 55 mm', 'zamiast podkładki z kompletu BH4AAW; odstęp końcówek przycisków od koszyka'),
    ('ekran w J7', 1, 'Sharp', 'LS027B7DH01A', 'panel pamięciowy LCD 2,7 cala, 400 × 240', 'ekranem do góry'),
    ('J8, J9', 1, 'Seeed', '102010611 (Wio z zestawu)', 'moduł Wio SX1262 z listwami 1x7', 'antena przez u.FL i przewód do SMA'),
    ('J5, J6', 1, 'Espressif', 'ESP32-S3-DevKitC-1-N8R8', 'płytka MCU v1.1', 'zasilana przez piny 3V3'),
    ('D20', 2, 'Hongjiacheng (R+O)', 'SMBJ33CA (LCSC C19077587)', 'TVS dwukierunkowy 33 V, SMB',
     'do ręcznego montażu D20 na jednym z dwóch prototypów: 1 sztuka i 1 zapasowa; JLC go nie montuje'),
    ('F1', 1, 'Schurter', '0001.2504', 'bezpiecznik T1A 5x20 mm', 'wkładany w zaciski F1; drugi: Littelfuse 0477001'),
]

FLAGS = ['GND', '+3V3', 'VSYS', 'V12_MID', 'VCTL', '+3V3_RF']

# ESP32-S3 GPIO per DevKitC-1 v1.1 header pin (user guide v1.1).
DEVKIT_GPIO = {
    **{('J5', i + 1): g for i, g in enumerate(
        ['3V3', '3V3', 'EN', 'GPIO4', 'GPIO5', 'GPIO6', 'GPIO7', 'GPIO15', 'GPIO16', 'GPIO17', 'GPIO18',
         'GPIO8', 'GPIO3', 'GPIO46', 'GPIO9', 'GPIO10', 'GPIO11', 'GPIO12', 'GPIO13', 'GPIO14', '5V', 'GND'])},
    **{('J6', i + 1): g for i, g in enumerate(
        ['GND', 'GPIO43', 'GPIO44', 'GPIO1', 'GPIO2', 'GPIO42', 'GPIO41', 'GPIO40', 'GPIO39', 'GPIO38',
         'GPIO37', 'GPIO36', 'GPIO35', 'GPIO0', 'GPIO45', 'GPIO48', 'GPIO47', 'GPIO21', 'GPIO20', 'GPIO19',
         'GND', 'GND'])},
}
# Signal table: net, ESP32-S3 GPIO, role. v1.1 assignments unchanged; new ones marked in the role.
SIGNALS = [
    ('SPI_SCK_DEVKIT', 'GPIO12', 'SCK (przez R18 na SPI_SCK)'), ('SPI_MOSI', 'GPIO11', 'MOSI'),
    ('SPI_MISO', 'GPIO13', 'MISO'), ('RF_CS', 'GPIO10', 'NSS Wio'), ('RF_RESET', 'GPIO9', 'RESET Wio'),
    ('RF_GPIO0', 'GPIO14', 'BUSY Wio'), ('RF_GPIO1', 'GPIO21', 'DIO1 Wio'), ('RF_GPIO3', 'GPIO42', 'RXEN Wio'),
    ('FRAM_CS', 'GPIO8', 'CS FRAM'), ('LCD_CS', 'GPIO7', 'CS ekranu'), ('LCD_EXTCOMIN', 'GPIO17', 'EXTCOMIN'),
    ('LCD_DISP', 'GPIO16', 'DISP'), ('LED_ALARM', 'GPIO18', 'dioda alarmu'), ('BUZZER', 'GPIO15', 'brzęczyk'),
    ('BTN_UP', 'GPIO41', 'GÓRA'), ('BTN_DOWN', 'GPIO40', 'DÓŁ'), ('BTN_OK', 'GPIO39', 'OK'),
    ('BTN_BACK', 'GPIO2', 'WSTECZ'), ('SW_CISZA', 'GPIO1', 'CISZA'), ('BTN_PREP', 'GPIO6', 'przygotowanie'),
    ('V_AA_ADC', 'GPIO4', 'nowy: napięcie ogniw (ADC1)'), ('V_12_ADC', 'GPIO5', 'nowy: napięcie 12 V (ADC1; dawniej VTEST)'),
    ('DIV_EN', 'GPIO46', 'nowy: klucz dzielnika ogniw'), ('PWM_SYNC', 'GPIO45', 'nowy: PWM przetwornicy na czas TX'),
    ('PWR_INT', 'GPIO48', 'nowy: INT sterownika przycisku'), ('KILL_MCU', 'GPIO47', 'nowy: wyłączenie stacji przez KILL (Q11)'),
    ('USB_LAPTOP', 'GPIO3', 'nowy: laptop podłączony (stan niski), wybudzenie z czuwania'),
    ('USB_DP', 'GPIO20', 'nowy: USB D+ do gniazda USB-C'), ('USB_DN', 'GPIO19', 'nowy: USB D− do gniazda USB-C'),
]
# Never on the board: UART0 console, PSRAM pins of N8R8, RGB LED of v1.1, boot-mode GPIO0.
FORBIDDEN_GPIO = {'GPIO0', 'GPIO43', 'GPIO44', 'GPIO35', 'GPIO36', 'GPIO37', 'GPIO38'}
# Strapping pins in use: each needs a pull-down that gives its default (low) level at reset.
STRAP_PULLDOWN = {'GPIO45': 'R63', 'GPIO46': 'R43'}


def check():
    """Cross-check the signal table, single-pin nets and strapping pins."""
    nets = {}
    for p in PARTS:
        for pin, net in p['nets'].items():
            nets.setdefault(net, []).append((p['ref'], int(pin) if pin.isdigit() else pin))
    refs = [p['ref'] for p in PARTS]
    assert len(refs) == len(set(refs)), 'duplicate reference'
    for net, gpio, _role in SIGNALS:
        on_devkit = [DEVKIT_GPIO[m] for m in nets[net] if m[0] in ('J5', 'J6')]
        assert on_devkit == [gpio], (net, on_devkit, gpio)
    for net, members in nets.items():
        assert len(members) >= 2, ('single-pin net', net, members)
    used = {DEVKIT_GPIO[(r, int(pin))] for r in ('J5', 'J6') for pin in PARTS[refs.index(r)]['nets']}
    assert not used & FORBIDDEN_GPIO, used & FORBIDDEN_GPIO
    for gpio, ref in STRAP_PULLDOWN.items():
        net = next(n for n, g, _ in SIGNALS if g == gpio)
        assert PARTS[refs.index(ref)]['nets'] in ({'1': net, '2': 'GND'}, {'1': 'GND', '2': net}), (gpio, ref)
    return nets


if __name__ == '__main__':
    n = check()
    print(len(PARTS), 'items', len(n), 'nets')
