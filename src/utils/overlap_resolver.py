"""
Giải quyết chồng lấn giữa các thực thể.
Sử dụng weighted interval scheduling (QHĐ) để tìm tập tối ưu.
"""

import bisect
from typing import List, Dict


def select_non_overlapping(items: List[Dict]) -> List[Dict]:
    """
    Chọn tập con không chồng lấn với tổng score cực đại.
    
    Sử dụng quy hoạch động (weighted interval scheduling).
    Mỗi ký tự chỉ được thuộc tối đa một thực thể.
    
    Args:
        items: List of dicts with keys: start, end, score, (other fields preserved)
    
    Returns:
        Optimal non-overlapping subset, sorted by start position
    """
    if not items:
        return []
    
    # Sort by end position
    sorted_items = sorted(items, key=lambda x: x['end'])
    ends = [x['end'] for x in sorted_items]
    n = len(sorted_items)
    
    # DP arrays
    dp = [0.0] * (n + 1)  # dp[i] = max score using first i items
    back = [None] * (n + 1)  # backpointer for reconstruction
    
    for i in range(1, n + 1):
        item = sorted_items[i - 1]
        
        # Find latest item that doesn't overlap with current item
        # An item j doesn't overlap with i if ends[j] <= item['start']
        j = bisect.bisect_right(ends, item['start'], 0, i - 1)
        
        # Choice 1: Take current item
        score_take = item['score'] + dp[j]
        
        # Choice 2: Skip current item
        score_skip = dp[i - 1]
        
        if score_take > score_skip:
            dp[i] = score_take
            back[i] = ('take', j)
        else:
            dp[i] = score_skip
            back[i] = ('skip', i - 1)
    
    # Reconstruct solution
    selected = []
    i = n
    while i > 0:
        action, prev_i = back[i]
        if action == 'take':
            selected.append(sorted_items[i - 1])
        i = prev_i
    
    # Reverse to get correct order, then sort by start
    selected.reverse()
    selected.sort(key=lambda x: x['start'])
    
    return selected


def validate_non_overlapping(entities: List[Dict]) -> bool:
    """
    Validate that entities don't overlap.
    
    Returns:
        True if valid, False if overlapping detected
    """
    if not entities:
        return True
    
    sorted_ents = sorted(entities, key=lambda x: x['start'])
    
    for i in range(len(sorted_ents) - 1):
        if sorted_ents[i]['end'] > sorted_ents[i + 1]['start']:
            return False
    
    return True


def merge_entities_from_branches(
    encoder_entities: List[Dict],
    rule_entities: List[Dict],
    llm_entities: List[Dict] = None
) -> List[Dict]:
    """
    Merge entities from different branches and resolve overlaps.
    
    Args:
        encoder_entities: From encoder + cascade
        rule_entities: From rule-based (lab tests + drugs)
        llm_entities: From LLM fallback (optional)
    
    Returns:
        Final merged and non-overlapping entity list
    """
    # Combine all entities
    all_entities = []
    all_entities.extend(encoder_entities)
    all_entities.extend(rule_entities)
    if llm_entities:
        all_entities.extend(llm_entities)
    
    if not all_entities:
        return []
    
    # Resolve overlaps
    selected = select_non_overlapping(all_entities)
    
    # Sort by start position
    selected.sort(key=lambda x: x['start'])
    
    return selected


def test_overlap_resolver():
    """Test overlap resolution"""
    # Create test entities with overlaps
    entities = [
        {'text': 'sốt cao', 'type': 'TRIỆU_CHỨNG', 'start': 0, 'end': 7, 'score': 0.9},
        {'text': 'sốt', 'type': 'TRIỆU_CHỨNG', 'start': 0, 'end': 3, 'score': 0.7},  # Overlap!
        {'text': 'đau đầu', 'type': 'TRIỆU_CHỨNG', 'start': 10, 'end': 17, 'score': 0.95},
        {'text': 'viêm phổi', 'type': 'CHẨN_ĐOÁN', 'start': 20, 'end': 29, 'score': 0.85},
        {'text': 'phổi', 'type': 'CHẨN_ĐOÁN', 'start': 25, 'end': 29, 'score': 0.6},  # Overlap!
    ]
    
    print("="*60)
    print("Input entities (with overlaps):")
    for ent in sorted(entities, key=lambda x: x['start']):
        print(f"  [{ent['start']:2d}, {ent['end']:2d}] {ent['type']:20s} '{ent['text']}' (score: {ent['score']:.2f})")
    
    # Resolve overlaps
    selected = select_non_overlapping(entities)
    
    print("\n" + "="*60)
    print("After overlap resolution:")
    for ent in selected:
        print(f"  [{ent['start']:2d}, {ent['end']:2d}] {ent['type']:20s} '{ent['text']}' (score: {ent['score']:.2f})")
    
    # Validate
    is_valid = validate_non_overlapping(selected)
    print("\n" + "="*60)
    print(f"Validation: {'✓ PASS' if is_valid else '✗ FAIL'}")
    
    assert is_valid, "Overlap resolution failed!"
    assert len(selected) == 3, f"Expected 3 entities, got {len(selected)}"
    
    print("✓ All overlap tests passed!")


if __name__ == "__main__":
    test_overlap_resolver()
