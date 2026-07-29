"""
Negation Detection - Phát hiện phủ định cho thực thể
Xử lý các cụm như "Không có suy thận", "Phủ nhận viêm phổi"
"""

import re
from typing import List, Dict, Tuple, Optional


# Các từ phủ định tiếng Việt
NEGATION_CUES = [
    # Phủ định trực tiếp
    'không', 'không có', 'chưa', 'chưa có', 'chẳng',
    
    # Phủ nhận
    'phủ nhận', 'phủ định', 'loại trừ', 'loại bỏ',
    
    # Không thấy
    'không thấy', 'không ghi nhận', 'không phát hiện',
    'không quan sát', 'không có dấu hiệu',
    
    # Âm tính
    'âm tính', 'âm', '(-)', '(–)', 'negative',
    
    # Bình thường
    'bình thường', 'trong giới hạn bình thường', 'không bất thường'
]

# Pattern để bắt phủ định
NEGATION_PATTERN = re.compile(
    r'\b(?:' + '|'.join(re.escape(cue) for cue in NEGATION_CUES) + r')\b',
    re.IGNORECASE | re.UNICODE
)


class NegationDetector:
    """Phát hiện phủ định cho entities"""
    
    def __init__(self, window_size: int = 50):
        """
        Args:
            window_size: Số ký tự trước entity để tìm negation cue
        """
        self.window_size = window_size
        self.negation_cues = NEGATION_CUES
    
    def detect_negation(
        self,
        entity: Dict,
        text: str
    ) -> bool:
        """
        Kiểm tra xem entity có bị phủ định không.
        
        Args:
            entity: Dict với keys: text, start, end, type
            text: Văn bản gốc
        
        Returns:
            True nếu entity bị phủ định, False nếu khẳng định
        """
        # Lấy context trước entity
        context_start = max(0, entity['start'] - self.window_size)
        context = text[context_start:entity['start']]
        
        # Tìm negation cue trong context
        match = NEGATION_PATTERN.search(context)
        
        if match:
            # Kiểm tra xem có từ ngắt (terminator) giữa cue và entity không
            # Terminator: dấu chấm, dấu phẩy, "nhưng", "tuy nhiên"
            text_between = context[match.end():]
            
            # Nếu có dấu phân cách mạnh -> không phải phủ định
            if re.search(r'[.;]', text_between):
                return False
            
            # Nếu có "nhưng", "tuy nhiên" -> đảo ngược phủ định
            if re.search(r'\b(?:nhưng|tuy nhiên|tuy vậy)\b', text_between, re.IGNORECASE):
                return False
            
            return True
        
        return False
    
    def annotate_negation(
        self,
        entities: List[Dict],
        text: str
    ) -> List[Dict]:
        """
        Thêm annotation negation vào entities.
        
        Args:
            entities: List of entity dicts
            text: Văn bản gốc
        
        Returns:
            Updated entities với key 'negated' (True/False)
        """
        annotated = []
        
        for entity in entities:
            entity_copy = entity.copy()
            entity_copy['negated'] = self.detect_negation(entity, text)
            annotated.append(entity_copy)
        
        return annotated
    
    def get_assertion_status(self, entity: Dict) -> str:
        """
        Trả về assertion status cho entity.
        
        Returns:
            'negated', 'affirmed', hoặc 'uncertain'
        """
        if entity.get('negated', False):
            return 'negated'
        
        # Có thể mở rộng thêm 'uncertain' sau
        return 'affirmed'


def extract_negation_scope(
    text: str,
    negation_cue_pos: Tuple[int, int]
) -> Tuple[int, int]:
    """
    Xác định scope (phạm vi) của negation cue.
    
    Args:
        text: Văn bản gốc
        negation_cue_pos: (start, end) của negation cue
    
    Returns:
        (scope_start, scope_end) - phạm vi ảnh hưởng của phủ định
    """
    cue_end = negation_cue_pos[1]
    
    # Scope thường kéo dài đến:
    # 1. Dấu chấm, chấm phẩy
    # 2. Từ ngắt (nhưng, tuy nhiên)
    # 3. Tối đa 100 ký tự
    
    scope_end = cue_end
    remaining = text[cue_end:cue_end + 100]
    
    # Tìm điểm dừng
    for match in re.finditer(r'[.;]|\b(?:nhưng|tuy nhiên|tuy vậy)\b', remaining, re.IGNORECASE):
        scope_end = cue_end + match.start()
        break
    else:
        # Không tìm thấy -> scope đến cuối window
        scope_end = min(len(text), cue_end + 100)
    
    return (negation_cue_pos[0], scope_end)


def test_negation_detector():
    """Test negation detection"""
    test_cases = [
        {
            'text': 'Bệnh nhân không có suy thận, không có tiểu đường.',
            'entities': [
                {'text': 'suy thận', 'start': 20, 'end': 28, 'type': 'CHẨN_ĐOÁN'},
                {'text': 'tiểu đường', 'start': 41, 'end': 51, 'type': 'CHẨN_ĐOÁN'}
            ],
            'expected_negated': [True, True]
        },
        {
            'text': 'Phủ nhận đau ngực. Có sốt cao.',
            'entities': [
                {'text': 'đau ngực', 'start': 9, 'end': 17, 'type': 'TRIỆU_CHỨNG'},
                {'text': 'sốt cao', 'start': 22, 'end': 29, 'type': 'TRIỆU_CHỨNG'}
            ],
            'expected_negated': [True, False]
        },
        {
            'text': 'Không có tiền sử suy tim nhưng có tăng huyết áp.',
            'entities': [
                {'text': 'suy tim', 'start': 17, 'end': 24, 'type': 'CHẨN_ĐOÁN'},
                {'text': 'tăng huyết áp', 'start': 35, 'end': 48, 'type': 'CHẨN_ĐOÁN'}
            ],
            'expected_negated': [True, False]
        },
        {
            'text': 'Xét nghiệm HBsAg âm tính.',
            'entities': [
                {'text': 'HBsAg', 'start': 11, 'end': 16, 'type': 'TÊN_XÉT_NGHIỆM'},
                {'text': 'âm tính', 'start': 17, 'end': 24, 'type': 'KẾT_QUẢ_XÉT_NGHIỆM'}
            ],
            'expected_negated': [False, False]  # Âm tính là kết quả, không phải phủ định entity
        },
        {
            'text': 'Viêm phổi. Điều trị bằng kháng sinh.',
            'entities': [
                {'text': 'Viêm phổi', 'start': 0, 'end': 9, 'type': 'CHẨN_ĐOÁN'},
                {'text': 'kháng sinh', 'start': 26, 'end': 36, 'type': 'THUỐC'}
            ],
            'expected_negated': [False, False]
        }
    ]
    
    print("="*60)
    print("Testing Negation Detector")
    print("="*60)
    
    detector = NegationDetector(window_size=50)
    
    passed = 0
    failed = 0
    
    for i, case in enumerate(test_cases, 1):
        print(f"\nTest {i}: {case['text']}")
        
        annotated = detector.annotate_negation(case['entities'], case['text'])
        
        for j, (entity, expected) in enumerate(zip(annotated, case['expected_negated'])):
            negated = entity['negated']
            status = "✓" if negated == expected else "✗"
            
            print(f"  {status} '{entity['text']}': {entity['type']}")
            print(f"     negated={negated} (expected={expected})")
            
            if negated == expected:
                passed += 1
            else:
                failed += 1
    
    print("\n" + "="*60)
    print(f"Test Results: {passed} passed, {failed} failed")
    print("="*60)
    
    if failed == 0:
        print("✓ All negation tests passed!")
    else:
        print(f"⚠️ {failed} tests failed")


if __name__ == "__main__":
    test_negation_detector()
