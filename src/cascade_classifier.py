"""
THÁC 3 BẬC - Tách SYM_DIS -> TRIỆU_CHỨNG / CHẨN_ĐOÁN

Bậc 1: KB chương R (mã ICD bắt đầu với 'R') -> TRIỆU_CHỨNG
Bậc 2: KB ngoài chương R, cosine >= 0.93 -> CHẨN_ĐOÁN
Bậc 3: Còn lại -> hỏi Qwen nhị phân A/B
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Optional, Tuple
from sentence_transformers import SentenceTransformer


class CascadeClassifier:
    """Thác phân loại triệu chứng vs chẩn đoán"""
    
    def __init__(
        self,
        icd_path: str = None,
        embedding_model: str = "AITeamVN/Vietnamese_Embedding",
        threshold: float = 0.93
    ):
        """
        Args:
            icd_path: Path to icd10_vi_full.csv
            embedding_model: Sentence transformer model
            threshold: Cosine similarity threshold for Tier 2
        """
        self.threshold = threshold
        self.icd_codes = []
        self.icd_names = []
        self.icd_chapter_r = []  # Chương R - triệu chứng
        self.icd_other = []  # Ngoài chương R
        
        # Load ICD KB
        if icd_path:
            self.load_icd(icd_path)
        
        # Load embedding model
        print(f"Loading embedding model: {embedding_model}")
        self.encoder = SentenceTransformer(embedding_model)
        
        # Encode ICD names
        if self.icd_names:
            print("Encoding ICD knowledge base...")
            self.icd_embeddings = self.encoder.encode(
                self.icd_names,
                show_progress_bar=True,
                convert_to_numpy=True
            )
            print(f"  ✓ Encoded {len(self.icd_embeddings)} ICD terms")
    
    def load_icd(self, path: str):
        """Load ICD-10 Vietnamese KB"""
        print(f"Loading ICD-10 KB from {path}")
        df = pd.read_csv(path)
        
        # Assuming columns: code, name
        for _, row in df.iterrows():
            code = str(row['code']).strip()
            name = str(row['name']).strip()
            
            self.icd_codes.append(code)
            self.icd_names.append(name)
            
            # Separate chapter R (symptoms) from others (diseases)
            if code.startswith('R'):
                self.icd_chapter_r.append(len(self.icd_codes) - 1)
            else:
                self.icd_other.append(len(self.icd_codes) - 1)
        
        print(f"  ✓ Loaded {len(self.icd_codes)} ICD codes")
        print(f"    - Chapter R (symptoms): {len(self.icd_chapter_r)} codes")
        print(f"    - Other chapters (diseases): {len(self.icd_other)} codes")
    
    def tier1_chapter_r(self, span_text: str) -> Optional[str]:
        """
        Bậc 1: Retrieval trên chương R.
        Nếu top-1 thuộc chương R -> TRIỆU_CHỨNG
        
        Returns:
            'TRIỆU_CHỨNG' if matched, None otherwise
        """
        if not self.icd_chapter_r:
            return None
        
        # Encode query
        query_emb = self.encoder.encode([span_text], convert_to_numpy=True)[0]
        
        # Compute similarity with chapter R only
        chapter_r_embs = self.icd_embeddings[self.icd_chapter_r]
        similarities = np.dot(chapter_r_embs, query_emb)
        
        top_idx = np.argmax(similarities)
        top_score = similarities[top_idx]
        top_icd_idx = self.icd_chapter_r[top_idx]
        
        # Simple heuristic: if best match is in chapter R, classify as symptom
        # But need reasonable similarity (> 0.5)
        if top_score > 0.5:
            return 'TRIỆU_CHỨNG'
        
        return None
    
    def tier2_high_similarity(self, span_text: str) -> Optional[str]:
        """
        Bậc 2: Retrieval trên NGOÀI chương R.
        Nếu cosine >= threshold -> CHẨN_ĐOÁN
        
        Returns:
            'CHẨN_ĐOÁN' if matched, None otherwise
        """
        if not self.icd_other:
            return None
        
        # Encode query
        query_emb = self.encoder.encode([span_text], convert_to_numpy=True)[0]
        
        # Compute similarity with non-R chapters only
        other_embs = self.icd_embeddings[self.icd_other]
        similarities = np.dot(other_embs, query_emb)
        
        top_idx = np.argmax(similarities)
        top_score = similarities[top_idx]
        
        if top_score >= self.threshold:
            return 'CHẨN_ĐOÁN'
        
        return None
    
    def tier3_llm(
        self,
        span_text: str,
        context: str = "",
        llm_client = None
    ) -> Tuple[str, float]:
        """
        Bậc 3: Hỏi LLM nhị phân A/B.
        
        Args:
            span_text: Span text to classify
            context: Surrounding sentence for context
            llm_client: vLLM client hoặc compatible interface
        
        Returns:
            (label, confidence) where label in ['TRIỆU_CHỨNG', 'CHẨN_ĐOÁN']
        """
        if llm_client is None:
            # Default to TRIỆU_CHỨNG if no LLM available
            return 'TRIỆU_CHỨNG', 0.5
        
        # Construct prompt
        system_prompt = (
            "Bạn là bác sĩ. Với cụm từ được trích từ bệnh án, hãy chọn đúng một nhãn:\n"
            "A. TRIỆU_CHỨNG — biểu hiện bệnh nhân khai hoặc bác sĩ quan sát được trên người bệnh\n"
            "B. CHẨN_ĐOÁN — tên một bệnh hoặc hội chứng được quy cho bệnh nhân\n"
            "Chỉ trả về một chữ cái."
        )
        
        user_prompt = f"Đoạn: «{context}»\n\nCụm: «{span_text}»\n\nNhãn:"
        
        # Call LLM với constrained decoding
        # This part needs actual vLLM integration
        # For now, return placeholder
        
        # TODO: Implement actual LLM call with constrained decoding
        # response = llm_client.generate(...)
        # Parse logprobs for A/B and normalize
        
        return 'TRIỆU_CHỨNG', 0.6  # Placeholder
    
    def classify(
        self,
        span_text: str,
        context: str = "",
        llm_client = None
    ) -> Tuple[str, float, str]:
        """
        Chạy toàn bộ cascade.
        
        Returns:
            (label, confidence, tier_used)
            where tier_used in ['tier1_kb', 'tier2_kb', 'tier3_llm']
        """
        # Tier 1: Chapter R
        result = self.tier1_chapter_r(span_text)
        if result:
            return result, 1.0, 'tier1_kb'
        
        # Tier 2: High similarity
        result = self.tier2_high_similarity(span_text)
        if result:
            return result, 1.0, 'tier2_kb'
        
        # Tier 3: LLM
        label, confidence = self.tier3_llm(span_text, context, llm_client)
        return label, confidence, 'tier3_llm'
    
    def classify_batch(
        self,
        spans: List[Dict],
        llm_client = None
    ) -> List[Dict]:
        """
        Classify a batch of spans.
        
        Args:
            spans: List of dicts with keys: text, (optional) context
        
        Returns:
            Updated spans with keys: type, tier, confidence
        """
        results = []
        
        for span in spans:
            span_text = span['text']
            context = span.get('context', '')
            
            label, confidence, tier = self.classify(span_text, context, llm_client)
            
            span_updated = span.copy()
            span_updated['type'] = label
            span_updated['tier'] = tier
            span_updated['confidence'] = confidence
            
            results.append(span_updated)
        
        return results


def test_cascade():
    """Test cascade classifier"""
    # Mock ICD data
    import tempfile
    import os
    
    mock_icd = pd.DataFrame({
        'code': ['R50', 'R51', 'R52', 'J18', 'N18', 'I10'],
        'name': [
            'Sốt không rõ nguyên nhân',
            'Đau đầu',
            'Đau không phân loại nơi khác',
            'Viêm phổi',
            'Bệnh thận mạn',
            'Tăng huyết áp nguyên phát'
        ]
    })
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        mock_icd.to_csv(f, index=False)
        temp_path = f.name
    
    try:
        # Initialize classifier
        classifier = CascadeClassifier(icd_path=temp_path)
        
        # Test cases
        test_spans = [
            {'text': 'sốt cao', 'context': 'Bệnh nhân sốt cao 39 độ'},
            {'text': 'đau đầu', 'context': 'Than phiền đau đầu nhiều'},
            {'text': 'viêm phổi', 'context': 'Chẩn đoán viêm phổi'},
            {'text': 'tăng huyết áp', 'context': 'Tiền sử tăng huyết áp'},
        ]
        
        print("\n" + "="*60)
        print("Testing Cascade Classifier")
        print("="*60)
        
        results = classifier.classify_batch(test_spans)
        
        for span, result in zip(test_spans, results):
            print(f"\nSpan: '{span['text']}'")
            print(f"  -> {result['type']} (tier: {result['tier']}, conf: {result['confidence']:.2f})")
        
        print("\n✓ Cascade test completed!")
        
    finally:
        os.unlink(temp_path)


if __name__ == "__main__":
    test_cascade()
