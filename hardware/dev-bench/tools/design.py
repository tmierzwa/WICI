# SPDX-License-Identifier: MIT
"""Single source of the N1 carrier: parts, physical pins, nets and placement.

Board-local millimetres, x to the right and y down, origin at the top-left
board corner. Arduino positions come from the Uno R3 pin grid confirmed by
the nRF52840-DK PCA10056 3.0.3 pick-and-place file (Arduino frame: origin at
the lower-left Uno outline corner, y up). CC1120EM connector positions come
from the TI swrr091 CADSTAR archive. This data does not validate the circuit.
"""

BOARD_W, BOARD_H = 170.0, 100.0

# Arduino Uno outline on the carrier: x_u in 0..68.58, y_u in 0..53.34.
UNO_X, UNO_Y0 = BOARD_W - 68.58, 76.34


def uno(x_u, y_u):
    """Arduino frame (y up) to board frame (y down)."""
    return round(UNO_X + x_u, 4), round(UNO_Y0 - y_u, 4)


# CC1120EM (39.38 x 35.60 mm) lower-left corner in the Arduino frame. In the
# module top view the contact rows of P1 sit at x 3.937 (odd) and 5.207 (even)
# mm, pin 1 at y 15.38 mm, pin 19 at y 3.95 mm; P2 is 30.48 mm to the right.
EM_X_U, EM_Y_U = 4.5, 6.0
EM_W, EM_H = 39.38, 35.60
EM_P1 = uno(EM_X_U + 3.937, EM_Y_U + 15.38)
EM_P2 = (round(EM_P1[0] + 30.48, 4), EM_P1[1])
EM_SMA = uno(EM_X_U + 34.01, EM_Y_U + 27.24)

# ESP32-S3-DevKitC-1: header rows 22.86 mm apart, pin 1 at the antenna end,
# pin 22 7.96 mm from the USB end. USB end 1 mm inside the bottom edge.
DEVKIT_X = 73.5
DEVKIT_USB_Y = BOARD_H - 1.0
DEVKIT_PIN22_Y = round(DEVKIT_USB_Y - 7.96, 4)
DEVKIT_PIN1_Y = round(DEVKIT_PIN22_Y - 21 * 2.54, 4)
DEVKIT_J1_X, DEVKIT_J3_X = DEVKIT_X + 1.27, DEVKIT_X + 24.13

# Sharp LS027B7DH01A panel (62.8 x 42.82 x 1.64 mm, Sharp LCP-2110015A figure 8-1)
# display side up on 0.8 mm foam tape; top-left glass corner. Its FPC leaves the
# bottom edge on the panel centre line, 6.06 mm long, contacts on the back side,
# so it lies flat in a bottom-contact connector (Sharp recommends CFP-4610 for a
# flat FPC). Seen from the display side, terminal 1 (SCLK) is the right-hand
# contact. The connector front face sits FPC_GAP from the glass edge, which leaves
# about 3.8 mm of the FPC inside the connector (check at the fit print).
PANEL_X, PANEL_Y = 8.6, 4.0
PANEL_W, PANEL_H = 62.8, 42.82
FPC_GAP = 2.3
# Hirose FH12-10S-0.5SH: pads at y -1.85, front face (FPC entry) at y +4.4 in the
# footprint; rotated 180 degrees the entry faces the panel and pad 1 is on the right.
FPC_ORIGIN = (round(PANEL_X + PANEL_W / 2, 4), round(PANEL_Y + PANEL_H + FPC_GAP + 4.4, 4))

R0805 = 'Resistor_SMD:R_0805_2012Metric'
C0805 = 'Capacitor_SMD:C_0805_2012Metric'

PARTS = []


def part(ref, lib_id, value, footprint, nets, place, *, mpn='', manufacturer='',
         spec='', note='', variant='AB', bom=True):
    """Record one board item. place = (x, y, rotation) of the footprint origin."""
    PARTS.append(dict(ref=ref, lib_id=lib_id, value=value, footprint=footprint,
                      nets={str(k): v for k, v in nets.items()}, place=place,
                      mpn=mpn, manufacturer=manufacturer, spec=spec, note=note,
                      variant=variant, bom=bom))


# Rotation 90 turns a vertical 1xN socket so its pins run to +x, 270 to -x.
# Samtec SSQ with lead style -03: 8.51 mm body, 10.00 mm tails into the DK sockets.
def stack(n):
    return dict(mpn=f'SSQ-1{n:02d}-03-T-S', manufacturer='Samtec',
                spec=f'gniazdo 1x{n}, 2,54 mm, przelotowe z długimi wyprowadzeniami 10,0 mm (stacking), cyna',
                note='wyprowadzenia od spodu wchodzą w gniazda Arduino nRF52840-DK')


part('J1', 'Connector_Generic:Conn_01x08', 'ARDUINO POWER',
     'Connector_PinSocket_2.54mm:PinSocket_1x08_P2.54mm_Vertical',
     {4: '+3V3', 5: '+5V', 6: 'GND', 7: 'GND'}, (*uno(27.94, 2.54), 90),
     **stack(8))
part('J2', 'Connector_Generic:Conn_01x06', 'ARDUINO A0-A5',
     'Connector_PinSocket_2.54mm:PinSocket_1x06_P2.54mm_Vertical',
     {1: 'RF_GPIO0', 2: 'RF_CS', 3: 'RF_GPIO1', 4: 'RF_GPIO2', 5: 'VTEST', 6: 'RF_GPIO3'},
     (*uno(50.8, 2.54), 90), **stack(6))
part('J3', 'Connector_Generic:Conn_01x08', 'ARDUINO D0-D7',
     'Connector_PinSocket_2.54mm:PinSocket_1x08_P2.54mm_Vertical',
     {1: 'BTN_UP', 2: 'BTN_DOWN', 3: 'BUZZER', 4: 'SPI_SCK_DK', 5: 'LCD_CS',
      7: 'LCD_EXTCOMIN', 8: 'RF_RESET'},
     (*uno(63.5, 50.8), 270), **stack(8))
part('J4', 'Connector_Generic:Conn_01x10', 'ARDUINO D8-SCL',
     'Connector_PinSocket_2.54mm:PinSocket_1x10_P2.54mm_Vertical',
     {1: 'LCD_DISP', 2: 'FRAM_CS', 3: 'LED_ALARM', 4: 'SPI_MOSI', 5: 'SPI_MISO',
      6: 'SW_CISZA', 7: 'GND', 8: 'BTN_PREP', 9: 'BTN_OK', 10: 'BTN_BACK'},
     (*uno(41.656, 50.8), 270), **stack(10))

EM = dict(mpn='TFM-110-01-L-D', manufacturer='Samtec',
          spec='listwa Tiger Eye 2x10, 1,27 mm, przewlekana (styl -01), partner gniazd SFM-110-02-S-D-A '
               'modułu według karty Samtec F-226 (wysokość po złączeniu z SFM-02 do pomiaru)',
          variant='A', note='moduł CC1120EM-868-915 wpina się od góry; pin 1 od strony SMA modułu')
part('J9', 'Connector_Generic:Conn_02x10_Odd_Even', 'CC1120EM P1',
     'Connector_PinHeader_1.27mm:PinHeader_2x10_P1.27mm_Vertical',
     {1: 'GND', 10: 'RF_GPIO0', 12: 'RF_GPIO2', 14: 'RF_CS', 16: 'SPI_SCK',
      18: 'SPI_MOSI', 19: 'GND', 20: 'SPI_MISO'}, (*EM_P1, 0), **EM)
part('J10', 'Connector_Generic:Conn_02x10_Odd_Even', 'CC1120EM P2',
     'Connector_PinHeader_1.27mm:PinHeader_2x10_P1.27mm_Vertical',
     {2: 'GND', 7: '+3V3_RF', 9: '+3V3_RF', 15: 'RF_RESET', 18: 'RF_GPIO3'}, (*EM_P2, 0), **EM)

DEVKIT = dict(mpn='PPTC221LFBN-RC', manufacturer='Sullins',
              spec='gniazdo żeńskie 1x22, 2,54 mm, proste, THT', variant='B',
              note='ESP32-S3-DevKitC-1 wpina się od góry; pin 1 od strony anteny')
part('J5', 'Connector_Generic:Conn_01x22', 'DEVKITC J1',
     'Connector_PinSocket_2.54mm:PinSocket_1x22_P2.54mm_Vertical',
     {1: '+3V3_DEVKIT', 2: '+3V3_DEVKIT', 4: 'RF_GPIO2', 5: 'VTEST', 6: 'BTN_PREP', 7: 'LCD_CS',
      8: 'BUZZER', 9: 'LCD_DISP', 10: 'LCD_EXTCOMIN', 11: 'LED_ALARM', 12: 'FRAM_CS',
      15: 'RF_RESET', 16: 'RF_CS', 17: 'SPI_MOSI', 18: 'SPI_SCK_DEVKIT', 19: 'SPI_MISO',
      20: 'RF_GPIO0', 21: '+5V_DEVKIT', 22: 'GND'},
     (DEVKIT_J1_X, DEVKIT_PIN1_Y, 0), **DEVKIT)
part('J6', 'Connector_Generic:Conn_01x22', 'DEVKITC J3',
     'Connector_PinSocket_2.54mm:PinSocket_1x22_P2.54mm_Vertical',
     {1: 'GND', 4: 'SW_CISZA', 5: 'BTN_BACK', 6: 'RF_GPIO3', 7: 'BTN_UP', 8: 'BTN_DOWN',
      9: 'BTN_OK', 18: 'RF_GPIO1', 21: 'GND', 22: 'GND'},
     (DEVKIT_J3_X, DEVKIT_PIN1_Y, 0), **DEVKIT)

# Panel terminals (LCP-2110015A table 4-1): 1 SCLK, 2 SI, 3 SCS, 4 EXTCOMIN, 5 DISP,
# 6 VDDA, 7 VDD, 8 EXTMODE (to VDD: VCOM from EXTCOMIN), 9 VSS, 10 VSSA. VDD from the board's own
# 5 V boost U2, not from the MCU board's 5 V pin (DevKitC gives 4.6-4.8 V behind a diode).
part('J7', 'Connector_Generic_MountingPin:Conn_01x10_MountingPin', 'SHARP LS027B7DH01A',
     'Connector_FFC-FPC:Hirose_FH12-10S-0.5SH_1x10-1MP_P0.50mm_Horizontal',
     {1: 'SPI_SCK', 2: 'SPI_MOSI', 3: 'LCD_CS', 4: 'LCD_EXTCOMIN', 5: 'LCD_DISP', 6: '+5V_LCD', 7: '+5V_LCD',
      8: '+5V_LCD', 9: 'GND', 10: 'GND', 'MP': 'GND'}, (*FPC_ORIGIN, 180),
     mpn='FH12-10S-0.5SH(55)', manufacturer='Hirose',
     spec='złącze FPC 10-pin, 0,5 mm, styki od dołu, FPC 0,3 mm, SMD',
     note='panel Sharp LS027B7DH01A ekranem do góry, taśma FPC płasko; styk 1 panelu (SCLK) na padzie 1 po prawej')
part('U1', 'Memory_NVRAM:MB85RS2MT', 'CY15B104QN-50SXI', 'Package_SO:SOIC-8_5.3x5.3mm_P1.27mm',
     {1: 'FRAM_CS_U1', 2: 'SPI_MISO', 3: '+3V3', 4: 'GND', 5: 'SPI_MOSI', 6: 'SPI_SCK', 7: '+3V3', 8: '+3V3'},
     (86.0, 12.0, 0), mpn='CY15B104QN-50SXI', manufacturer='Infineon',
     spec='FRAM 4 Mbit SPI, 1,8–3,6 V, SOIC-8 208 mil',
     note='zamiennik na tym samym footprincie: RAMXEED MB85RS4MTPF-G-BCERE1; pin 7 (HOLD albo RESET) i WP na stałe do 3,3 V')
# FRAM guard (elektronika.md, "Zanik zasilania i zapis", point 2): below 2.66-2.74 V the supervisor U3
# forces CS of U1 high through the OR gate U4, whatever the MCU drives. The board cannot use the MCU
# reset for this: the Arduino RESET pin of nRF52840-DK is not connected (R45 not fitted, PCA10056 BOM).
part('U3', 'WICI:TPS3840PH', 'TPS3840PH27', 'Package_TO_SOT_SMD:SOT-23-5',
     {1: 'FRAM_GUARD', 2: '+3V3', 3: 'GND'}, (77.5, 14.0, 0),
     mpn='TPS3840PH27DBVR', manufacturer='Texas Instruments',
     spec='nadzorca napięcia, próg 2,7 V ±1,5%, histereza 75–125 mV, wyjście push-pull aktywne stanem wysokim, SOT-23-5',
     note='RESET = H, gdy +3V3 < 2,66–2,74 V; MR (4) i CT (5) wolne: opóźnienie startu ≤350 µs bez kondensatora')
part('U4', '74xGxx:74LVC1G32', '74LVC1G32', 'Package_TO_SOT_SMD:SOT-23-5',
     {1: 'FRAM_CS', 2: 'FRAM_GUARD', 3: 'GND', 4: 'FRAM_CS_U1', 5: '+3V3'}, (77.5, 8.0, 0),
     mpn='SN74LVC1G32DBVR', manufacturer='Texas Instruments', spec='bramka OR 1-kanałowa, 1,65–5,5 V, SOT-23-5',
     note='CS FRAM = CS z MCU lub RESET z U3: przy spadku zasilania FRAM niewybrana niezależnie od MCU')
part('J11', 'Connector_Generic:Conn_01x09', 'ANALIZATOR',
     'Connector_PinHeader_2.54mm:PinHeader_1x09_P2.54mm_Vertical',
     {1: 'GND', 2: 'SPI_SCK', 3: 'SPI_MOSI', 4: 'SPI_MISO', 5: 'RF_CS', 6: 'FRAM_CS',
      7: 'LCD_CS', 8: 'RF_GPIO0', 9: 'RF_GPIO2'}, (105.0, 91.0, 90),
     mpn='61300911121', manufacturer='Würth Elektronik', spec='listwa męska 1x9, 2,54 mm, THT',
     note='analizator stanów logicznych (8 kanałów); pin 1 = GND')
part('JP1', 'Connector_Generic:Conn_01x02', '3V3 DEVKITC',
     'Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical',
     {1: '+3V3', 2: '+3V3_DEVKIT'}, (89.0, 26.5, 90),
     mpn='61300211121', manufacturer='Würth Elektronik', spec='listwa męska 1x2, 2,54 mm, ze zworką',
     note='założona tylko w stanowisku B; pomiar prądu 3,3 V')
part('JP2', 'Connector_Generic:Conn_01x02', '5V DEVKITC',
     'Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical',
     {1: '+5V', 2: '+5V_DEVKIT'}, (70.6, 80.0, 0),
     mpn='61300211121', manufacturer='Würth Elektronik', spec='listwa męska 1x2, 2,54 mm, ze zworką',
     note='założona tylko w stanowisku B; zasila brzęczyk, pomiar prądu 5 V')
part('JP3', 'Connector_Generic:Conn_01x02', '3V3 RADIO A',
     'Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical',
     {1: '+3V3', 2: '+3V3_RF'}, (131.0, 88.0, 90),
     mpn='61300211121', manufacturer='Würth Elektronik', spec='listwa męska 1x2, 2,54 mm, ze zworką',
     note='założona w stanowisku A (zasila CC1120EM); amperomierz zamiast zworki mierzy prąd radia '
          '(zakres ≥200 mA); poza obrysem X-NUCLEO, bo listwa ze zworką (8,9 mm) sięga spodu nakładki w stanowisku B')
part('J12', 'Connector:Screw_Terminal_01x02', 'VTEST 0-15V',
     'TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal',
     {1: 'VTEST_IN', 2: 'GND'}, (150.0, 92.0, 0),
     mpn='1715721', manufacturer='Phoenix Contact', spec='zacisk śrubowy 2-pin, 5,08 mm',
     note='napięcie z zasilacza laboratoryjnego do prób progów ogniw i 12 V; najwyżej 15 V')

BUTTONS = [('SW1', 'GÓRA', 'BTN_UP', 14.0), ('SW2', 'DÓŁ', 'BTN_DOWN', 30.0),
           ('SW3', 'OK', 'BTN_OK', 46.0), ('SW4', 'WSTECZ', 'BTN_BACK', 62.0)]
for ref, label, net, cx in BUTTONS:
    part(ref, 'Switch:SW_Push', label, 'Button_Switch_THT:SW_SPST_Omron_B3F-40xx',
         {1: net, 2: 'GND'}, (cx - 6.25, 67.5, 0), mpn='B3F-4055', manufacturer='Omron',
         spec='przycisk 12x12 mm z wysuniętym popychaczem, nasadka Omron B32-1310',
         note='pady 1 wspólne (12,5 mm), pady 2 wspólne; zestyk między grupami 1 i 2')
part('SW5', 'Switch:SW_SPDT', 'CISZA', 'WICI:Toggle_ESwitch_100SP1T1B4M2QE',
     {1: 'GND', 2: 'SW_COM'}, (14.0, 89.0, 0), mpn='100SP1T1B4M2QE', manufacturer='E-Switch',
     spec='przełącznik dźwigienkowy SPDT ON-NONE-ON, wyprowadzenia PCB 4,70 mm',
     note='zwarte 1-2 = cisza radiowa (SW_CISZA = L); 2-3 = praca')
part('SW6', 'Switch:SW_Push', 'PRZYGOTOWANIE', 'Button_Switch_THT:SW_TH_Tactile_Omron_B3F-100x',
     {1: 'BTN_PREP', 2: 'GND'}, (25.0, 86.75, 0), mpn='B3F-1000', manufacturer='Omron',
     spec='przycisk 6x6 mm', note='na stacji pod plombowaną pokrywą')
part('D1', 'Device:LED', 'ALARM', 'LED_THT:LED_D5.0mm', {1: 'GND', 2: 'LED_A'}, (36.0, 89.0, 0),
     mpn='WP7113ID', manufacturer='Kingbright', spec='LED 5 mm czerwona, rozproszona',
     note='katoda (pad kwadratowy 1) do masy')
part('R1', 'Device:R', '1k', R0805, {1: 'LED_ALARM', 2: 'LED_A'}, (37.3, 83.5, 0),
     mpn='RC0805FR-071KL', manufacturer='Yageo', spec='1 kΩ 1% 0805', note='prąd diody około 1 mA')
part('BZ1', 'Device:Buzzer', 'CEM-1203(42)', 'Buzzer_Beeper:MagneticBuzzer_ProSignal_ABT-410-RC',
     {1: 'BZ_P', 2: 'BZ_N'}, (46.0, 89.0, 0), mpn='CEM-1203(42)', manufacturer='Same Sky (CUI Devices)',
     spec='brzęczyk magnetyczny 12 mm, sterowany z zewnątrz, 2048 Hz, cewka 42 Ω',
     note='pad 1 = "+"; sprawdzić znak "+" na obudowie przy montażu')
part('R2', 'Device:R', '22R', 'Resistor_SMD:R_1206_3216Metric', {1: '+5V', 2: 'BZ_P'}, (46.0, 81.0, 0),
     mpn='RC1206FR-0722RL', manufacturer='Yageo', spec='22 Ω 1% 1206, 0,25 W',
     note='brzęczyk z +5V, nie z szyny radia; około 3,3 V szczytowo na cewce, najwyżej około 75 mA przy stałym stanie wysokim BUZZER')
part('D2', 'Device:D', '1N4148W', 'Diode_SMD:D_SOD-123', {1: 'BZ_P', 2: 'BZ_N'}, (52.0, 81.0, 180),
     mpn='1N4148W-7-F', manufacturer='Diodes Incorporated', spec='dioda 75 V, SOD-123',
     note='dioda gasząca cewki brzęczyka')
part('Q1', 'Transistor_BJT:MMBT3904', 'MMBT3904', 'Package_TO_SOT_SMD:SOT-23',
     {1: 'Q_B', 2: 'GND', 3: 'BZ_N'}, (58.0, 84.0, 0), mpn='MMBT3904LT1G', manufacturer='onsemi',
     spec='NPN 40 V 200 mA, SOT-23', note='klucz brzęczyka')
part('R3', 'Device:R', '1k', R0805, {1: 'BUZZER', 2: 'Q_B'}, (58.0, 79.0, 0),
     mpn='RC0805FR-071KL', manufacturer='Yageo', spec='1 kΩ 1% 0805', note='rezystor bazy Q1')
part('R4', 'Device:R', '100k', R0805, {1: 'Q_B', 2: 'GND'}, (63.0, 84.0, 90),
     mpn='RC0805FR-07100KL', manufacturer='Yageo', spec='100 kΩ 1% 0805',
     note='Q1 wyłączony, gdy MCU nie steruje linią BUZZER')

part('R16', 'Device:R', '1k', R0805, {1: 'SW_COM', 2: 'SW_CISZA'}, (19.5, 81.0, 0),
     mpn='RC0805FR-071KL', manufacturer='Yageo', spec='1 kΩ 1% 0805',
     note='SW_CISZA przez 1 kΩ: wyjście MCU na tej linii nie zwiera się do masy (0,3 V przy ciszy)')
part('R17', 'Device:R', '33R', R0805, {1: 'SPI_SCK_DK', 2: 'SPI_SCK'}, (158.3, 29.5, 90),
     mpn='RC0805FR-0733RL', manufacturer='Yageo', spec='33 Ω 1% 0805',
     note='szeregowy SCK przy złączu Arduino D3: łagodzi zbocza na rozgałęzionej sieci')
part('R18', 'Device:R', '33R', R0805, {1: 'SPI_SCK_DEVKIT', 2: 'SPI_SCK'}, (79.0, 80.88, 0),
     mpn='RC0805FR-0733RL', manufacturer='Yageo', spec='33 Ω 1% 0805',
     note='szeregowy SCK przy GPIO12 DevKitC')
part('R19', 'Device:R', '10k', R0805, {1: 'LCD_DISP', 2: 'GND'}, (FPC_ORIGIN[0] + 13.0, FPC_ORIGIN[1] - 2.0, 90),
     mpn='RC0805FR-0710KL', manufacturer='Yageo', spec='10 kΩ 1% 0805',
     note='DISP = L do startu MCU: ekran biały, pamięć obrazu zachowana')
part('R20', 'Device:R', '10k', R0805, {1: '+3V3', 2: 'FRAM_CS'}, (86.0, 18.5, 0),
     mpn='RC0805FR-0710KL', manufacturer='Yageo', spec='10 kΩ 1% 0805',
     note='FRAM niewybrana przed startem MCU')
part('D3', 'Diode:BAT54S', 'BAT54S', 'Package_TO_SOT_SMD:SOT-23', {1: 'GND', 2: '+3V3', 3: 'VTEST'},
     (163.5, 87.5, 0), mpn='BAT54SLT1G', manufacturer='onsemi', spec='podwójna dioda Schottky 30 V, SOT-23',
     note='ogranicza VTEST do zakresu -0,3...+3,6 V przy odwrotnej polaryzacji albo za wysokim napięciu J12')

PULLUPS = [('R5', 'BTN_UP', (14.0, 61.0)), ('R6', 'BTN_DOWN', (30.0, 61.0)),
           ('R7', 'BTN_OK', (46.0, 61.0)), ('R8', 'BTN_BACK', (62.0, 61.0)),
           ('R9', 'SW_CISZA', (14.0, 81.0)), ('R10', 'BTN_PREP', (28.25, 81.0))]
for ref, net, (x, y) in PULLUPS:
    part(ref, 'Device:R', '10k', R0805, {1: '+3V3', 2: net}, (x, y, 0),
         mpn='RC0805FR-0710KL', manufacturer='Yageo', spec='10 kΩ 1% 0805', note='podciągnięcie wejścia')
part('R11', 'Device:R', '10k', R0805, {1: '+3V3', 2: 'RF_CS'}, (148.0, 62.0, 90),
     mpn='RC0805FR-0710KL', manufacturer='Yageo', spec='10 kΩ 1% 0805',
     note='radio niewybrane przed startem MCU')
part('R12', 'Device:R', '10k', R0805, {1: 'RF_RESET', 2: 'GND'}, (151.0, 62.0, 90),
     mpn='RC0805FR-0710KL', manufacturer='Yageo', spec='10 kΩ 1% 0805',
     note='A: CC1120 w resecie do startu MCU; B: S2-LP włączony (SDN = L)')
part('R13', 'Device:R', '10k', R0805, {1: 'LCD_CS', 2: 'GND'}, (FPC_ORIGIN[0] - 13.0, FPC_ORIGIN[1] - 2.0, 90),
     mpn='RC0805FR-0710KL', manufacturer='Yageo', spec='10 kΩ 1% 0805',
     note='ściąga LCD_CS do masy; CS ekranu jest aktywny stanem wysokim')
part('R14', 'Device:R', '100k', R0805, {1: 'VTEST_IN', 2: 'VTEST'}, (158.5, 82.0, 0),
     mpn='RT0805BRD07100KL', manufacturer='Yageo', spec='100 kΩ 0,1% 25 ppm/K 0805',
     note='górny rezystor dzielnika VTEST; 0,1%, bo dzielnik z rezystorów 1% sam dawał do ±1,7% błędu skali')
part('R15', 'Device:R', '20k', R0805, {1: 'VTEST', 2: 'GND'}, (163.0, 82.0, 90),
     mpn='RT0805BRD0720KL', manufacturer='Yageo', spec='20 kΩ 0,1% 25 ppm/K 0805',
     note='VTEST = VTEST_IN / 6 (±0,17% z tolerancji); 15 V daje 2,5 V')
part('C1', 'Device:C', '10u', C0805, {1: '+3V3_RF', 2: 'GND'}, (148.0, 57.0, 90),
     mpn='CL21A106KAYNNNG', manufacturer='Samsung Electro-Mechanics', spec='10 µF 25 V X5R 0805',
     note='+3V3_RF przy module CC1120EM')
part('C2', 'Device:C', '100n', C0805, {1: '+3V3_RF', 2: 'GND'}, (151.0, 57.0, 90),
     mpn='CL21B104KBCNNNC', manufacturer='Samsung Electro-Mechanics', spec='100 nF 50 V X7R 0805',
     note='+3V3_RF przy module CC1120EM')
part('C3', 'Device:C', '100n', C0805, {1: '+3V3', 2: 'GND'}, (92.5, 12.0, 90),
     mpn='CL21B104KBCNNNC', manufacturer='Samsung Electro-Mechanics', spec='100 nF 50 V X7R 0805',
     note='+3V3 przy FRAM U1')
part('C11', 'Device:C', '100n', C0805, {1: '+3V3', 2: 'GND'}, (77.5, 4.0, 90),
     mpn='CL21B104KBCNNNC', manufacturer='Samsung Electro-Mechanics', spec='100 nF 50 V X7R 0805',
     note='+3V3 przy bramce U4')
part('C12', 'Device:C', '100n', C0805, {1: '+3V3', 2: 'GND'}, (77.5, 18.5, 90),
     mpn='CL21B104KBCNNNC', manufacturer='Samsung Electro-Mechanics', spec='100 nF 50 V X7R 0805',
     note='+3V3 przy nadzorcy U3')
# Hold-up for the FRAM guard: U3 asserts at most 30 us after +3V3 is 10 % below its threshold
# (2.394 V worst case, TI SNVSB03E table 6.6); +3V3 must stay above 2.0 V (CY15B104Q) for twice that
# at 150 mA, i.e. >= 23 uF effective counting only this board. C13 gives >= 32 uF at 3.3 V
# (40 % left after DC bias, -20 % tolerance), C8 about 6 uF more; module capacitance is not counted.
part('C13', 'Device:C', '100u', 'Capacitor_SMD:C_1210_3225Metric', {1: '+3V3', 2: 'GND'}, (77.5, 23.0, 90),
     mpn='LMK325ABJ107MM-P', manufacturer='Taiyo Yuden', spec='100 µF 10 V X5R 1210',
     note='podtrzymanie +3V3 przez czas reakcji nadzorcy U3 (budżet w plytka-nosna.md, „Zasilanie”)')
part('C4', 'Device:C', '10u', C0805, {1: '+5V_LCD', 2: 'GND'}, (FPC_ORIGIN[0] - 8.0, FPC_ORIGIN[1] - 2.0, 90),
     mpn='CL21A106KAYNNNG', manufacturer='Samsung Electro-Mechanics', spec='10 µF 25 V X5R 0805',
     note='VDD panelu (Sharp zaleca ≥1 µF)')
part('C6', 'Device:C', '100n', C0805, {1: '+5V_LCD', 2: 'GND'}, (FPC_ORIGIN[0] + 8.0, FPC_ORIGIN[1] - 2.0, 90),
     mpn='CL21B104KBCNNNC', manufacturer='Samsung Electro-Mechanics', spec='100 nF 50 V X7R 0805',
     note='VDDA panelu (Sharp zaleca ≥0,1 µF)')
part('C7', 'Device:C', '100n', C0805, {1: 'LCD_DISP', 2: 'GND'}, (FPC_ORIGIN[0] + 10.5, FPC_ORIGIN[1] - 2.0, 90),
     mpn='CL21B104KBCNNNC', manufacturer='Samsung Electro-Mechanics', spec='100 nF 50 V X7R 0805',
     note='DISP panelu (Sharp zaleca 0,1 µF)')
part('C5', 'Device:C', '100n', C0805, {1: 'VTEST', 2: 'GND'}, (165.5, 82.0, 90),
     mpn='CL21B104KBCNNNC', manufacturer='Samsung Electro-Mechanics', spec='100 nF 50 V X7R 0805',
     note='filtr wejścia ADC VTEST')


# Panel supply: Microchip MCP1640 synchronous boost (DS20002234D) from +3V3 to +5V_LCD.
# VOUT = VFB (1 + RTOP / RBOT) = 1.21 V x (1 + 1000/309) = 5.13 V; with VFB 1.175-1.245 V and 1 %
# resistors 4.90-5.36 V, inside the panel's 4.8-5.5 V. CIN >= 4.7 uF, COUT >= 10 uF, L 4.7 uH
# (Table 5-1, 5-2); 100 pF across RTOP against output spikes in PFM (section 5.4).
BOOST = (64.0, 51.0)
part('U2', 'Regulator_Switching:MCP1640x-xCHY', 'MCP1640', 'Package_TO_SOT_SMD:SOT-23-6',
     {1: 'BST_SW', 2: 'GND', 3: '+3V3', 4: 'BST_FB', 5: '+5V_LCD', 6: '+3V3'}, (*BOOST, 0),
     mpn='MCP1640T-I/CHY', manufacturer='Microchip', spec='przetwornica podwyższająca synchroniczna 0,65–5,5 V, PFM, SOT-23-6',
     note='5,1 V panelu z +3V3 (3,0 V w stanowisku A); EN na stałe do VIN')
part('L1', 'Device:L', '4u7', 'Inductor_SMD:L_Wuerth_WE-TPC-3816', {1: '+3V3', 2: 'BST_SW'},
     (BOOST[0] - 6.0, BOOST[1], 90), mpn='744031004', manufacturer='Würth Elektronik',
     spec='4,7 µH, Isat 0,9 A, 105 mΩ, ekranowana, 3,8 × 3,8 mm', note='cewka z tabeli 5-2 karty MCP1640')
part('C8', 'Device:C', '10u', C0805, {1: '+3V3', 2: 'GND'}, (BOOST[0] - 6.0, BOOST[1] + 4.5, 0),
     mpn='CL21A106KAYNNNG', manufacturer='Samsung Electro-Mechanics', spec='10 µF 25 V X5R 0805',
     note='wejście U2 (karta: ≥4,7 µF)')
part('C9', 'Device:C', '10u', C0805, {1: '+5V_LCD', 2: 'GND'}, (BOOST[0] + 4.5, BOOST[1] + 1.0, 90),
     mpn='CL21A106KAYNNNG', manufacturer='Samsung Electro-Mechanics', spec='10 µF 25 V X5R 0805',
     note='wyjście U2; razem z C4 przy panelu ≥10 µF także po spadku pojemności przy 5 V')
part('R21', 'Device:R', '1M', R0805, {1: '+5V_LCD', 2: 'BST_FB'}, (BOOST[0] + 1.0, BOOST[1] + 4.5, 0),
     mpn='RC0805FR-071ML', manufacturer='Yageo', spec='1,00 MΩ 1% 0805', note='RTOP dzielnika U2')
part('R22', 'Device:R', '309k', R0805, {1: 'BST_FB', 2: 'GND'}, (BOOST[0] + 1.0, BOOST[1] + 7.0, 0),
     mpn='RC0805FR-07309KL', manufacturer='Yageo', spec='309 kΩ 1% 0805', note='RBOT dzielnika U2')
part('C10', 'Device:C', '100p', C0805, {1: '+5V_LCD', 2: 'BST_FB'}, (BOOST[0] + 5.5, BOOST[1] + 5.75, 90),
     mpn='CL21C101JBANNNC', manufacturer='Samsung Electro-Mechanics', spec='100 pF 50 V C0G 0805',
     note='równolegle do R21 (karta MCP1640, 5.4)')

# Loose items without a footprint, listed in the BOM after the board parts.
EXTRAS = [
    ('JP1-JP3', 3, 'Würth Elektronik', '60900213421', 'zworka 2,54 mm', 'A i B',
     'stanowisko A: JP3; stanowisko B: JP1, JP2'),
    ('SW1-SW4', 4, 'Omron', 'B32-1310', 'nasadka przycisku B3F, czarna', 'A i B', ''),
    ('H1-H9', 9, '', '', 'dystans M3 × 12 mm z dwiema śrubami (w H6-H9 nylonowe, łeb śruby ≤4,4 mm)', 'A i B',
     'stanowisko B stoi na H1-H9; w A dystanse H1, H2, H5 podpierają lewą część płytki, wysokość z przymiarki'),
    ('ekran w J7', 1, 'Sharp', 'LS027B7DH01A', 'panel pamięciowy LCD 2,7 cala, 400 × 240, FPC 10-pin 0,5 mm', 'A i B',
     'w J7; ekranem do góry na taśmie piankowej, w obrysie na opisie płytki'),
    ('pod ekranem', 1, '3M', '4032', 'taśma piankowa dwustronna 0,8 mm, około 60 × 40 mm', 'A i B',
     'pod panelem; przykleja się po włożeniu FPC do J7'),
]

HOLES = [  # ref, x, y, footprint, note
    ('H1', 3.5, 3.5, 'M3'), ('H2', 3.5, 96.5, 'M3'), ('H3', 166.5, 3.5, 'M3'),
    ('H4', 166.5, 96.5, 'M3'), ('H5', 68.0, 96.5, 'M3'),
    ('H6', *uno(13.97, 2.54), 'UNO'), ('H7', *uno(15.24, 50.8), 'UNO'),
    ('H8', *uno(66.04, 7.62), 'UNO'), ('H9', *uno(66.04, 35.56), 'UNO'),
]
for ref, x, y, size in HOLES:
    fp = {'M3': 'MountingHole:MountingHole_3.2mm_M3', 'UNO': 'WICI:MountingHole_3.2mm_Arduino'}[size]
    part(ref, 'Mechanical:MountingHole', size, fp, {}, (round(x, 4), round(y, 4), 0), bom=False,
         note='otwór nieplaterowany; H6-H9 to otwory Arduino Uno R3, zgodne z otworami nRF52840-DK')

# Over male headers of the nRF52840-DK below the shield: a notch for P5 (2x3,
# ICSP position) at Arduino (64.897, 27.94) and, over P20 (1x13) at y 40.64,
# a band without any copper (pin tips may touch the underside).
NOTCH_P5 = (uno(61.0, 32.3)[0], uno(61.0, 32.3)[1], BOARD_W, uno(61.0, 23.0)[1])
SLOT_P20 = (uno(17.0, 42.1)[0], uno(17.0, 42.1)[1], uno(51.0, 39.2)[0], uno(51.0, 39.2)[1])

# Ground pads that DRC reported as starved thermals for the kept routing session.
SOLID_GND_PADS = [('J6', '22'), ('J4', '7'), ('Q1', '2')]

POWER_NETS = {'+3V3', '+3V3_RF', '+5V', '+5V_LCD', '+3V3_DEVKIT', '+5V_DEVKIT', 'GND'}
FLAGS = ['+3V3', '+3V3_RF', '+5V', '+3V3_DEVKIT', '+5V_DEVKIT', 'GND', 'VTEST_IN']
# Signal nets reached from an MCU pin through a series resistor.
SERIES = {'SPI_SCK': ('SPI_SCK_DK', 'SPI_SCK_DEVKIT')}

# Signal table for documentation: net, Arduino, nRF52840 GPIO, ESP32-S3 GPIO.
SIGNALS = [
    ('SPI_SCK', 'D3', 'P1.04', 'GPIO12'), ('SPI_MOSI', 'D11', 'P1.13', 'GPIO11'),
    ('SPI_MISO', 'D12', 'P1.14', 'GPIO13'), ('RF_CS', 'A1', 'P0.04', 'GPIO10'),
    ('RF_RESET', 'D7', 'P1.08', 'GPIO9'), ('RF_GPIO0', 'A0', 'P0.03', 'GPIO14'),
    ('RF_GPIO1', 'A2', 'P0.28', 'GPIO21'), ('RF_GPIO2', 'A3', 'P0.29', 'GPIO4'),
    ('RF_GPIO3', 'A5', 'P0.31', 'GPIO42'), ('FRAM_CS', 'D9', 'P1.11', 'GPIO8'),
    ('LCD_CS', 'D4', 'P1.05', 'GPIO7'), ('LCD_EXTCOMIN', 'D6', 'P1.07', 'GPIO17'),
    ('LCD_DISP', 'D8', 'P1.10', 'GPIO16'), ('LED_ALARM', 'D10', 'P1.12', 'GPIO18'),
    ('BUZZER', 'D2', 'P1.03', 'GPIO15'), ('BTN_UP', 'D0', 'P1.01', 'GPIO41'),
    ('BTN_DOWN', 'D1', 'P1.02', 'GPIO40'), ('BTN_OK', 'SDA', 'P0.26', 'GPIO39'),
    ('BTN_BACK', 'SCL', 'P0.27', 'GPIO2'), ('SW_CISZA', 'D13', 'P1.15', 'GPIO1'),
    ('BTN_PREP', 'AREF', 'P0.02', 'GPIO6'), ('VTEST', 'A4', 'P0.30', 'GPIO5'),
]
ARDUINO_PIN = {  # Arduino label -> (connector, pin)
    'A0': ('J2', 1), 'A1': ('J2', 2), 'A2': ('J2', 3), 'A3': ('J2', 4), 'A4': ('J2', 5), 'A5': ('J2', 6),
    'D0': ('J3', 1), 'D1': ('J3', 2), 'D2': ('J3', 3), 'D3': ('J3', 4), 'D4': ('J3', 5), 'D5': ('J3', 6),
    'D6': ('J3', 7), 'D7': ('J3', 8), 'D8': ('J4', 1), 'D9': ('J4', 2), 'D10': ('J4', 3),
    'D11': ('J4', 4), 'D12': ('J4', 5), 'D13': ('J4', 6), 'AREF': ('J4', 8), 'SDA': ('J4', 9),
    'SCL': ('J4', 10),
}
DEVKIT_GPIO = {  # (connector, pin) -> ESP32-S3 GPIO, DevKitC-1 user guide v1.1
    **{('J5', i + 1): g for i, g in enumerate(
        ['3V3', '3V3', 'EN', 'GPIO4', 'GPIO5', 'GPIO6', 'GPIO7', 'GPIO15', 'GPIO16', 'GPIO17', 'GPIO18',
         'GPIO8', 'GPIO3', 'GPIO46', 'GPIO9', 'GPIO10', 'GPIO11', 'GPIO12', 'GPIO13', 'GPIO14', '5V', 'GND'])},
    **{('J6', i + 1): g for i, g in enumerate(
        ['GND', 'GPIO43', 'GPIO44', 'GPIO1', 'GPIO2', 'GPIO42', 'GPIO41', 'GPIO40', 'GPIO39', 'GPIO38',
         'GPIO37', 'GPIO36', 'GPIO35', 'GPIO0', 'GPIO45', 'GPIO48', 'GPIO47', 'GPIO21', 'GPIO20', 'GPIO19',
         'GND', 'GND'])},
}


def check():
    """Cross-check the signal table against the connector pins."""
    nets = {}
    for p in PARTS:
        for pin, net in p['nets'].items():
            nets.setdefault(net, []).append((p['ref'], int(pin) if pin.isdigit() else pin))
    for net, ard, _nrf, gpio in SIGNALS:
        members = [m for n in (net, *SERIES.get(net, ())) for m in nets[n]]
        conn = ARDUINO_PIN[ard]
        assert conn in members, (net, ard)
        on_devkit = [DEVKIT_GPIO[c] for c in members if c[0] in ('J5', 'J6')]
        assert on_devkit == [gpio], (net, on_devkit, gpio)
    for net, members in nets.items():
        assert len(members) >= 2, ('single-pin net', net, members)
    for ref in ('J5', 'J6'):
        for pin in PARTS[[p['ref'] for p in PARTS].index(ref)]['nets']:
            assert DEVKIT_GPIO[(ref, int(pin))] not in {
                'GPIO0', 'GPIO3', 'GPIO45', 'GPIO46', 'GPIO19', 'GPIO20', 'GPIO43', 'GPIO44',
                'GPIO38', 'GPIO48', 'GPIO35', 'GPIO36', 'GPIO37', 'GPIO47'}
    return nets


if __name__ == '__main__':
    n = check()
    print(len(PARTS), 'items', len(n), 'nets')
