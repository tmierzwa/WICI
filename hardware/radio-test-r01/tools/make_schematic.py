# SPDX-License-Identifier: GPL-3.0-or-later
"""Generate an editable schematic from explicit prototype connections.

Library pin geometry comes from KiCad 9.0.0 with the R01.2 fuse, mounting
hole and power-flag additions from KiCad 10.0.6. This generator does not validate
the circuit, route a PCB, or authorize manufacturing.
"""
from copy import deepcopy
import csv
import json
import math
from pathlib import Path
import uuid
from sexpr import Atom as A, parse, dump, children, child, walk

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT.parent / 'libraries'
if not LIB.exists():
    LIB = ROOT / 'cad/symbols'
NS = uuid.UUID('467d264c-787d-4b39-8f3c-c13d337d015a')


def uid(name):
    """Give each design object a stable UUID."""
    return str(uuid.uuid5(NS, name))


def symbol(lib_id):
    """Resolve library inheritance while preserving child properties."""
    lib, name = lib_id.split(':')
    defs = {s[1]: s for s in children(parse((LIB / (lib + '.kicad_sym')).read_text()), 'symbol')}
    def resolve(key):
        own = deepcopy(defs[key])
        ext = children(own, 'extends')
        if not ext:
            return own
        base = resolve(ext[0][1])
        old = base[1]
        base[1] = key
        for s in children(base, 'symbol'):
            s[1] = key + s[1][len(old):]
        for p in children(own, 'property'):
            base[:] = [x for x in base if not (isinstance(x, list) and x[0] == 'property' and x[1] == p[1])]
            base.append(p)
        return base
    result = resolve(name)
    result[1] = lib_id
    return result


PARTS = []


def part(ref, lib_id, value, footprint, nets, at, note=''):
    """Record physical pin numbers, signal names, and schematic placement."""
    PARTS.append(dict(ref=ref, lib_id=lib_id, value=value, footprint=footprint,
                      nets={str(k): v for k, v in nets.items()}, at=at, note=note))


R = 'Resistor_SMD:R_0805_2012Metric'
C = 'Capacitor_SMD:C_0805_2012Metric'
part('U1', 'MCU_ST_STM32F1:STM32F103CBTx', 'STM32F103CBT6',
     'Package_QFP:LQFP-48_7x7mm_P0.5mm',
     {1:'V3', 5:'HSE8', 7:'NRST', 8:'GND', 9:'V3', 14:'CS_N', 15:'SCK',
      16:'MISO', 17:'MOSI', 18:'IRQ0', 19:'IRQ2', 20:'BOOT1', 21:'RF_RESET_N',
      23:'GND', 24:'V3', 25:'USB_ATTACH_N', 26:'STATUS_LED', 30:'UART_TX',
      31:'UART_RX', 32:'USB_DM_MCU', 33:'USB_DP_MCU', 34:'SWDIO', 35:'GND',
      36:'V3', 37:'SWCLK', 42:'SCL', 43:'SDA', 44:'BOOT0', 47:'GND', 48:'V3'},
     [215.9, 83.82], 'All unused GPIOs explicit NC. C8 substitution needs a verified 64 KiB build.')
part('J1', 'Connector:USB_B', 'Wuerth 61400416121', 'WICI:USB_B_61400416121',
     {1:'VBUS_USB', 2:'USB_DM', 3:'USB_DP', 4:'GND', 5:'GND'}, [35.56,35.56])
part('U2', 'Regulator_Linear:AP2112K-3.3', 'AP2112K-3.3TRG1', 'Package_TO_SOT_SMD:SOT-23-5',
     {1:'VBUS', 2:'GND', 3:'VBUS', 5:'V3'}, [109.22,35.56],
     'Alternative TLV75533PDBVR: same physical pin numbers. Pin 4 is NC.')
part('U3', 'Power_Protection:USBLC6-2SC6', 'USBLC6-2SC6', 'Package_TO_SOT_SMD:SOT-23-6',
     {1:'USB_DP', 2:'GND', 3:'USB_DM', 4:'USB_DM', 5:'VBUS_USB', 6:'USB_DP'}, [35.56,91.44])
part('Y1', 'Oscillator:ASE-xxxMHz', 'ASE-8.000MHZ-L-C-T',
     'Oscillator:Oscillator_SMD_Abracon_ASE-4Pin_3.2x2.5mm',
     {1:'V3', 2:'GND', 3:'HSE8', 4:'V3'}, [109.22,91.44],
     '8 MHz CMOS, HSE bypass mode. This is the MCU clock, not the radio clock.')
part('U4', 'Memory_EEPROM:24LC64', 'M24C64-RMN6TP', 'Package_SO:SOIC-8_3.9x4.9mm_P1.27mm',
     {1:'GND', 2:'GND', 3:'GND', 4:'GND', 5:'SDA', 6:'SCL', 7:'GND', 8:'V3'},
     [35.56,149.86], 'Generic 24LC64 symbol. M24C64-R and Microchip AT24C64D-SSHM-T need firmware qualification.')
part('Q1', 'Transistor_FET:BSS84', 'BSS84,215', 'Package_TO_SOT_SMD:SOT-23',
     {1:'USB_ATTACH_N', 2:'V3', 3:'USB_PULLUP'}, [109.22,149.86],
     'PMOS source is physical pin 2. Gate pulled high at reset; LOW attaches USB.')
part('J2', 'Connector_Generic:Conn_02x05_Odd_Even', 'RADIO 3V3 SPI',
     'WICI:IDC_61201021621',
     {1:'GND', 2:'V3', 3:'SCK', 4:'GND', 5:'MOSI', 6:'MISO', 7:'CS_N',
      8:'RF_RESET_N', 9:'IRQ0', 10:'IRQ2'}, [215.9,180.34],
     'Keyed cable <= 5 cm; all signals 3.3 V. V3 is output. Never connect another supply.')
part('J3', 'Connector_Generic:Conn_01x05', 'SWD: VTref DIO GND CLK RESET',
     'Connector_PinHeader_2.54mm:PinHeader_1x05_P2.54mm_Vertical',
     {1:'V3', 2:'SWDIO', 3:'GND', 4:'SWCLK', 5:'NRST'}, [35.56,208.28],
     'VTref is sense only: USB powers the board; programmer must not drive pin 1.')
part('J4', 'Connector_Generic:Conn_01x03', 'UART: GND TX RX',
     'Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical',
     {1:'GND', 2:'UART_TX', 3:'UART_RX'}, [109.22,208.28])
part('SW1', 'Switch:SW_Push', 'RESET', 'Button_Switch_THT:SW_PUSH_6mm',
     {1:'NRST', 2:'GND'}, [35.56,261.62])
part('D1', 'Device:LED', 'STATUS', 'LED_SMD:LED_0805_2012Metric',
     {1:'GND', 2:'LED_A'}, [109.22,261.62])
for ref,val,n1,n2,pos,note in [
 ('R1','0R','USB_DP','USB_DP_MCU',[170.18,149.86],'USB series tuning footprint, default 0R; do not blindly fit 22R.'),
 ('R2','0R','USB_DM','USB_DM_MCU',[170.18,180.34],''),
 ('R3','1k5 1%','USB_PULLUP','USB_DP',[170.18,208.28],''),
 ('R4','10k','V3','USB_ATTACH_N',[170.18,238.76],''),
 ('R5','10k','V3','NRST',[35.56,292.10],''),
 ('R6','10k','BOOT0','GND',[109.22,292.10],''),
 ('R7','10k','BOOT1','GND',[170.18,292.10],''),
 ('R8','10k','V3','CS_N',[215.9,238.76],''),
 ('R9','10k','RF_RESET_N','GND',[215.9,269.24],'Radio held in reset until firmware starts.'),
 ('R10','4k7','V3','SCL',[35.56,332.74],''),
 ('R11','4k7','V3','SDA',[109.22,332.74],''),
 ('R12','2k2','STATUS_LED','LED_A',[170.18,332.74],''),
]:
    part(ref,'Device:R',val,R,{1:n1,2:n2},pos,note)
for idx,(value,n1,n2,at,note) in enumerate([
 ('1u 16V X7R','VBUS','GND',[297.18,35.56],'USB input bulk kept below the USB attach capacitance budget.'),
 ('4u7 16V X7R','V3','GND',[365.76,35.56],'Effective capacitance >= 1uF at 3.3 V across temperature.'),
 ('100n 16V X7R','V3','GND',[297.18,91.44],'U1 pin 24, one capacitor per VDD pin.'),
 ('100n 16V X7R','V3','GND',[365.76,91.44],'U1 pin 36.'),
 ('100n 16V X7R','V3','GND',[434.34,91.44],'U1 pin 48.'),
 ('100n 16V X7R','V3','GND',[297.18,149.86],'U1 VBAT pin 1.'),
 ('100n 16V X7R','V3','GND',[365.76,149.86],'U1 VDDA pin 9.'),
 ('1u 16V X7R','V3','GND',[434.34,149.86],'U1 VDDA pin 9, with C7.'),
 ('4u7 16V X7R','V3','GND',[297.18,208.28],'Local MCU bulk.'),
 ('10n 16V X7R','V3','GND',[365.76,208.28],'Y1 pins 4-2, per oscillator recommendation.'),
 ('100n 16V X7R','V3','GND',[434.34,208.28],'U4 pin 8.'),
 ('100n 16V X7R','NRST','GND',[297.18,269.24],'STM32 reset filtering.'),
 ('1u 16V X7R','V3','GND',[365.76,269.24],'At the radio connector; RF module has its own decoupling.'),
 ('100n 16V X7R','VBUS_USB','GND',[434.34,269.24],'U3 clamp reference, connector side of F1.')
],1):
    part(f'C{idx}','Device:C',value,C,{1:n1,2:n2},at,note)
for index,(net,at) in enumerate([
    ('VBUS',[434.34,35.56]),('V3',[502.92,35.56]),('GND',[502.92,91.44]),
    ('NRST',[502.92,149.86]),('HSE8',[502.92,208.28]),
    ('RF_RESET_N',[502.92,269.24]),('CS_N',[502.92,332.74]),
],1):
    part(f'TP{index}','Connector:TestPoint',net,'TestPoint:TestPoint_Pad_D1.5mm',
         {1:net},at,'Probe with a short ground lead. No test stubs on USB data.')

part('F1', 'Device:Polyfuse', 'MF-NSMF050-2', 'WICI:PPTC_1206_1.8x1.8_Gap1.0',
     {1:'VBUS_USB', 2:'VBUS'}, [35.56,386.08],
     '0.5 A hold at 23 C, 1 A trip; alternative Littelfuse 1206L050/15YR. Temperature derating and voltage drop require bench verification. Not a 500 mA current limiter.')
for index in range(1,5):
    part(f'H{index}', 'Mechanical:MountingHole', 'M3 NPTH 3.2 mm',
         'MountingHole:MountingHole_3.2mm_M3', {}, [109.22 + 68.58*(index-1),386.08],
         'Non-plated mounting hole, 6.4 mm component/copper keepout; insulating hardware.')

part('#FLG1', 'power:PWR_FLAG', 'PWR_FLAG', '', {1:'VBUS'}, [434.34,386.08],
     'Fused USB power is supplied through passive F1. This marks the source for ERC; it does not bypass F1.')


ASSEMBLY = json.loads((ROOT / 'assembly-parts.json').read_text())
assert set(ASSEMBLY) == {p['ref'] for p in PARTS if not p['ref'].startswith(('#', 'TP', 'H'))}
for p in PARTS:
    if p['ref'] in ASSEMBLY:p.update(ASSEMBLY[p['ref']])

def effects(size=1.27, hide=False, justify=None):
    """Create schematic text settings."""
    e=[A('effects'),[A('font'),[A('size'),size,size]]]
    if hide:e.append([A('hide'),A('yes')])
    if justify:e.append([A('justify'),A(justify)])
    return e


def generate():
    """Write self-contained KiCad sources and the explicit connection schedule."""
    root_id=uid('root')
    symbols={p['lib_id']:symbol(p['lib_id']) for p in PARTS}
    schematic=[A('kicad_sch'),[A('version'),20250114],[A('generator'),'eeschema'],
       [A('uuid'),root_id],[A('paper'),'A2'],
       [A('title_block'),[A('title'),'WICI R01.3 USB controller'],
        [A('date'),'2026-10-06'],[A('rev'),'R01.3'],
        [A('comment'),1,'RF module separate. Firmware and physical tests pending.']],
       [A('lib_symbols'),*symbols.values()]]
    for p in PARTS:
        s=symbols[p['lib_id']]
        pins=[x for x in walk(s) if x and x[0]=='pin']
        pin_numbers={child(x,'number')[1] for x in pins}
        if not set(p['nets'])<=pin_numbers:
            raise ValueError(f"{p['ref']}: missing physical pins {set(p['nets'])-pin_numbers}")
        x,y=p['at']
        instance=[A('symbol'),[A('lib_id'),p['lib_id']],[A('at'),x,y,0],[A('unit'),1],
          [A('in_bom'),A('no' if p['ref'].startswith(('#', 'TP', 'H')) else 'yes')],
          [A('on_board'),A('no' if p['ref'].startswith('#') else 'yes')],
          [A('dnp'),A('no')],[A('uuid'),uid(p['ref'])]]
        for prop,value,dy,hidden in [('Reference',p['ref'],-8.89,False),('Value',p['value'],-6.35,False),
                                    ('Footprint',p['footprint'],0,True),('Datasheet',p.get('datasheet',''),0,True),
                                    ('Manufacturer',p.get('manufacturer',''),0,True),('MPN',p.get('mpn',''),0,True)]:
            if prop in ('Manufacturer','MPN') and p['ref'] not in ASSEMBLY:continue
            # MCU text remains clear of its 81-mm-tall body.
            if p['ref']=='U1' and not hidden:dy-=35.56
            instance.append([A('property'),prop,value,[A('at'),x,y+dy,0],effects(1.27,hidden)])
        for pin in sorted(pin_numbers):
            instance.append([A('pin'),pin,[A('uuid'),uid(f"{p['ref']}.pin.{pin}")]])
        instance.append([A('instances'),[A('project'),'radio-usb-controller',
                         [A('path'),'/' + root_id,[A('reference'),p['ref']],[A('unit'),1]]]])
        schematic.append(instance)
        connected_positions={}
        for pin in pins:
            num=child(pin,'number')[1]
            px,py,angle=map(float,child(pin,'at')[1:])
            gx,gy=round(x+px,6),round(y-py,6)
            if num not in p['nets']:
                schematic.append([A('no_connect'),[A('at'),gx,gy],[A('uuid'),uid(f"{p['ref']}.nc.{num}")]])
                continue
            net=p['nets'][num]
            if (gx,gy) in connected_positions:
                if connected_positions[gx,gy]!=net:raise ValueError('Stacked pin net mismatch')
                continue
            connected_positions[gx,gy]=net
            length=5.08
            ex=round(gx-length*math.cos(math.radians(angle)),6)
            ey=round(gy+length*math.sin(math.radians(angle)),6)
            schematic.append([A('wire'),[A('pts'),[A('xy'),gx,gy],[A('xy'),ex,ey]],
              [A('stroke'),[A('width'),0],[A('type'),A('default')]],
              [A('uuid'),uid(f"{p['ref']}.wire.{num}")]])
            rotation=90 if angle in (90,270) else 0
            schematic.append([A('label'),net,[A('at'),ex,ey,rotation],
                              effects(1.016,justify='left'),[A('uuid'),uid(f"{p['ref']}.label.{num}")]])
    path=ROOT/'cad/radio-usb-controller.kicad_sch'
    path.write_text(dump(schematic)+'\n')
    library_dir=ROOT/'cad/symbols'
    library_dir.mkdir(exist_ok=True)
    grouped={}
    for lib_id,s in symbols.items():
        lib,name=lib_id.split(':')
        libsym=deepcopy(s);libsym[1]=name
        grouped.setdefault(lib,[]).append(libsym)
    for lib,defs in grouped.items():
        (library_dir/(lib+'.kicad_sym')).write_text(dump([A('kicad_symbol_lib'),
            [A('version'),20220914],[A('generator'),'kicad_symbol_editor'],*defs])+'\n')
    table=[A('sym_lib_table'),[A('version'),7]]
    for lib in sorted(grouped):
        table.append([A('lib'),[A('name'),lib],[A('type'),'KiCad'],
            [A('uri'),'${KIPRJMOD}/symbols/'+lib+'.kicad_sym'],[A('options'),''],
            [A('descr'),'KiCad 9.0.0 and 10.0.6 subset, see KICAD-LIBRARY-LICENSE.md']])
    (ROOT/'cad/sym-lib-table').write_text(dump(table)+'\n')
    (ROOT/'connections.json').write_text(json.dumps(PARTS,ensure_ascii=False,indent=2)+'\n')
    with (ROOT/'connections.csv').open('w',newline='') as f:
        writer=csv.writer(f);writer.writerow(['reference','physical_pin','net'])
        for p in PARTS:
            for pin,net in p['nets'].items():writer.writerow([p['ref'],pin,net])
    with (ROOT/'bom.csv').open('w',newline='') as f:
        writer=csv.writer(f);writer.writerow(['reference','quantity','value_or_MPN','footprint','manufacturer','mpn','assembly','specification','datasheet','note'])
        for p in PARTS:
            if not p['ref'].startswith(('#', 'TP', 'H')):writer.writerow([p['ref'],1,p['value'],p['footprint'],p['manufacturer'],p['mpn'],p['assembly'],p['specification'],p['datasheet'],p['note']])
    print(f'{sum(not p["ref"].startswith("#") for p in PARTS)} board items; {path}')


if __name__=='__main__':generate()
