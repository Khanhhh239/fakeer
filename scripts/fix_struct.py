"""Fix synth_struct.py: section cuoi lay het entities, fix inline offset"""
import os

path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "src", "synth_struct.py")
with open(path, encoding="utf-8") as f:
    src = f.read()

# Fix 1: section cuoi lay het entities con lai
old = """        # Lay entities cho muc nay
        sec_ents = ents_copy[:section_size]
        ents_copy = ents_copy[section_size:]"""

new = """        # Lay entities cho muc nay -- section cuoi lay het phan con lai
        is_last = (sec_idx == n_sections - 1) or (len(ents_copy) <= section_size)
        if is_last:
            sec_ents = ents_copy
            ents_copy = []
        else:
            sec_ents = ents_copy[:section_size]
            ents_copy = ents_copy[section_size:]"""

assert old in src, f"Target not found:\n{old}"
src = src.replace(old, new)
print("Fixed section_last")

# Fix 2: inline layout dung bb.add_entity truc tiep, bo phan tao prefix_line rieng
# (cai bug: bb.add_raw(prefix_line) viet heading lan 2 sau da add_raw(heading_line))
old_inline = """        elif layout == "inline" and sec_ents:
            line, offsets = build_inline_line(sec_ents, heading, separator=", ")
            # Tao lai theo tung entity de theo doi offset
            prefix_line = f"{_apply_case(heading, case_fmt)}: "
            bb.add_raw(prefix_line)
            for i, (surface, etype) in enumerate(sec_ents):
                bb.add_entity(surface, etype)
                if i < len(sec_ents) - 1:
                    bb.add_raw(", ")
            bb.add_raw("\\n")"""

new_inline = """        elif layout == "inline" and sec_ents:
            # Khong them heading rieng -- da add o tren
            # Xoa dong heading vua add, thay bang inline prefix
            # Thuc ra: heading da add roi, them ": " roi list entity
            # Viet lai: phan heading_line da co colon_str, nen chi can entity
            for i, (surface, etype) in enumerate(sec_ents):
                bb.add_entity(surface, etype)
                if i < len(sec_ents) - 1:
                    bb.add_raw(", ")
            bb.add_raw("\\n")"""

assert old_inline in src, "old_inline not found"
src = src.replace(old_inline, new_inline)
print("Fixed inline layout")

with open(path, "w", encoding="utf-8") as f:
    f.write(src)
print("Done")
