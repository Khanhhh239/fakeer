"""Patch test_local.py: add 3 synth modules"""
import os

path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "test_local.py")
with open(path, encoding="utf-8") as f:
    src = f.read()

# Add 3 new test functions before run_all_tests
new_funcs = '''
def test_synth_source():
    """T0 -- kho nguon tong hop (phan tang ICD, trich hoat chat, sinh KQ)"""
    print("\\n" + "="*60)
    print("TEST SYNTH: Source (T0)")
    print("="*60)
    from synth_source import test_synth_source as _run
    _run()


def test_synth_anchor():
    """anchor_all + validate_document (BANGIAO §4-§5)"""
    print("\\n" + "="*60)
    print("TEST SYNTH: Anchor + Validate")
    print("="*60)
    from synth_anchor import test_synth_anchor as _run
    _run()


def test_synth_struct():
    """T2A -- khoi cau truc bat bien offset (BANGIAO §3.3)"""
    print("\\n" + "="*60)
    print("TEST SYNTH: Struct T2A")
    print("="*60)
    from synth_struct import test_synth_struct as _run
    _run()


'''

target = "def run_all_tests():"
assert target in src, "run_all_tests not found"
src = src.replace(target, new_funcs + target)

# Add to tests list
old_list_end = '''        ("V2 Export BTC (K8)", test_export_btc_v2),
    ]'''
new_list_end = '''        ("V2 Export BTC (K8)", test_export_btc_v2),
        ("Synth Source (T0)", test_synth_source),
        ("Synth Anchor+Validate", test_synth_anchor),
        ("Synth Struct T2A", test_synth_struct),
    ]'''
assert old_list_end in src, "tests list end not found"
src = src.replace(old_list_end, new_list_end)

with open(path, "w", encoding="utf-8") as f:
    f.write(src)
print("Patched test_local.py with 3 synth test functions")
