import sys; sys.path.insert(0,'src')
import random; random.seed(42)
from synth_struct import build_block, LAYOUT, NUMBERING, BULLET, INDENT, COLON, BLANKS, CASE_FMTS

orig_layout = LAYOUT[:]
LAYOUT[:] = ['bullet']

h_ls = ['Trieu chung lam sang','Tien su benh','Ket qua xet nghiem']
h_hd = ['Cau hoi','Tra loi']
ents_in = [('sot cao','TC'),('ho khan','TC'),('viem phoi','CD'),('amoxicillin','TH'),('cong thuc mau','XN')]

text, ents = build_block(ents_in, h_ls, h_hd, n_sections=2)
print(f'n_sections=2, section_size = {len(ents_in)}//{2} = {len(ents_in)//2}')
print(f'Entities returned: {len(ents)} (expected 5)')
print('Text:')
print(repr(text))
print()
for e in ents:
    actual = text[e['position'][0]:e['position'][1]]
    ok = actual == e['text']
    print(f'  {"ok" if ok else "BAD"} {e["text"]!r} pos={e["position"]} actual={actual!r}')

LAYOUT[:] = orig_layout
