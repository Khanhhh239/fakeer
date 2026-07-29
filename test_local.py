"""
Script test local để verify các module hoạt động đúng.
Chạy script này TRƯỚC KHI push lên git.
"""

import sys
import os

# Add src to path
sys.path.insert(0, 'src')

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
    
    from branch_c_drugs import test_branch_c
    test_branch_c()

def test_overlap_resolver():
    """Test giải quyết chồng lấn"""
    print("\n" + "="*60)
    print("TEST 4: Overlap Resolver")
    print("="*60)
    
    from utils.overlap_resolver import test_overlap_resolver
    test_overlap_resolver()

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
        ("Overlap Resolver", test_overlap_resolver),
        ("Real Data", test_on_real_data),
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
