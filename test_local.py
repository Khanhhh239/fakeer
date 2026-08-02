"""
Script test local để verify các module hoạt động đúng.
Chạy script này TRƯỚC KHI push lên git.
"""

import sys
import os

# Console Windows mặc định là cp1252 -> in tiếng Việt sẽ ném UnicodeEncodeError
# và làm sập cả bộ test trước khi chạy được ca nào. Ép UTF-8 ngay từ đầu.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Add src to path
sys.path.insert(0, "src")

def test_text_alignment():
    """Test ánh xạ offset"""
    print("\n" + "="*60)
    print("TEST 1: Text Alignment")
    print("="*60)
    
    from utils.text_alignment import test_alignment
    test_alignment()

def test_branch_b():
    """Test nhánh B - xét nghiệm"""
    print("\n" + "="*60)
    print("TEST 2: Branch B (Lab Tests)")
    print("="*60)
    
    from branch_b_lab_tests import test_branch_b
    test_branch_b()

def test_branch_c():
    """Test nhánh C - thuốc"""
    print("\n" + "="*60)
    print("TEST 3: Branch C (Drugs)")
    print("="*60)
    
    from branch_c_drugs import test_branch_c_rules
    test_branch_c_rules()

def test_ner_metrics():
    """Test F1 mức thực thể (thay seqeval — gói đó vỡ trên Python 3.12 của Kaggle)"""
    print("\n" + "="*60)
    print("TEST: NER Metrics (entity F1)")
    print("="*60)

    from utils.ner_metrics import test_ner_metrics as _run
    _run()

def test_overlap_resolver():
    """Test giải quyết chồng lấn"""
    print("\n" + "="*60)
    print("TEST 4: Overlap Resolver")
    print("="*60)

    from utils.overlap_resolver import test_overlap_resolver
    test_overlap_resolver()

def test_segment_units_v2():
    """V2 K1 — phân đoạn thành unit, gắn heading cha + zone"""
    print("\n" + "="*60)
    print("TEST V2: Segment Units (K1)")
    print("="*60)
    from segment_units import test_segment_units as _run
    _run()

def test_span_anchor_v2():
    """V2 K6 — neo span LLM sinh về văn bản gốc + hàng rào chống ảo giác"""
    print("\n" + "="*60)
    print("TEST V2: Span Anchor (K6)")
    print("="*60)
    from span_anchor import test_span_anchor as _run
    _run()

def test_merge_entities_v2():
    """V2 K7 — hợp nhất nguồn, heading prior, giải xung đột loại"""
    print("\n" + "="*60)
    print("TEST V2: Merge Entities (K7)")
    print("="*60)
    from merge_entities import test_merge_entities as _run
    _run()

def test_llm_extract_v2():
    """V2 K2 — prompt + parse (phần không cần GPU/vllm)"""
    print("\n" + "="*60)
    print("TEST V2: LLM Extract prompt/parse (K2)")
    print("="*60)
    from llm_extract import test_llm_extract as _run
    _run()

def test_export_btc_v2():
    """V2 K8 — chuẩn biên, mở rộng KB, xuất format BTC"""
    print("\n" + "="*60)
    print("TEST V2: Export BTC format (K8)")
    print("="*60)
    from export_btc import test_export_btc as _run
    _run()

def test_on_real_data():
    """Test trên data thật từ input/"""
    print("\n" + "="*60)
    print("TEST 5: Real Data Test")
    print("="*60)
    
    # Read a sample file
    with open('input/1.txt', 'r', encoding='utf-8') as f:
        text = f.read()
    
    print(f"Loaded input/1.txt ({len(text)} chars)")
    
    # Test alignment
    from utils.text_alignment import segment_with_map
    words, spans, ok = segment_with_map(text)
    
    assert ok, "Alignment FAILED on real data!"
    print(f"✓ Alignment OK: {len(words)} words")
    
    # Test branch B
    from branch_b_lab_tests import extract_lab_pairs
    lab_ents = extract_lab_pairs(text)
    print(f"✓ Branch B: {len(lab_ents)} lab test entities")
    
    # Test branch C (without actual dictionary)
    from branch_c_drugs import DrugMatcher
    matcher = DrugMatcher()
    matcher.add_custom_drugs(["Medrol", "Furosemid", "Paracetamol"])
    drug_ents = matcher.extract_drugs(text)
    print(f"✓ Branch C: {len(drug_ents)} drug entities")
    
    print("\n✓ Real data test PASSED!")

def run_all_tests():
    """Run all tests"""
    print("\n" + "="*60)
    print("RUNNING ALL LOCAL TESTS")
    print("="*60)
    
    tests = [
        ("Text Alignment", test_text_alignment),
        ("Branch B", test_branch_b),
        ("Branch C", test_branch_c),
        ("NER Metrics", test_ner_metrics),
        ("Overlap Resolver", test_overlap_resolver),
        ("Real Data", test_on_real_data),
        ("V2 Segment Units (K1)", test_segment_units_v2),
        ("V2 Span Anchor (K6)", test_span_anchor_v2),
        ("V2 Merge Entities (K7)", test_merge_entities_v2),
        ("V2 LLM Extract (K2)", test_llm_extract_v2),
        ("V2 Export BTC (K8)", test_export_btc_v2),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        try:
            test_func()
            passed += 1
        except Exception as e:
            print(f"\n❌ {name} FAILED: {e}")
            failed += 1
    
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    print(f"Passed: {passed}/{len(tests)}")
    print(f"Failed: {failed}/{len(tests)}")
    
    if failed == 0:
        print("\n✓ ALL TESTS PASSED! Ready to push to git.")
    else:
        print("\n❌ SOME TESTS FAILED! Fix before pushing.")
        sys.exit(1)

if __name__ == "__main__":
    run_all_tests()
