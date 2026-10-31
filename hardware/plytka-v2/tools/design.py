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


def part(ref, lib_id, value, footprint, nets, *, mpn='', manufacturer='', spec='', note='', bom=True):
    """Record one board item; nets maps pin number to net name."""
    PARTS.append(dict(ref=ref, lib_id=lib_id, value=value, footprint=footprint,
                      nets={str(k): v for k, v in nets.items()}, mpn=mpn, manufacturer=manufacturer,
                      spec=spec, note=note, bom=bom))


def res(ref, value, a, b, note, mpn='', spec='', footprint=R0805):
    part(ref, 'Device:R', value, footprint, {1: a, 2: b}, mpn=mpn, manufacturer='Yageo' if mpn else '',
         spec=spec or f'{value} 1% 0805', note=note)


def cap(ref, value, a, b, note, mpn='', manufacturer='Samsung Electro-Mechanics', spec='', footprint=C0805):
    part(ref, 'Device:C', value, footprint, {1: a, 2: b}, mpn=mpn, manufacturer=manufacturer if mpn else '',
         spec=spec, note=note)


def zener15(ref, cathode, anode, note):
    part(ref, 'Device:D_Zener', 'BZT52C15', 'Diode_SMD:D_SOD-123', {1: cathode, 2: anode}, mpn='BZT52C15-7-F',
         manufacturer='Diodes Incorporated', spec='Zener 15 V, SOD-123', note=note)


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
# Pin names after the L0 wiring (hardware/l0-diagnostic/ZLECENIE.md); row spacing and pins J1.6, J1.7,
# J2.7 are taken from the Seeed drawing before layout. SCK joins the bus after R18, like panel and FRAM.
WIO = dict(mpn='PPTC071LFBN-RC', manufacturer='Sullins', spec='gniazdo żeńskie 1x7, 2,54 mm, proste, THT',
           note='Wio SX1262 (z zestawu 102010611) na listwach 1x7; rozstaw rzędów z rysunku Seeed przed layoutem')
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
     spec='gniazdo USB-C 16-pin, USB 2.0, SMD', note='VBUS tylko na bramkę Q12: laptop nigdy nie zasila stacji')
res('R65', '5k1', 'USB_CC1', 'GND', 'CC1: urządzenie USB-C (bez tego laptop z USB-C nie wykryje stacji)',
    'RC0805FR-075K1L')
res('R66', '5k1', 'USB_CC2', 'GND', 'CC2: jak R65', 'RC0805FR-075K1L')
# Laptop detection for the standby relay (concept 06, "Czuwanie przekaźnika"): the sleeping MCU cannot serve USB,
# so it wakes on USB_LAPTOP going low and does not sleep while it stays low. VBUS reaches only the gate of Q12, so
# no current flows from the laptop into the station, also when it is off (4.5 uA into R73/R74 at 5 V).
res('R73', '100k', 'USB_VBUS', 'Q12_G', 'VBUS laptopa na bramkę Q12', 'RC0805FR-07100KL')
res('R74', '1M', 'Q12_G', 'GND', 'Q12 wyłączony bez laptopa', 'RC0805FR-071ML')
zener15('D17', 'Q12_G', 'GND', 'VGS Q12 ≤15 V przy VBUS do 20 V (zasilacz z PD)')
part('Q12', 'Transistor_FET:2N7002', '2N7002', SOT23, {1: 'Q12_G', 2: 'GND', 3: 'USB_LAPTOP'},
     mpn='2N7002-7-F', manufacturer='Diodes Incorporated', spec='N-MOSFET 60 V, SOT-23',
     note='wykrywanie laptopa: stan niski przy VBUS od około 3 V (próg bramki do 2,5 V)')
res('R75', '100k', '+3V3', 'USB_LAPTOP', 'stan wysoki bez laptopa', 'RC0805FR-07100KL')
part('U8', 'Power_Protection:USBLC6-2SC6', 'USBLC6-2SC6', 'Package_TO_SOT_SMD:SOT-23-6',
     {1: 'USB_DP', 2: 'GND', 3: 'USB_DN', 4: 'USB_DN', 5: '+3V3', 6: 'USB_DP'},
     mpn='USBLC6-2SC6', manufacturer='STMicroelectronics', spec='ochrona ESD 2 linii danych USB, SOT-23-6',
     note='pin VBUS do +3V3: VBUS gniazda idzie tylko do bramki Q12, nie do szyny')

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
     note='zamiennik: RAMXEED MB85RS4MTPF-G-BCERE1')
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

BUTTONS = [('SW1', 'GÓRA', 'BTN_UP'), ('SW2', 'DÓŁ', 'BTN_DOWN'), ('SW3', 'OK', 'BTN_OK'),
           ('SW4', 'WSTECZ', 'BTN_BACK')]
for ref, label, net in BUTTONS:
    part(ref, 'Switch:SW_Push', label, 'Button_Switch_THT:SW_SPST_Omron_B3F-40xx', {1: net, 2: 'GND'},
         mpn='B3F-4055', manufacturer='Omron', spec='przycisk 12x12 mm, nasadka B32-1310',
         note='rozmiar i rozstaw przycisków pod obudowę i rękawice: do ustalenia z obudową')
part('SW5', 'Switch:SW_SPDT', 'CISZA', 'WICI:Toggle_ESwitch_100SP1T1B4M2QE', {1: 'GND', 2: 'SW_COM'},
     mpn='100SP1T1B4M2QE', manufacturer='E-Switch', spec='przełącznik dźwigienkowy SPDT ON-NONE-ON',
     note='1-2 = cisza radiowa (SW_CISZA = L)')
part('SW6', 'Switch:SW_Push', 'PRZYGOTOWANIE', 'Button_Switch_THT:SW_TH_Tactile_Omron_B3F-100x',
     {1: 'BTN_PREP', 2: 'GND'}, mpn='B3F-1000', manufacturer='Omron', spec='przycisk 6x6 mm',
     note='pod naklejką serwisową')
for ref, net in (('R5', 'BTN_UP'), ('R6', 'BTN_DOWN'), ('R7', 'BTN_OK'), ('R8', 'BTN_BACK'),
                 ('R9', 'SW_CISZA'), ('R10', 'BTN_PREP')):
    res(ref, '10k', '+3V3', net, 'podciągnięcie wejścia', 'RC0805FR-0710KL')
res('R16', '1k', 'SW_COM', 'SW_CISZA', 'SW_CISZA przez 1 kΩ', 'RC0805FR-071KL')

part('D1', 'Device:LED', 'ALARM', 'LED_THT:LED_D5.0mm', {1: 'GND', 2: 'LED_A'}, mpn='WP7113ID',
     manufacturer='Kingbright', spec='LED 5 mm czerwona, rozproszona', note='katoda do masy')
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

# --- 12 V input (elektronika.md point 3): fuse, TVS, LM74800-Q1 with two 60 V MOSFETs -----------------------
# Common drain (TI application figure): Q2 is the ideal diode (source at A), Q3 the switch to VSYS. The
# common drain V12_MID is fed through the Q2 body diode even in shutdown, so it powers the button
# controller from 12 V alone (no cells) and is where the 12 V is measured.
part('J2', 'Connector_Generic:Conn_01x02', '12V', XH2, {1: '12V_IN', 2: 'GND'}, mpn='B2B-XH-A(LF)(SN)',
     manufacturer='JST', spec='złącze 2-pin, 2,5 mm, THT', note='przewód do gniazda 12 V w ściance obudowy')
part('F1', 'Device:Fuse', 'T1A', 'Fuse:Fuseholder_Clip-5x20mm_Bel_FC-203-22_Lateral_P17.80x5.00mm_D1.17mm_Horizontal',
     {1: '12V_IN', 2: 'V12_F'}, mpn='0001.2504', manufacturer='Schurter',
     spec='bezpiecznik zwłoczny T1A 5x20 mm, 300 V DC, w oprawce na płytce',
     note='oprawka (dwa zaciski 5x20) w BOM montażowni do dobrania; drugi: Littelfuse 0477001')
part('D4', 'Device:D_TVS', 'SMBJ33CA', 'Diode_SMD:D_SMB', {1: 'V12_F', 2: 'GND'}, mpn='SMBJ33CA',
     manufacturer='Vishay', spec='TVS dwukierunkowy 33 V, ograniczenie 53,3 V, SMB',
     note='LCSC C19077587 (pula promocyjna); zapasowo Littelfuse C83325')
part('U5', 'WICI:LM74800-Q1', 'LM74800-Q1', 'Package_SON:WSON-12-1EP_3x3mm_P0.5mm_EP1.5x2.5mm',
     {1: 'S12_DGATE', 2: 'V12_F', 3: 'V12_MID', 4: 'S12_SW', 5: 'S12_OV', 6: 'S12_EN', 7: 'GND',
      8: 'S12_HGATE', 9: 'VSYS', 10: 'V12_MID', 11: 'S12_CAP', 12: 'V12_MID'},
     mpn='LM74800QDRRRQ1', manufacturer='Texas Instruments',
     spec='sterownik idealnej diody i łącznika 3–65 V, do −65 V, WSON-12 3 × 3 mm',
     note='LCSC C3215600; pad termiczny RTN zostaje niepodłączony (karta, tabela 6-1)')
NMOS60 = dict(mpn='AO4264E', manufacturer='Alpha & Omega', spec='N-MOSFET 60 V, 9,8 mΩ, SOIC-8')
part('Q2', 'WICI:NMOS_SO8', 'AO4264E', 'Package_SO:SOIC-8_3.9x4.9mm_P1.27mm',
     {1: 'V12_F', 2: 'V12_F', 3: 'V12_F', 4: 'S12_DGATE', 5: 'V12_MID', 6: 'V12_MID', 7: 'V12_MID',
      8: 'V12_MID'}, note='idealna dioda (DGATE); LCSC C334232 (pula basic); zapasowo BUK7Y15-60EX', **NMOS60)
part('Q3', 'WICI:NMOS_SO8', 'AO4264E', 'Package_SO:SOIC-8_3.9x4.9mm_P1.27mm',
     {1: 'VSYS', 2: 'VSYS', 3: 'VSYS', 4: 'S12_HGATE', 5: 'V12_MID', 6: 'V12_MID', 7: 'V12_MID',
      8: 'V12_MID'}, note='łącznik do VSYS (HGATE), odcina przy OVP i UV', **NMOS60)
cap('C30', '100n', 'V12_MID', 'GND', 'VS U5 (karta: 100 nF)', 'CL21B104KCFNNNE', spec='100 nF 100 V X7R 0805')
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
res('R32', '1k', 'S12_HGATE', 'S12_DVDT', 'R1 z rysunku 9-3 karty (szybsze wyłączenie); wartość do sprawdzenia',
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
     note='podłącza dzielnik 12 V tylko przy włączonej stacji; impuls 53,3 V wymaga ≥60 V')
res('R33', '100k', 'V12_F', 'Q4_G', 'bramka Q4 do źródła', 'RC0805FR-07100KL')
part('D5', 'Device:D_Zener', 'BZT52C15', 'Diode_SMD:D_SOD-123', {1: 'V12_F', 2: 'Q4_G'},
     mpn='BZT52C15-7-F', manufacturer='Diodes Incorporated', spec='Zener 15 V, SOD-123',
     note='|VGS| Q4 ≤15 V przy 33 V ciągle i impulsie')
res('R34', '100k', 'Q4_G', 'Q5_D', 'bramka Q4 do klucza Q5', 'RC0805FR-07100KL')
part('Q5', 'Transistor_FET:2N7002', '2N7002', SOT23, {1: 'Q5_G', 2: 'GND', 3: 'Q5_D'},
     mpn='2N7002-7-F', manufacturer='Diodes Incorporated', spec='N-MOSFET 60 V, SOT-23', note='klucz Q4 z szyny ON')
res('R35', '100k', 'ON', 'Q5_G', 'ON na bramkę Q5', 'RC0805FR-07100KL')
res('R36', '1M', 'Q5_G', 'GND', 'Q5 wyłączony bez ON; 91% ON na bramce także przy ogniwach około 4 V', 'RC0805FR-071ML')
zener15('D15', 'Q5_G', 'GND', 'VGS Q5 ≤15 V przy ON do około 35 V')
res('R37', '221k', 'V12_SW', 'S12_EN', 'dzielnik UV: włączenie 11,94 V (11,59–12,29 V), wyłączenie 10,98 V (10,58–11,24 V)',
    **precise('221 kΩ', 'RT0805BRD07221KL'))
res('R38', '10k', 'S12_EN', 'V_12_ADC', 'dzielnik UV i pomiaru 12 V', **precise('10,0 kΩ', 'RT0805BRD0710KL'))
res('R39', '15k4', 'V_12_ADC', 'GND', 'pomiar 12 V: 0,0625 × V12', **precise('15,4 kΩ', 'RT0805BRD0715K4L'))
cap('C33', '100n', 'V_12_ADC', 'GND', 'filtr wejścia ADC 12 V', 'CL21B104KBCNNNC', spec='100 nF 50 V X7R 0805')
part('D6', 'Diode:BAT54S', 'BAT54S', SOT23, {1: 'GND', 2: '+3V3', 3: 'V_12_ADC'}, mpn='BAT54SLT1G',
     manufacturer='onsemi', spec='podwójna dioda Schottky 30 V, SOT-23', note='ogranicza wejście ADC przy 53,3 V')

# --- AA cells: 1 Ohm pulse resistor and Schottky diode to VSYS (decision Z7) -------------------------------
part('J1', 'Connector_Generic:Conn_01x02', 'OGNIWA 4xAA', XH2, {1: 'BAT_IN', 2: 'GND'}, mpn='B2B-XH-A(LF)(SN)',
     manufacturer='JST', spec='złącze 2-pin, 2,5 mm, THT', note='przewód do koszyka 4 × AA z kluczowaniem')
res('R40', '1R', 'BAT_IN', 'BAT_R', 'ogranicza udar przy wkładaniu ogniw do ≤5 A (Z13); napięcie mierzone przed nim',
    'RC2512FK-071RL', spec='1 Ω 1% 2512, 1 W, impulsowy', footprint='Resistor_SMD:R_2512_6332Metric')
part('D7', 'Device:D_Schottky', 'Schottky 40V', 'Diode_SMD:D_SMA', {1: 'VSYS', 2: 'BAT_R'},
     spec='Schottky VR ≥30 V, spadek ≤0,4 V przy 120 mA, impuls ≥5 A, mały prąd wsteczny przy 16 V i 45 °C',
     note='część do wyboru po sprawdzeniu dopuszczalnego prądu wstecznego ogniw L91 (zasilanie.md, „Otwarte”)')
part('Q6', 'Transistor_FET:BSS84', 'BSS84AK', SOT23, {1: 'Q6_G', 2: 'BAT_IN', 3: 'VAA_SW'},
     mpn='BSS84AK', manufacturer='Nexperia', spec='P-MOSFET −50 V, SOT-23',
     note='podłącza dzielnik ogniw tylko na czas pomiaru (DIV_EN)')
res('R41', '100k', 'BAT_IN', 'Q6_G', 'Q6 wyłączony bez sterowania', 'RC0805FR-07100KL')
part('Q7', 'Transistor_FET:2N7002', '2N7002', SOT23, {1: 'DIV_EN', 2: 'GND', 3: 'Q6_G'},
     mpn='2N7002-7-F', manufacturer='Diodes Incorporated', spec='N-MOSFET 60 V, SOT-23', note='klucz Q6 z MCU')
res('R43', '100k', 'DIV_EN', 'GND', 'DIV_EN niski do startu MCU; GPIO46 musi być niski przy resecie',
    'RC0805FR-07100KL')
res('R44', '39k', 'VAA_SW', 'V_AA_ADC', 'pomiar ogniw: 7,3 V → 1,49 V (zakres ATTEN2)', **precise('39,0 kΩ', 'RT0805BRD0739KL'))
res('R45', '10k', 'V_AA_ADC', 'GND', 'pomiar ogniw', **precise('10,0 kΩ', 'RT0805BRD0710KL'))
cap('C34', '100n', 'V_AA_ADC', 'GND', 'filtr wejścia ADC ogniw', 'CL21B104KBCNNNC', spec='100 nF 50 V X7R 0805')
part('D11', 'Diode:BAT54S', 'BAT54S', SOT23, {1: 'GND', 2: '+3V3', 3: 'V_AA_ADC'}, mpn='BAT54SLT1G',
     manufacturer='onsemi', spec='podwójna dioda Schottky 30 V, SOT-23', note='ogranicza wejście ADC przy ogniwach odwrotnie')

# --- Power button controller: LTC2955-2 on the diode sum of the cells and 12 V --------------------------
# 12 V side through 1 kOhm / 1 uF (data sheet: VIN > 20 V through 1 kOhm) and a 33 V Zener, because the
# common drain follows the input up to 33 V and the TVS clamp (53.3 V); LTC2955 works to 36 V.
part('D8', 'Device:D', 'BAS116H', 'Diode_SMD:D_SOD-123F', {1: 'VCTL', 2: 'BAT_R'}, mpn='BAS116H',
     manufacturer='Nexperia', spec='dioda 75 V, ≤5 nA, SOD-123F', note='suma diodowa od strony ogniw')
part('D9', 'Device:D', 'BAS116H', 'Diode_SMD:D_SOD-123F', {1: 'VCTL', 2: 'V12_FLT'}, mpn='BAS116H',
     manufacturer='Nexperia', spec='dioda 75 V, ≤5 nA, SOD-123F', note='suma diodowa od strony 12 V')
res('R46', '1k', 'V12_MID', 'V12_FLT', 'filtr 12 V przed sumą (Z14); ze wspólnego drenu, więc działa z samego 12 V; '
    '2512, bo przy ograniczeniu 53,3 V traci około 0,4 W', 'RC2512FK-071KL', spec='1 kΩ 1% 2512, 1 W',
    footprint='Resistor_SMD:R_2512_6332Metric')
cap('C35', '1u', 'V12_FLT', 'GND', 'filtr 12 V przed sumą (Z14)', 'CL21B105KBFNNNE', spec='1 µF 50 V X7R 0805')
part('D10', 'Device:D_Zener', 'BZT52C33', 'Diode_SMD:D_SOD-123', {1: 'V12_FLT', 2: 'GND'},
     mpn='BZT52C33-7-F', manufacturer='Diodes Incorporated', spec='Zener 33 V (31–35 V), SOD-123',
     note='VIN LTC2955 ≤35 V (praca do 36 V); przy 24–28,8 V nie przewodzi')
cap('C36', '100n', 'VCTL', 'GND', 'VIN U6', 'CL21B104KBCNNNC', spec='100 nF 50 V X7R 0805')
part('U6', 'WICI:LTC2955-2', 'LTC2955ITS8-2', 'Package_TO_SOT_SMD:TSOT-23-8',
     {1: 'PWR_ON', 2: 'PWR_KILL', 3: 'PWR_TMR', 4: 'GND', 5: 'PWR_PB', 6: 'VCTL', 7: 'PWR_ENB', 8: 'PWR_INT'},
     mpn='LTC2955ITS8-2#TRPBF', manufacturer='Analog Devices', spec='sterownik przycisku zasilania 1,5–36 V, TSOT-23-8',
     note='włączenie przyciskiem albo zboczem narastającym ON (powrót 12 V); pinout TS8 z karty rew. A, s. 3')
# Automatic start from 12 V (elektronika.md, "Stany zasilania 12 V"): a rising edge on ON (0.76-0.84 V)
# turns the station on; in TS8 the falling edge does nothing, and a steady high ON does not restart it
# after a manual off. 309k / 30.1k at 0.1 %: 8.56 V at the lowest threshold, 9.01 V nominal, 9.46 V at the
# highest, below any working 12 V source, so every connection or return of 12 V crosses it. The threshold may
# lie under the UV rising threshold: the controller stays on (KILL from the ON rail, Q11) and U5 joins 12 V
# once it rises above about 11.9 V. 35 uA from 12 V while connected; D13 leakage (about 1 uA hot) on the
# 27.4 kOhm node raises it by about 0.3 V.
res('R70', '309k', 'V12_F', 'PWR_ON', 'samoczynne włączenie przy podłączeniu i powrocie 12 V: 8,56–9,46 V',
    **precise('309 kΩ', 'RT0805BRD07309KL'))
res('R71', '30k1', 'PWR_ON', 'GND', 'dolny rezystor dzielnika ON', **precise('30,1 kΩ', 'RT0805BRD0730K1L'))
cap('C53', '470n', 'PWR_ON', 'GND', 'filtr ON (około 13 ms) przeciw zakłóceniom z przewodu 12 V', 'CL21B474KBFNNNE',
    spec='470 nF 50 V X7R 0805')
part('D13', 'Device:D_Schottky', 'BAT54H', 'Diode_SMD:D_SOD-323', {1: 'PWR_ON', 2: 'GND'}, mpn='BAT54HT1G',
     manufacturer='onsemi', spec='dioda Schottky 30 V, SOD-323', note='ON ≥ −0,3 V przy odwrotnym 12 V (karta: −0,3 V)')
cap('C37', '2u2', 'PWR_TMR', 'GND', 'wymuszone wyłączenie po 5,2–19 s przytrzymania', 'CL21B225KAFNNNE',
    spec='2,2 µF 25 V X7R 0805')
part('J3', 'Connector_Generic:Conn_01x02', 'WYLACZNIK', XH2, {1: 'PWR_PB', 2: 'GND'}, mpn='B2B-XH-A(LF)(SN)',
     manufacturer='JST', spec='złącze 2-pin, 2,5 mm, THT', note='przewód do przycisku zasilania w panelu')
res('R47', '10k', '+3V3', 'PWR_INT', 'podciągnięcie INT (otwarty dren)', 'RC0805FR-0710KL')
part('Q8', 'Transistor_FET:BSS84', 'BSS84AK', SOT23, {1: 'Q8_G', 2: 'VCTL', 3: 'ON'},
     mpn='BSS84AK', manufacturer='Nexperia', spec='P-MOSFET −50 V, SOT-23', note='szyna ON z sumy diodowej')
res('R49', '1M', 'VCTL', 'Q8_G', 'bramka Q8 do źródła; wyłączony EN̄ i tak wisi na VIN przez 900 kΩ w U6', 'RC0805FR-071ML')
res('R50', '100k', 'Q8_G', 'PWR_ENB', 'EN̄ do bramki Q8: |VGS| = 91% VCTL, około 3 V przy ogniwach 4 V', 'RC0805FR-07100KL')
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
     manufacturer='Diodes Incorporated', spec='Zener 5,1 V, SOD-123', note='KILL ≤6 V (karta) przy VCTL do około 35 V')
part('Q11', 'Transistor_FET:2N7002', '2N7002', SOT23, {1: 'KILL_MCU', 2: 'GND', 3: 'PWR_KILL'},
     mpn='2N7002-7-F', manufacturer='Diodes Incorporated', spec='N-MOSFET 60 V, SOT-23',
     note='MCU wyłącza stację; GPIO nie widzi napięcia KILL, więc nie zasila MCU przez diody ochronne')
res('R72', '100k', 'KILL_MCU', 'GND', 'Q11 wyłączony przy resecie i bez zasilania MCU', 'RC0805FR-07100KL')

# RUN of the 3V3 converter must stay <= VIN + 0.3 V, so it is switched from VSYS (Q9) and not taken
# from ON, which follows the 12 V side even when the switch is open. The 0.5 uA RUN hysteresis current
# times R55 gives 0.11 V, below the RUN threshold, so the converter does switch off.
part('Q9', 'Transistor_FET:BSS84', 'BSS84AK', SOT23, {1: 'Q9_G', 2: 'VSYS', 3: 'RUN'},
     mpn='BSS84AK', manufacturer='Nexperia', spec='P-MOSFET −50 V, SOT-23', note='RUN przetwornicy z VSYS')
res('R51', '1M', 'VSYS', 'Q9_G', 'Q9 wyłączony bez sterowania', 'RC0805FR-071ML')
part('Q10', 'Transistor_FET:2N7002', '2N7002', SOT23, {1: 'Q10_G', 2: 'GND', 3: 'Q9_G'},
     mpn='2N7002-7-F', manufacturer='Diodes Incorporated', spec='N-MOSFET 60 V, SOT-23', note='klucz Q9 z szyny ON')
res('R53', '100k', 'ON', 'Q10_G', 'ON na bramkę Q10', 'RC0805FR-07100KL')
res('R54', '1M', 'Q10_G', 'GND', 'Q10 wyłączony bez ON; przy ogniwach około 4 V ON ≈ 3,3 V, więc VGS ≈ 3 V (próg 2N7002 do 2,5 V)',
    'RC0805FR-071ML')
zener15('D14', 'Q10_G', 'GND', 'VGS Q10 ≤15 V przy ON do około 35 V')
res('R55', '220k', 'RUN', 'GND', 'RUN niski przy wyłączonym Q9', 'RC0805FR-07220KL')
cap('C52', '1n', 'RUN', 'GND', 'filtr RUN (karta LTC3115-1: 1000 pF, nie więcej)', 'CL21B102KBANNNC',
    spec='1 nF 50 V X7R 0805')

# --- VSYS and the 3V3 converter: LTC3115-1, values of the JLC test board (hardware/przetwornica-3v3) ---------
part('C50', 'Device:C_Polarized', '100u 25V', 'Capacitor_THT:CP_Radial_D8.0mm_P3.50mm', {1: 'VSYS', 2: 'GND'},
     spec='elektrolit o małym upływie 100 µF 25 V (np. Nichicon UKL)',
     note='kondensator szyny: przełączenie 12 V ↔ ogniwa bez restartu; wartość i część z próby toru ogniw')
part('U7', 'WICI:LTC3115-1', 'LTC3115-1', 'WICI:LTC3115-1_FE20_CA',
     {1: 'GND', 2: 'RUN', 3: 'CONV_SW2', 4: '+3V3', 5: 'GND', 6: 'GND', 7: 'CONV_VC', 8: 'CONV_FB', 9: 'CONV_RT',
      10: 'GND', 11: 'GND', 12: 'CONV_VCC', 13: 'VSYS', 14: 'CONV_VCC', 15: 'CONV_BST2', 16: 'CONV_BST1',
      17: 'VSYS', 18: 'CONV_SW1', 19: 'PWM_SYNC', 20: 'GND', 21: 'GND'},
     mpn='LTC3115EFE-1#PBF', manufacturer='Analog Devices', spec='przetwornica podwyższająco-obniżająca 2,7–40 V, TSSOP-20 EP',
     note='LCSC C580689 (pula extended); footprint z generatora płytki testowej; czeka na pomiar sprawności (Z11)')
part('L2', 'Device:L', '15u', 'WICI:L_Bourns_SRP1038A', {1: 'CONV_SW2', 2: 'CONV_SW1'}, mpn='SRP1038A-150M',
     manufacturer='Bourns', spec='15 µH, Isat ≥2 A, 40/45 mΩ', note='LCSC C780183')
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

HOLES = ['H1', 'H2', 'H3', 'H4']
for ref in HOLES:
    part(ref, 'Mechanical:MountingHole', 'M3', 'MountingHole:MountingHole_3.2mm_M3', {}, bom=False,
         note='położenie i liczba z obudowy (Hammond 1599KBAT, pomiar)')

EXTRAS = [
    ('JP3', 1, 'Würth Elektronik', '60900213421', 'zworka 2,54 mm', 'założona w pracy; zdjęta przy pomiarze prądu radia'),
    ('SW1-SW4', 4, 'Omron', 'B32-1310', 'nasadka przycisku B3F, czarna', ''),
    ('ekran w J7', 1, 'Sharp', 'LS027B7DH01A', 'panel pamięciowy LCD 2,7 cala, 400 × 240', 'ekranem do góry'),
    ('J8, J9', 1, 'Seeed', '102010611 (Wio z zestawu)', 'moduł Wio SX1262 z listwami 1x7', 'antena przez u.FL i przewód do SMA'),
    ('J5, J6', 1, 'Espressif', 'ESP32-S3-DevKitC-1-N8R8', 'płytka MCU v1.1', 'zasilana przez piny 3V3'),
    ('F1', 1, 'Schurter', '0001.2504', 'bezpiecznik T1A 5x20 mm', 'wkładany do oprawki F1'),
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
