"""Write src/synth_struct.py -- T2A khoi cau truc (BANGIAO §3.3)"""
import os

content = r'''"""
T2A -- Dung khoi benh an cau truc bang code, KHONG dung LLM.

API chinh:
    build_block(entities, heading_lamsang, heading_hoidap) -> (text, ents_out)
    build_blocks(entities_list, n) -> List[(text, ents_out)]

Bat bien: text[e['position'][0]:e['position'][1]] == e['text'] voi MOI e.
Offset tinh truc tiep theo vi tri chen trong code, khong dung .find() sau khi tao.
"""

import random
import os
import sys
from typing import List, Dict, Tuple, Optional

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KB = os.path.join(_ROOT, "kb")


def _load_txt(name: str) -> List[str]:
    path = os.path.join(KB, name)
    with open(path, encoding="utf-8") as f:
        return [ln.strip() for ln in f if ln.strip()]


# Cac tuy bien layout theo BANGIAO §3.3
NUMBERING = [None, "1.", "1)", "I.", "A.", "Muc 1:", "1 -", "(1)"]
BULLET    = ["-", "•", "*", "+", "‣", "·", None, "1.", "a)", "–"]
INDENT    = ["", "  ", "    ", "      ", "\t"]
COLON     = [":", "", " :", " -", "..."]
BLANKS    = [0, 1, 2]
CASE_FMTS = ["lower", "upper", "title"]
LAYOUT    = ["bullet", "inline", "numbered"]


def _apply_case(text: str, case_fmt: str) -> str:
    if case_fmt == "upper":
        return text.upper()
    if case_fmt == "title":
        return text.title()
    return text


class BlockBuilder:
    """Xay khoi benh an cau truc, theo doi offset chinh xac."""

    def __init__(self):
        self.buf: List[str] = []  # danh sach cac doan van ban
        self.ents: List[Dict] = []
        self._pos: int = 0  # vi tri hien tai trong text cuoi

    def _flush_buf_len(self) -> int:
        """Tinh chieu dai van ban se tao tu buf hien tai."""
        return sum(len(s) for s in self.buf)

    def add_raw(self, text: str) -> "BlockBuilder":
        """Them chuoi thuan, khong co thuc the."""
        self.buf.append(text)
        self._pos += len(text)
        return self

    def add_entity(self, surface: str, etype: str) -> "BlockBuilder":
        """Them thuc the, ghi lai offset."""
        start = self._pos
        self.buf.append(surface)
        end = self._pos + len(surface)
        self.ents.append({
            "text": surface,
            "type": etype,
            "position": [start, end],
        })
        self._pos = end
        return self

    def add_newlines(self, n: int) -> "BlockBuilder":
        nl = "\n" * n
        self.buf.append(nl)
        self._pos += len(nl)
        return self

    def build(self) -> Tuple[str, List[Dict]]:
        """Tra ve (text, entities). Bat bien da bao dam."""
        text = "".join(self.buf)
        return text, self.ents


def build_heading_line(heading: str, numbering: Optional[str],
                       colon: str, case_fmt: str) -> str:
    """Tao dong heading."""
    h = _apply_case(heading, case_fmt)
    if numbering:
        return f"{numbering} {h}{colon}\n"
    return f"{h}{colon}\n"


def build_bullet_line(surface: str, bullet: Optional[str],
                      indent: str) -> Tuple[str, int]:
    """
    Tao dong bullet, tra ve (line, offset_of_surface).
    offset_of_surface la vi tri surface trong line (tinh tu dau line).
    """
    if bullet:
        prefix = f"{indent}{bullet} "
    else:
        prefix = indent
    line = f"{prefix}{surface}\n"
    return line, len(prefix)


def build_inline_line(items: List[Tuple[str, str]],
                      heading: str, separator: str = ", ") -> Tuple[str, List[int]]:
    """
    Tao dong inline: "Heading: item1, item2, item3\n"
    Tra ve (line, [offset_item1, offset_item2, ...]).
    """
    prefix = f"{heading}: "
    line_parts = [prefix]
    offsets = []
    for i, (surface, _) in enumerate(items):
        off = sum(len(p) for p in line_parts)
        offsets.append(off)
        line_parts.append(surface)
        if i < len(items) - 1:
            line_parts.append(separator)
    line_parts.append("\n")
    return "".join(line_parts), offsets


def build_block(
    entities: List[Tuple[str, str]],   # [(surface, type), ...]
    heading_lamsang: List[str],
    heading_hoidap: List[str],
    n_sections: int = 3,
) -> Tuple[str, List[Dict]]:
    """
    Dung 1 khoi benh an cau truc.

    entities: danh sach (surface, type) cua cac thuc the can chen.
    Tra ve (text, ents_out) voi bat bien offset.
    """
    all_headings = heading_lamsang + heading_hoidap
    bb = BlockBuilder()

    # Chon cau hinh layout ngau nhien
    layout = random.choice(LAYOUT)
    case_fmt = random.choice(CASE_FMTS)
    bullet_char = random.choice(BULLET)
    indent_str = random.choice(INDENT)
    colon_str = random.choice(COLON)
    blank_lines = random.choice(BLANKS)
    numbering = random.choice(NUMBERING)

    # Tron entities ngau nhien
    ents_copy = list(entities)
    random.shuffle(ents_copy)

    # Chia thanh cac phan (sections)
    n_ents = len(ents_copy)
    section_size = max(1, n_ents // max(n_sections, 1))

    for sec_idx in range(n_sections):
        if not ents_copy:
            break

        # Heading muc
        heading = random.choice(all_headings)
        heading_line = build_heading_line(heading, numbering if sec_idx == 0 else None,
                                          colon_str, case_fmt)
        bb.add_raw(heading_line)

        # Lay entities cho muc nay
        sec_ents = ents_copy[:section_size]
        ents_copy = ents_copy[section_size:]

        if layout == "bullet":
            for surface, etype in sec_ents:
                line, off = build_bullet_line(surface, bullet_char, indent_str)
                # off la vi tri surface trong line
                # bb._pos dang o dau line -> offset thuc the = bb._pos + off
                start = bb._pos + off
                bb.add_raw(line[:off])
                bb.add_entity(surface, etype)
                # Them phan con lai cua line (xuong dong)
                tail = line[off + len(surface):]
                bb.add_raw(tail)

        elif layout == "inline" and sec_ents:
            line, offsets = build_inline_line(sec_ents, heading, separator=", ")
            # Tao lai theo tung entity de theo doi offset
            prefix_line = f"{_apply_case(heading, case_fmt)}: "
            bb.add_raw(prefix_line)
            for i, (surface, etype) in enumerate(sec_ents):
                bb.add_entity(surface, etype)
                if i < len(sec_ents) - 1:
                    bb.add_raw(", ")
            bb.add_raw("\n")

        elif layout == "numbered":
            for i, (surface, etype) in enumerate(sec_ents, 1):
                prefix = f"{indent_str}{i}. "
                bb.add_raw(prefix)
                bb.add_entity(surface, etype)
                bb.add_raw("\n")

        else:  # fallback: bullet
            for surface, etype in sec_ents:
                bb.add_raw(f"{indent_str}- ")
                bb.add_entity(surface, etype)
                bb.add_raw("\n")

        # Them dong trong giua cac muc
        bb.add_newlines(blank_lines)

    return bb.build()


def build_blocks(
    entities_list: List[List[Tuple[str, str]]],
    n: int,
    heading_lamsang: Optional[List[str]] = None,
    heading_hoidap: Optional[List[str]] = None,
) -> List[Tuple[str, List[Dict]]]:
    """
    Sinh n khoi cau truc. entities_list la kho thuc the, chon ngau nhien moi khoi.
    """
    if heading_lamsang is None:
        heading_lamsang = _load_txt("heading_lamsang.txt")
    if heading_hoidap is None:
        heading_hoidap = _load_txt("heading_hoidap.txt")

    results = []
    for _ in range(n):
        ents = random.choice(entities_list) if entities_list else []
        text, ents_out = build_block(ents, heading_lamsang, heading_hoidap)
        results.append((text, ents_out))
    return results


# ─── TEST ─────────────────────────────────────────────────────────────────


def test_synth_struct():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    failed = 0

    # Dummy headings
    h_ls = ["Trieu chung lam sang", "Tien su benh", "Ket qua xet nghiem",
             "Cac thuoc su dung", "Chan doan", "Xu tri"]
    h_hd = ["Cau hoi", "Tra loi bac si"]

    # 1) build_block layout=bullet: bat bien offset cho 5 entity
    ents_in = [
        ("sot cao", "TRIỆU_CHỨNG"),
        ("ho khan", "TRIỆU_CHỨNG"),
        ("viem phoi", "CHẨN_ĐOÁN"),
        ("amoxicillin", "THUỐC"),
        ("cong thuc mau", "TÊN_XÉT_NGHIỆM"),
    ]
    import random
    random.seed(42)
    text1, ents1 = build_block(ents_in, h_ls, h_hd)
    ok1a = len(ents1) == 5
    ok1b = all(text1[e["position"][0]:e["position"][1]] == e["text"] for e in ents1)
    ok1 = ok1a and ok1b
    print(f"  {'ok' if ok1 else 'FAIL'} build_block bullet: {len(ents1)} ents, "
          f"offset_ok={ok1b}")
    if not ok1b:
        for e in ents1:
            actual = text1[e["position"][0]:e["position"][1]]
            if actual != e["text"]:
                print(f"    BAD: text={e['text']!r}, actual={actual!r}, "
                      f"pos={e['position']}")
    failed += not ok1

    # 2) build_block layout=inline: bat bien
    random.seed(0)
    # Force inline layout
    import synth_struct as _self
    orig = _self.LAYOUT[:]
    _self.LAYOUT[:] = ["inline"]
    text2, ents2 = build_block(ents_in, h_ls, h_hd)
    _self.LAYOUT[:] = orig
    ok2 = (len(ents2) == 5 and
           all(text2[e["position"][0]:e["position"][1]] == e["text"] for e in ents2))
    print(f"  {'ok' if ok2 else 'FAIL'} build_block inline: {len(ents2)} ents, "
          f"offset_ok={ok2}")
    if not ok2:
        for e in ents2:
            actual = text2[e["position"][0]:e["position"][1]]
            if actual != e["text"]:
                print(f"    BAD: {e['text']!r} != {actual!r}")
    failed += not ok2

    # 3) build_block layout=numbered: bat bien
    random.seed(7)
    _self.LAYOUT[:] = ["numbered"]
    text3, ents3 = build_block(ents_in, h_ls, h_hd)
    _self.LAYOUT[:] = orig
    ok3 = (len(ents3) == 5 and
           all(text3[e["position"][0]:e["position"][1]] == e["text"] for e in ents3))
    print(f"  {'ok' if ok3 else 'FAIL'} build_block numbered: {len(ents3)} ents")
    failed += not ok3

    # 4) build_blocks: sinh 20 khoi, assert bat bien 100% (khong can kiem bang mat)
    entities_list = [ents_in] * 10
    blocks = build_blocks(entities_list, 20, h_ls, h_hd)
    n_ok = 0
    bad_cases = []
    for i, (text, ents) in enumerate(blocks):
        block_ok = all(text[e["position"][0]:e["position"][1]] == e["text"]
                       for e in ents)
        if block_ok:
            n_ok += 1
        else:
            bad_cases.append(i)
    ok4 = n_ok == 20
    print(f"  {'ok' if ok4 else 'FAIL'} build_blocks 20 khoi: {n_ok}/20 bat bien ok "
          f"{f'| bad: {bad_cases}' if bad_cases else ''}")
    failed += not ok4

    # 5) heading thuc su lay tu file kb/ (khong hard-code)
    from synth_struct import _load_txt
    try:
        real_h_ls = _load_txt("heading_lamsang.txt")
        real_h_hd = _load_txt("heading_hoidap.txt")
        ok5 = len(real_h_ls) == 67 and len(real_h_hd) == 8
        print(f"  {'ok' if ok5 else 'FAIL'} heading tu KB: "
              f"lamsang={len(real_h_ls)}, hoidap={len(real_h_hd)}")
        # Sinh 5 khoi dung heading thuc
        blocks5 = build_blocks(entities_list, 5)
        ok5b = all(
            all(t[e["position"][0]:e["position"][1]] == e["text"]
                for e in es)
            for t, es in blocks5
        )
        print(f"  {'ok' if ok5b else 'FAIL'} build_blocks voi heading thuc: bat bien={ok5b}")
        failed += not (ok5 and ok5b)
    except Exception as ex:
        print(f"  FAIL heading tu KB: {ex}")
        failed += 1

    print(f"\n{'='*60}")
    if failed:
        raise AssertionError(f"synth_struct: {failed} ca THAT BAI")
    print("ok synth_struct: tat ca ca PASS")


if __name__ == "__main__":
    test_synth_struct()
'''

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
out = os.path.join(root, "src", "synth_struct.py")
with open(out, "w", encoding="utf-8") as f:
    f.write(content)
print(f"Written {out} ({len(content)} bytes)")
