import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import diagnose

class L0Checks(unittest.TestCase):
    def test_pinmap_matches_quote(self):
        import re
        pins={name:int(value) for name,value in re.findall(r'(\w+)\s*=\s*(\d+)',(ROOT/'src/board.h').read_text())}
        with (ROOT/'reference/polaczenia-MCU-L0.csv').open() as f:
            for row in csv.DictReader(f):self.assertEqual(pins[row['sygnal']],int(row['GPIO']),row['sygnal'])
        self.assertEqual(len(pins),20)
    def test_fram_report_rejects_missing_pass(self):
        lines=[f'FRAM_PASS {i} 0 {diagnose.expected_crc(i,0x12345678):08X} {diagnose.expected_crc(i,0x12345678):08X}' for i in range(5)]+['FRAM_DONE 12345678 WRITE']
        diagnose.validate_fram(lines,0x12345678,False)
        with self.assertRaises(RuntimeError):diagnose.validate_fram(lines[1:],0x12345678,False)
        with self.assertRaises(RuntimeError):diagnose.validate_fram(lines,0x12345679,False)
    def test_retention_cannot_be_write_report(self):
        crc=diagnose.expected_crc(4,1)
        diagnose.validate_fram([f'FRAM_PASS 4 0 {crc:08X} {crc:08X}','FRAM_DONE 00000001 VERIFY'],1,True)
        with self.assertRaises(RuntimeError):diagnose.validate_fram(['FRAM_PASS 4 0 ABCD ABCD','FRAM_DONE 00000001 WRITE'],1,True)
    def test_mixed_requires_completion_and_no_errors(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'radio.jsonl'
            for line,ok in [('MIX_DONE 4000 0 4000 900000 225',True),('MIX_DONE 4000 1 4000 900000 225',False),('MIX_START 900000',False)]:
                p.write_text(json.dumps({'node':'A','line':line,'elapsed_s':895})+'\n')
                if ok:self.assertEqual(diagnose.validate_mixed(p)['errors'],0)
                else:
                    with self.assertRaises(RuntimeError):diagnose.validate_mixed(p)
    def test_native_diagnostic_vectors(self):
        source=r'''
#include "diagnostic.h"
#include "fram_id.h"
#include "commands.h"
#include "font.h"
#include <assert.h>
#include <initializer_list>
int main(){
 using namespace diagnostic;
 uint32_t c=0xFFFFFFFF;for(char b:"123456789")if(b)c=crc(c,b);assert((c^0xFFFFFFFF)==0xCBF43926);
 assert(inRange(0,FRAM_SIZE));assert(inRange(FRAM_SIZE,0));assert(!inRange(FRAM_SIZE,1));assert(!inRange(0xFFFFFFF0,32));
 assert(!cooldownElapsed(10,0,20));assert(cooldownElapsed(20,0,20));assert(cooldownElapsed(5,0xFFFFFFF0,20));
 assert(pattern(123,0,7)==0);assert(pattern(123,1,7)==255);assert(pattern(123,2,7)==170);assert(pattern(123,3,7)==85);
 assert(pattern(123,4,7)==pattern(123,4,7));assert(pattern(123,4,7)!=pattern(123,4,8));
 uint8_t id[]={0x7f,0x7f,0x7f,0x7f,0x7f,0x7f,0xc2,0x2c,0xa1};assert(fram::classify(id)==fram::Part::CY15B104QN);
 id[8]=0xa5;assert(fram::classify(id)==fram::Part::UNKNOWN);
 uint8_t mb[]={0x04,0x7f,0x49,0x03,0xff,0xff,0xff,0xff,0xff};assert(fram::classify(mb)==fram::Part::MB85RS4MT);
 assert(commands::parse("FRAMVERIFY FFFFFFFF").value==0xFFFFFFFF);
 for(const char* bad:{"FRAMVERIFY -1","FRAMVERIFY 100000000","LCD +1","LCD 01"})
   assert(commands::parse(bad).kind==commands::Kind::Unknown);
 for(size_t i=1;i<font::GLYPH_COUNT;++i)assert(font::GLYPHS[i-1].codepoint<font::GLYPHS[i].codepoint);
 assert(font::glyph(0x110000).codepoint==font::REPLACEMENT);
 for(const char* bad:{"\xC0\xAF","\xED\xA0\x80","\xF4\x90\x80\x80","\xE2"}) {
   const char* cursor=bad;assert(font::next(cursor)==font::REPLACEMENT);
 }
 const char* polish="\xC4\x85";assert(font::next(polish)==0x105);assert(font::next(polish)==0);

}
'''
        with tempfile.TemporaryDirectory() as t:
            s=Path(t)/'test.cpp';s.write_text(source);bin=Path(t)/'test'
            subprocess.run(['clang++','-std=c++11','-Wall','-Wextra','-Werror','-I'+str(ROOT/'src'),str(s),str(ROOT/'src/font.cpp'),'-o',str(bin)],check=True)
            subprocess.run([str(bin)],check=True)

if __name__=='__main__':unittest.main()
