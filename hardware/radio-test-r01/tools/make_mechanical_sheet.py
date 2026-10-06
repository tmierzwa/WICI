# SPDX-License-Identifier: GPL-3.0-or-later
"""Create an unmirrored 1:1 fit-check PDF from exported PCB pad geometry.

The PDF contains physical-size pads, finished drills, bodies and a 50 mm
calibration bar. Printing and fitting real parts remain manual acceptance steps.
"""
import json,math
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.pagesizes import A4
ROOT=Path(__file__).resolve().parents[1]
def main():
 g=json.loads((ROOT/'checks/mechanical-geometry.json').read_text());target=ROOT/'mechanika-1-do-1.pdf';c=canvas.Canvas(str(target),pagesize=A4)
 c.setTitle('WICI R01.3 - mechanical fit check 1:1');c.setAuthor('WICI open hardware project')
 def line(text,x,y,size=9):c.setFont('Helvetica',size);c.setFillColorRGB(0,0,0);c.drawString(x*mm,y*mm,text)
 line('WICI R01.3 - KONTROLA MECHANIKI 1:1',20,278,13)
 line('WIDOK Z GORY / STRONA ELEMENTOW / BEZ ODBICIA LUSTRZANEGO',20,267,9)
 line('Drukuj: 100% / rozmiar rzeczywisty. Wylacz dopasowanie do strony.',20,260,9)
 line('Najpierw zmierz kreske kontrolna. Dopiero potem sprawdzaj elementy.',20,254,9)
 bx,by=25,180
 def p(pos):return ((bx+pos[0]-80)*mm,(by+115-pos[1])*mm)
 c.setStrokeColorRGB(0,0,0);c.setLineWidth(.15*mm);c.rect(bx*mm,by*mm,70*mm,55*mm)
 # Bodies are actual transformed F.Fab primitives from the saved PCB.
 for f in g['footprints']:
  c.setStrokeColorRGB(.45,.45,.45);c.setLineWidth(.08*mm)
  for d in f['fab']:
   a,z=p(d['start']),p(d['end']);shape=d['shape']
   if shape==g['shape_ids']['SEGMENT']:c.line(*a,*z)
   elif shape==g['shape_ids']['RECT']:c.rect(min(a[0],z[0]),min(a[1],z[1]),abs(a[0]-z[0]),abs(a[1]-z[1]))
   elif shape==g['shape_ids']['CIRCLE']:c.circle(*a,math.dist(a,z))
  for pad in f['pads']:
   x,y=p(pad['pos']);w,h=[v*mm for v in pad['size']];dx,dy=[v*mm for v in pad['drill']]
   c.saveState();c.translate(x,y);c.rotate(pad['angle']);c.setLineWidth(.06*mm);c.setStrokeColorRGB(.3,.3,.3);c.setFillColorRGB(.92,.92,.92)
   if pad['shape']==g['pad_circle']:c.circle(0,0,w/2,stroke=1,fill=1)
   else:c.rect(-w/2,-h/2,w,h,stroke=1,fill=1)
   if dx and dy:c.setFillColorRGB(1,1,1);c.ellipse(-dx/2,-dy/2,dx/2,dy/2,stroke=1,fill=1)
   c.restoreState()
   if f['ref'] in ('J1','J2','J3','J4','SW1'):
    c.setFillColorRGB(0,0,0);c.setFont('Helvetica',3.5)
    c.drawCentredString(x,y-1.25,pad['number'])
  x,y=p(f['refpos']);c.setFillColorRGB(0,0,0);c.setFont('Helvetica',4.8);c.drawCentredString(x,y,f['ref'])
 # Correct PCB-to-connector orientation remains visible on the paper sheet.
 line('70 x 55 mm; otwory 3.2 mm, rozstaw 62 x 47 mm',25,173,7)
 line('USB-B J1 - numery elektryczne:',110,229,9)
 for i,text in enumerate(['1 = +5 V z USB (przed F1)','2 = D-','3 = D+','4 = GND','5 = ekran / GND']):line(text,110,220-i*6,8)
 line('J1: Wuerth 61400416121',110,180,8)
 line('J2: Wuerth 61201021621, IDC 2 x 5',110,173,8)
 line('SW1: Omron B3F-1000; styki 6.5 x 4.5 mm',110,166,8)
 # This is intentionally independent of SVG/page bounding-box auto-scaling.
 c.setStrokeColorRGB(0,0,0);c.setLineWidth(.15*mm);c.line(25*mm,160*mm,75*mm,160*mm)
 for x in (25,75):c.line(x*mm,158*mm,x*mm,162*mm)
 line('OD KRESKI DO KRESKI: DOKLADNIE 50.00 mm',25,151,8)
 for y,text in [(137,'1. Zmierz linie kontrolna 50 mm i zewnetrzny obrys 70 x 55 mm.'),(129,'2. Sprawdz USB-B, przycisk i IDC na fizycznym wydruku, od strony elementow.'),(121,'3. Nie odbijaj kartki i nie zamieniaj widoku od spodu z widokiem z gory.'),(113,'4. Sprawdz srednice otworow, wszystkie nozki, obrys i miejsce na wtyki.'),(105,'5. Dla SW1 zmierz styki: wspolne nozki i zwarcie po nacisnieciu.'),(97,'6. Potwierdz pin 1 USB (+5 V) i pin 4 (GND) z karta rzeczywistej czesci.'),(89,'7. Sprawdz klucz IDC i zgodnosc pin 1 / kwadratowego pola.'),(81,'8. Uzyj izolacyjnych dystansow M3. Nie dawaj metalowej podkladki > 6.4 mm.')]:line(text,20,y,8)
 line('Wynik dopasowania: NIE WYKONANO. To szablon do kontroli, nie dopuszczenie produkcji.',20,67,8)
 line('USB: __________  SW1: __________  IDC: __________  Skala: __________',20,54,8)
 line('MPN / osoba / data / uwagi: __________________________________________________',20,43,8)
 line('Wersja PCB R01.3. ERC/DRC nie zastapuja proby mechanicznej.',20,28,8)
 c.save()
 print(target)
if __name__=='__main__':main()
