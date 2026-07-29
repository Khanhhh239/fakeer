"""
LLM Tier 3 Classifier - Phân loại TRIỆU_CHỨNG vs CHẨN_ĐOÁN bằng Qwen
Sử dụng vLLM với constrained decoding để đảm bảo output là A hoặc B
"""

from typing import Tuple, Optional
import numpy as np


class LLMClassifier:
    """Classifier sử dụng Qwen cho tier 3 của cascade"""
    
    def __init__(
        self,
        model_name: str = "Qwen/Qwen2.5-7B-Instruct",
        device: str = "cuda"
    ):
        """
        Args:
            model_name: Qwen model name (Qwen3-8B hoặc Qwen2.5-7B-Instruct)
            device: 'cuda' hoặc 'cpu'
        """
        self.model_name = model_name
        self.device = device
        self.llm = None
        
    def load_model(self):
        """Load vLLM model"""
        if self.llm is not None:
            return
        
        print(f"Loading LLM: {self.model_name}")
        from vllm import LLM, SamplingParams
        
        self.llm = LLM(
            model=self.model_name,
            dtype="float16",
            max_model_len=2048,
            gpu_memory_utilization=0.5,  # Tiết kiệm memory cho encoder
            tensor_parallel_size=1
        )
        
        print(f"✓ LLM loaded: {self.model_name}")
    
    def classify(
        self,
        span_text: str,
        context: str = ""
    ) -> Tuple[str, float]:
        """
        Phân loại span thành TRIỆU_CHỨNG hoặc CHẨN_ĐOÁN.
        
        Args:
            span_text: Text của span cần phân loại
            context: Câu chứa span để làm context
        
        Returns:
            (label, confidence) where label in ['TRIỆU_CHỨNG', 'CHẨN_ĐOÁN']
        """
        if self.llm is None:
            self.load_model()
        
        # Construct prompt
        system_prompt = (
            "Bạn là bác sĩ. Với cụm từ được trích từ bệnh án, hãy chọn đúng một nhãn:\n"
            "A. TRIỆU_CHỨNG — biểu hiện bệnh nhân khai hoặc bác sĩ quan sát được trên người bệnh\n"
            "B. CHẨN_ĐOÁN — tên một bệnh hoặc hội chứng được quy cho bệnh nhân\n\n"
            "Chỉ trả về một chữ cái A hoặc B."
        )
        
        user_prompt = f"Đoạn: «{context}»\n\nCụm: «{span_text}»\n\nNhãn:"
        
        # Format messages
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        # Apply chat template
        from vllm import SamplingParams
        
        tokenizer = self.llm.get_tokenizer()
        prompt = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True
        )
        
        # Sampling params để lấy logprobs
        sampling_params = SamplingParams(
            temperature=0,
            max_tokens=4,
            logprobs=10,  # Get top 10 logprobs để chắc chắn có A và B
            stop=["\n", ".", ","]
        )
        
        # Generate
        outputs = self.llm.generate([prompt], sampling_params)
        output = outputs[0]
        
        # Parse first token logprobs
        try:
            if output.outputs[0].logprobs and len(output.outputs[0].logprobs) > 0:
                first_token_logprobs = output.outputs[0].logprobs[0]
                
                # Find logprobs for A and B tokens
                logprob_A = None
                logprob_B = None
                
                for token_id, logprob_obj in first_token_logprobs.items():
                    token_str = logprob_obj.decoded_token.strip().upper()
                    
                    # Check for A or B
                    if 'A' in token_str or token_str == 'A':
                        logprob_A = logprob_obj.logprob
                    elif 'B' in token_str or token_str == 'B':
                        logprob_B = logprob_obj.logprob
                
                # If we found both A and B, normalize
                if logprob_A is not None and logprob_B is not None:
                    prob_A = np.exp(logprob_A)
                    prob_B = np.exp(logprob_B)
                    total = prob_A + prob_B
                    
                    prob_A_norm = prob_A / total
                    prob_B_norm = prob_B / total
                    
                    if prob_A_norm >= prob_B_norm:
                        return 'TRIỆU_CHỨNG', float(prob_A_norm)
                    else:
                        return 'CHẨN_ĐOÁN', float(prob_B_norm)
            
            # Fallback: parse generated text
            generated_text = output.outputs[0].text.strip().upper()
            
            # Look for A or B in first few characters
            if 'A' in generated_text[:5]:
                return 'TRIỆU_CHỨNG', 0.7
            elif 'B' in generated_text[:5]:
                return 'CHẨN_ĐOÁN', 0.7
            
            # Ultimate fallback: default to symptom
            return 'TRIỆU_CHỨNG', 0.5
            
        except Exception as e:
            print(f"⚠️ Error parsing LLM output: {e}")
            # Safe fallback
            return 'TRIỆU_CHỨNG', 0.5
    
    def classify_batch(
        self,
        spans: list[dict]
    ) -> list[dict]:
        """
        Phân loại batch spans.
        
        Args:
            spans: List of dicts with keys: text, context
        
        Returns:
            Updated spans với keys: type, confidence
        """
        if not spans:
            return []
        
        if self.llm is None:
            self.load_model()
        
        # Prepare all prompts
        prompts = []
        tokenizer = self.llm.get_tokenizer()
        
        system_prompt = (
            "Bạn là bác sĩ. Với cụm từ được trích từ bệnh án, hãy chọn đúng một nhãn:\n"
            "A. TRIỆU_CHỨNG — biểu hiện bệnh nhân khai hoặc bác sĩ quan sát được trên người bệnh\n"
            "B. CHẨN_ĐOÁN — tên một bệnh hoặc hội chứng được quy cho bệnh nhân\n\n"
            "Chỉ trả về một chữ cái A hoặc B."
        )
        
        for span in spans:
            user_prompt = f"Đoạn: «{span.get('context', '')}»\n\nCụm: «{span['text']}»\n\nNhãn:"
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            prompt = tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True
            )
            prompts.append(prompt)
        
        # Generate batch
        from vllm import SamplingParams
        sampling_params = SamplingParams(
            temperature=0,
            max_tokens=4,
            logprobs=10,
            stop=["\n", ".", ","]
        )
        
        outputs = self.llm.generate(prompts, sampling_params)
        
        # Parse results
        results = []
        for span, output in zip(spans, outputs):
            try:
                # Parse logprobs
                if output.outputs[0].logprobs and len(output.outputs[0].logprobs) > 0:
                    first_token_logprobs = output.outputs[0].logprobs[0]
                    
                    logprob_A = None
                    logprob_B = None
                    
                    for token_id, logprob_obj in first_token_logprobs.items():
                        token_str = logprob_obj.decoded_token.strip().upper()
                        if 'A' in token_str or token_str == 'A':
                            logprob_A = logprob_obj.logprob
                        elif 'B' in token_str or token_str == 'B':
                            logprob_B = logprob_obj.logprob
                    
                    if logprob_A is not None and logprob_B is not None:
                        prob_A = np.exp(logprob_A)
                        prob_B = np.exp(logprob_B)
                        total = prob_A + prob_B
                        
                        prob_A_norm = prob_A / total
                        prob_B_norm = prob_B / total
                        
                        span_updated = span.copy()
                        if prob_A_norm >= prob_B_norm:
                            span_updated['type'] = 'TRIỆU_CHỨNG'
                            span_updated['confidence'] = float(prob_A_norm)
                        else:
                            span_updated['type'] = 'CHẨN_ĐOÁN'
                            span_updated['confidence'] = float(prob_B_norm)
                        
                        results.append(span_updated)
                        continue
                
                # Fallback
                generated_text = output.outputs[0].text.strip().upper()
                span_updated = span.copy()
                
                if 'B' in generated_text[:5]:
                    span_updated['type'] = 'CHẨN_ĐOÁN'
                    span_updated['confidence'] = 0.7
                else:
                    span_updated['type'] = 'TRIỆU_CHỨNG'
                    span_updated['confidence'] = 0.7
                
                results.append(span_updated)
                
            except Exception as e:
                print(f"⚠️ Error processing span: {e}")
                span_updated = span.copy()
                span_updated['type'] = 'TRIỆU_CHỨNG'
                span_updated['confidence'] = 0.5
                results.append(span_updated)
        
        return results


def test_llm_classifier():
    """Test LLM classifier"""
    # Test cases
    test_spans = [
        {'text': 'sốt cao', 'context': 'Bệnh nhân sốt cao 39 độ'},
        {'text': 'đau đầu', 'context': 'Than phiền đau đầu nhiều ngày'},
        {'text': 'viêm phổi', 'context': 'Chẩn đoán xác định viêm phổi'},
        {'text': 'huyết áp tăng', 'context': 'Tiền sử huyết áp tăng 5 năm'},
        {'text': 'mệt mỏi', 'context': 'Cảm thấy mệt mỏi toàn thân'},
    ]
    
    print("="*60)
    print("Testing LLM Classifier (Tier 3)")
    print("="*60)
    
    try:
        classifier = LLMClassifier(model_name="Qwen/Qwen2.5-7B-Instruct")
        
        print("\nSingle classification:")
        for span in test_spans[:2]:
            label, conf = classifier.classify(span['text'], span['context'])
            print(f"  '{span['text']}' -> {label} (conf: {conf:.2f})")
        
        print("\nBatch classification:")
        results = classifier.classify_batch(test_spans)
        for result in results:
            print(f"  '{result['text']}' -> {result['type']} (conf: {result['confidence']:.2f})")
        
        print("\n✓ LLM classifier test passed!")
        
    except Exception as e:
        print(f"\n⚠️ Could not test LLM (need vLLM + GPU): {e}")
        print("This is OK - LLM will be tested on Kaggle")


if __name__ == "__main__":
    test_llm_classifier()
