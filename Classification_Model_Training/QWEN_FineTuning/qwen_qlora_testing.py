import os
os.environ["HF_TOKEN"] = "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"
os.environ['HF_HOME'] = '/work/pi_bhatt_umass_edu/farah_urdu/HuggingfaceCash'
os.environ['TOKENIZERS_PARALLELISM'] = 'false'
os.environ['TRANSFORMERS_VERBOSITY'] = 'error'

import json
import torch
import pandas as pd
from datasets import Dataset, DatasetDict
from transformers import (
    AutoTokenizer,
    AutoModelForCausalLM,
    BitsAndBytesConfig,  # NEW: For loading quantized model
)
from peft import PeftModel, PeftConfig  # NEW: For loading LoRA adapters
from sklearn.metrics import precision_recall_fscore_support, classification_report
import numpy as np
from typing import Dict, List, Optional
import warnings
from tqdm import tqdm
import pickle
warnings.filterwarnings('ignore')

class QLoRAEvaluator:
    def __init__(
        self,
        base_model_name: str = "Qwen/Qwen2.5-7B-Instruct",  # NEW: Base model name
        adapter_dir: str = "/work/pi_bhatt_umass_edu/farah_urdu/qwen_bilingual_finetuned_qlora_improved/",  # NEW:  Adapter directory
        urdu_folder: str = "./Urdu",
        english_folder: str = "./English",
        output_dir:  str = "./evaluation_results_qlora_Urdu",
        checkpoint_every: int = 500,
        batch_size: int = 8,  # Can be larger with QLoRA
        max_length:  int = 2048,  # Match training length
        language: str = "urdu",
        load_in_4bit: bool = True,  # NEW: Load base model in 4-bit
    ):
        self.base_model_name = base_model_name
        self.adapter_dir = adapter_dir
        self.urdu_folder = urdu_folder
        self.english_folder = english_folder
        self.output_dir = output_dir
        self.checkpoint_every = checkpoint_every
        self.batch_size = batch_size
        self. max_length = max_length
        self.language = language
        self.load_in_4bit = load_in_4bit
        
        os.makedirs(self.output_dir, exist_ok=True)
        
        self.valid_labels = []
        self._load_labels()
        
        print("Loading tokenizer...")
        # Load tokenizer from adapter directory (has same tokenizer as base)
        self.tokenizer = AutoTokenizer.from_pretrained(
            adapter_dir,
            token=os.environ.get("HF_TOKEN"),
            cache_dir='/work/pi_bhatt_umass_edu/farah_urdu/HuggingfaceCash/'
        )
        self.tokenizer.padding_side = 'left'  # Left padding for batch inference
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
        
        self.model = None
        self.device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
        
        print(f"Device: {self.device}")
        print(f"Base model: {self.base_model_name}")
        print(f"Adapter directory: {self. adapter_dir}")
        print(f"Batch size: {self.batch_size}")
        print(f"Max length: {self.max_length}")
        print(f"Load in 4-bit: {self.load_in_4bit}")
        print(f"Checkpoint every: {checkpoint_every} samples")
    
    def _load_labels(self):
        """Load labels from adapter directory"""
        labels_file = os.path.join("/work/pi_bhatt_umass_edu/farah_urdu/qwen_bilingual_finetuned_qlora_improved/", 'extracted_labels.json')
        if os.path.exists(labels_file):
            with open(labels_file, 'r', encoding='utf-8') as f:
                labels_info = json.load(f)
                self.valid_labels = labels_info. get('normalized_labels', [])
                self.label_mapping = labels_info.get('original_to_normalized', {})
            print(f"Loaded {len(self.valid_labels)} labels from {labels_file}")
        else:
            raise ValueError(f"Labels file not found:  {labels_file}")
    
    def load_model(self):
        """Load base model + LoRA adapters"""
        if self.model is not None:
            return
        
        print(f"\nLoading QLoRA model...")
        print(f"Step 1: Loading base model:  {self.base_model_name}")
        
        if self.load_in_4bit:
            # NEW: Load base model in 4-bit (same as training)
            bnb_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.bfloat16,
                bnb_4bit_use_double_quant=True,
            )
            
            base_model = AutoModelForCausalLM.from_pretrained(
                self. base_model_name,
                quantization_config=bnb_config,
                device_map="auto",
                trust_remote_code=True,
                token=os.environ.get("HF_TOKEN"),
                cache_dir='/work/pi_bhatt_umass_edu/farah_urdu/HuggingfaceCash/',
                torch_dtype=torch.bfloat16,
            )
            print("Base model loaded in 4-bit")
        else:
            # Load in FP16 (uses more memory but might be faster)
            base_model = AutoModelForCausalLM.from_pretrained(
                self.base_model_name,
                torch_dtype=torch.float16,
                device_map="auto",
                trust_remote_code=True,
                token=os.environ.get("HF_TOKEN"),
                cache_dir='/work/pi_bhatt_umass_edu/farah_urdu/HuggingfaceCash/'
            )
            print("Base model loaded in FP16")
        
        # NEW: Load LoRA adapters on top of base model
        print(f"\nStep 2: Loading LoRA adapters from:  {self.adapter_dir}")
        self.model = PeftModel.from_pretrained(
            base_model,
            self.adapter_dir,
            torch_dtype=torch.bfloat16 if self.load_in_4bit else torch.float16,
        )
        
        # Merge adapters for faster inference (optional)
        # Uncomment if you want to merge (uses more memory but faster)
        # print("Merging LoRA adapters with base model...")
        # self.model = self.model.merge_and_unload()
        
        self.model.eval()
        
        print("✓ QLoRA model loaded successfully!")
        
        # Print model info
        try:
            from peft import get_peft_model_state_dict
            trainable_params = sum(p. numel() for p in self.model.parameters() if p.requires_grad)
            all_params = sum(p.numel() for p in self.model.parameters())
            print(f"\nModel info:")
            print(f"  Total parameters: {all_params:,}")
            print(f"  Trainable parameters: {trainable_params:,}")
            print(f"  Trainable %: {100 * trainable_params / all_params:.4f}%")
        except:
            pass

    def load_test_data(self):
        """Load test data"""
        print("\nLoading test data...")
        all_test_data = []
        
        # Load Urdu test data
        if self.urdu_folder is not None :
            urdu_test_path = os.path.join(self.urdu_folder, 'test.json')
            if os.path.exists(urdu_test_path):
                with open(urdu_test_path, 'r', encoding='utf-8') as f:
                    urdu_data = json.load(f)
                    for item in urdu_data: 
                        item['language'] = 'urdu'
                    all_test_data.extend(urdu_data)
                print(f"Loaded {len(urdu_data)} Urdu test samples")
        
        # Load English test data
        if self.english_folder is not None :
            english_test_path = os. path.join(self.english_folder, 'test.json')
            if os.path.exists(english_test_path):
                with open(english_test_path, 'r', encoding='utf-8') as f:
                    english_data = json.load(f)
                    for item in english_data:
                        item['language'] = 'english'
                    all_test_data. extend(english_data)
                print(f"Loaded {len(english_data)} English test samples")
        
        print(f"Total test samples: {len(all_test_data)}")
        return all_test_data

    def load_checkpoint(self):
        """Load evaluation checkpoint"""
        checkpoint_file = os.path.join(self.output_dir, 'evaluation_checkpoint.pkl')
        if os.path.exists(checkpoint_file):
            print(f"\nFound checkpoint: {checkpoint_file}")
            with open(checkpoint_file, 'rb') as f:
                checkpoint = pickle.load(f)
            print(f"Resuming from sample {checkpoint['last_processed_idx'] + 1}")
            return checkpoint
        return None

    def save_checkpoint(self, checkpoint_data):
        """Save evaluation checkpoint"""
        checkpoint_file = os.path.join(self. output_dir, 'evaluation_checkpoint.pkl')
        with open(checkpoint_file, 'wb') as f:
            pickle.dump(checkpoint_data, f)

    def normalize_labels(self, labels:  List[str]) -> str:
        """Normalize labels"""
        normalized = []
        for label in labels:
            if label in self. label_mapping:
                norm_label = self.label_mapping[label]
            else:
                norm_label = label. strip().lower()
            if norm_label in self.valid_labels:
                normalized.append(norm_label)
        
        # Remove duplicates
        seen = set()
        normalized = [x for x in normalized if not (x in seen or seen.add(x))]
        
        if not normalized and self.valid_labels:
            normalized. append(self.valid_labels[0])
        
        return ', '.join(normalized) if normalized else self.valid_labels[0] if self.valid_labels else 'other'

    def parse_predicted_labels(self, generated_text: str) -> List[str]:
        """
        Parse predicted labels from generated text
        IMPROVED: Better parsing for Qwen chat format
        """
        # Remove any instruction parts
        text = generated_text.lower().strip()
        
        # Try to extract just the labels part
        if "<|im_end|>" in text: 
            # Split by assistant response
            parts = text.split("<|im_start|>assistant")
            if len(parts) > 1:
                text = parts[-1].replace("<|im_end|>", "").strip()
        
        # Remove common artifacts
        text = text.replace('"', '').replace("'", '').replace('[', '').replace(']', '').strip()
        text = text.split('\n')[0].strip()  # Take first line only
        
        # Split by comma
        predicted_labels = [label.strip() for label in text.split(',')]
        
        # Validate against valid labels
        valid_predictions = []
        for label in predicted_labels:
            if label in self.valid_labels:
                valid_predictions.append(label)
            else:
                # Try fuzzy matching
                for valid_label in self.valid_labels:
                    if valid_label in label or label in valid_label:
                        valid_predictions.append(valid_label)
                        break
        
        # Remove duplicates
        seen = set()
        valid_predictions = [x for x in valid_predictions if not (x in seen or seen.add(x))]
        
        return valid_predictions if valid_predictions else [self.valid_labels[0]] if self.valid_labels else ['other']

    def predict_batch(self, articles: List[str]):
        """
        Predict labels for a batch of articles
        IMPROVED: Using Qwen chat template format (same as training)
        """
        input_texts = []
        
        for article in articles:
            # Use same format as training
            prompt = f"""<|im_start|>system
You are an expert crime news classifier. Your task is to classify news articles into one or more crime categories. <|im_end|>
<|im_start|>user
Classify the following news article into one or more of these crime categories: 
{', '.join(self.valid_labels)}

Instructions:
- Select ALL categories that apply (this is multi-label classification)
- Output ONLY the category names, separated by commas
- If multiple categories apply, list all of them
- Use only the exact category names provided above
- Do not add explanations or extra text

News Article: 
{article}<|im_end|>
<|im_start|>assistant
"""
            input_texts.append(prompt)
        
        # Tokenize
        inputs = self. tokenizer(
            input_texts,
            return_tensors="pt",
            truncation=True,
            max_length=self.max_length,
            padding=True
        )
        inputs = {k: v.to(self.device) for k, v in inputs. items()}
        
        # Generate predictions
        with torch.no_grad():
            if self.load_in_4bit:
                # Use bfloat16 for 4-bit models
                with torch.cuda.amp.autocast(dtype=torch.bfloat16):
                    outputs = self.model.generate(
                        **inputs,
                        max_new_tokens=50,  # Increased for multi-label
                        do_sample=False,  # Greedy decoding for consistency
                        pad_token_id=self.tokenizer.pad_token_id,
                        eos_token_id=self.tokenizer.eos_token_id,
                        num_beams=1,
                        use_cache=True,
                        temperature=None,  # Disable sampling
                        top_p=None,
                    )
            else:
                with torch.cuda.amp.autocast():
                    outputs = self.model.generate(
                        **inputs,
                        max_new_tokens=50,
                        do_sample=False,
                        pad_token_id=self.tokenizer.pad_token_id,
                        eos_token_id=self. tokenizer.eos_token_id,
                        num_beams=1,
                        use_cache=True,
                    )
        
        # Decode predictions
        predictions = []
        for i, output in enumerate(outputs):
            # Extract only the generated tokens (not the input)
            generated_tokens = output[inputs['input_ids'][i].shape[0]:]
            generated_text = self.tokenizer. decode(generated_tokens, skip_special_tokens=True)
            predicted_labels = self.parse_predicted_labels(generated_text)
            predictions.append(predicted_labels)
        
        return predictions

    def evaluate(self, resume:  bool = True):
        """Evaluate the model"""
        # Load model
        self.load_model()
        
        # Load test data
        test_data = self.load_test_data()
        
        # Initialize or load checkpoint
        if resume: 
            checkpoint = self.load_checkpoint()
        else:
            checkpoint = None
        
        if checkpoint:
            start_idx = checkpoint['last_processed_idx'] + 1
            y_true_single = checkpoint['y_true_single']
            y_pred_single = checkpoint['y_pred_single']
            y_true_multilabel = checkpoint['y_true_multilabel']
            y_pred_multilabel = checkpoint['y_pred_multilabel']
            all_predictions = checkpoint. get('all_predictions', [])
        else:
            start_idx = 0
            y_true_single = []
            y_pred_single = []
            y_true_multilabel = []
            y_pred_multilabel = []
            all_predictions = []
        
        print(f"\nStarting evaluation from sample {start_idx}")
        print(f"Total samples to process: {len(test_data) - start_idx}")
        
        # Process in batches with progress bar
        with tqdm(total=len(test_data) - start_idx, desc="Evaluating", unit="sample") as pbar:
            for batch_start in range(start_idx, len(test_data), self.batch_size):
                batch_end = min(batch_start + self.batch_size, len(test_data))
                batch = test_data[batch_start: batch_end]
                
                # Prepare articles
                articles = []
                true_labels_batch = []
                
                for example in batch:
                    title = example. get('title', '')
                    content = example.get('content', '')
                    article = f"{title}\n\n{content}".strip()
                    articles.append(article)
                    
                    # Get true labels
                    true_labels_raw = example.get('final_labels', [])
                    if not isinstance(true_labels_raw, list):
                        true_labels_raw = [true_labels_raw]
                    true_labels = self.normalize_labels(true_labels_raw).split(', ')
                    true_labels_batch.append(true_labels)
                
                # Predict batch
                try:
                    predictions_batch = self.predict_batch(articles)
                except Exception as e:
                    print(f"\nError processing batch {batch_start}-{batch_end}: {e}")
                    # Process one by one if batch fails
                    predictions_batch = []
                    for article in articles:
                        try: 
                            pred = self.predict_batch([article])[0]
                            predictions_batch.append(pred)
                        except: 
                            predictions_batch.append([self.valid_labels[0]])
                
                # Store results
                for i, (true_labels, predicted_labels) in enumerate(zip(true_labels_batch, predictions_batch)):
                    y_true_single.append(true_labels[0])
                    y_pred_single.append(predicted_labels[0])
                    
                    true_binary = [1 if label in true_labels else 0 for label in self.valid_labels]
                    pred_binary = [1 if label in predicted_labels else 0 for label in self.valid_labels]
                    y_true_multilabel.append(true_binary)
                    y_pred_multilabel.append(pred_binary)
                    
                    all_predictions.append({
                        'idx': batch_start + i,
                        'title': batch[i].get('title', '')[:100],
                        'language': batch[i].get('language', 'unknown'),
                        'true_labels': true_labels,
                        'predicted_labels': predicted_labels
                    })
                
                # Update progress bar
                pbar.update(len(batch))
                
                # Save checkpoint periodically
                if (batch_end % self.checkpoint_every < self.batch_size) or batch_end == len(test_data):
                    checkpoint_data = {
                        'last_processed_idx': batch_end - 1,
                        'y_true_single': y_true_single,
                        'y_pred_single': y_pred_single,
                        'y_true_multilabel': y_true_multilabel,
                        'y_pred_multilabel':  y_pred_multilabel,
                        'all_predictions': all_predictions
                    }
                    self.save_checkpoint(checkpoint_data)
                    
                    # Save intermediate results
                    if batch_end < len(test_data):
                        self.save_intermediate_results(
                            y_true_single, y_pred_single,
                            y_true_multilabel, y_pred_multilabel,
                            all_predictions, batch_end
                        )
        
        print("\n" + "="*70)
        print("Evaluation Complete!")
        print("="*70)
        
        # Calculate and save final results
        results = self.calculate_metrics(
            y_true_single, y_pred_single,
            y_true_multilabel, y_pred_multilabel,
            all_predictions
        )
        
        # Clean up checkpoint
        checkpoint_file = os.path.join(self.output_dir, 'evaluation_checkpoint.pkl')
        if os.path.exists(checkpoint_file):
            os.remove(checkpoint_file)
            print("\nCheckpoint file removed (evaluation complete)")
        
        return results

    def save_intermediate_results(self, y_true_single, y_pred_single,
                                   y_true_multilabel, y_pred_multilabel,
                                   all_predictions, samples_processed):
        """Save intermediate results"""
        intermediate_file = os.path.join(self.output_dir, f'intermediate_results_{samples_processed}.json')
        
        # Calculate current metrics
        precision, recall, f1, _ = precision_recall_fscore_support(
            y_true_single, y_pred_single, average='weighted', zero_division=0
        )
        
        results = {
            'samples_processed': samples_processed,
            'single_label':  {
                'precision': float(precision),
                'recall':  float(recall),
                'f1_score': float(f1)
            },
            'sample_predictions': all_predictions[-10:]  # Last 10 predictions
        }
        
        with open(intermediate_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

    def calculate_metrics(self, y_true_single, y_pred_single,
                         y_true_multilabel, y_pred_multilabel, all_predictions):
        """Calculate and save metrics"""
        print("\n" + "="*70)
        print(f"{self.language. upper()} QLoRA MODEL EVALUATION RESULTS")
        print("="*70)
        
        # Single-label metrics
        precision, recall, f1, _ = precision_recall_fscore_support(
            y_true_single, y_pred_single, average='weighted', zero_division=0
        )
        
        print(f"\nSingle-Label Metrics (First Label Only):")
        print(f"  Precision: {precision:.4f}")
        print(f"  Recall: {recall:.4f}")
        print(f"  F1-Score: {f1:.4f}")
        
        print("\n" + "-"*70)
        print("Classification Report:")
        print("-"*70)
        print(classification_report(y_true_single, y_pred_single, zero_division=0))
        
        # Multi-label metrics
        y_true_ml = np.array(y_true_multilabel)
        y_pred_ml = np.array(y_pred_multilabel)
        
        print("\n" + "="*70)
        print("Multi-Label Metrics (All Labels):")
        print("="*70)
        print(f"\n{'Label':<40} {'Precision':<12} {'Recall':<12} {'F1-Score':<12} {'Support'}")
        print("-"*100)
        
        per_label_metrics = {}
        for i, label in enumerate(self.valid_labels):
            actual_support = int(np.sum(y_true_ml[: , i]))
            
            try:
                prec, rec, f1_score, sup = precision_recall_fscore_support(
                    y_true_ml[:, i],
                    y_pred_ml[:, i],
                    average='binary',
                    zero_division=0
                )
                
                prec_val = float(prec) if prec is not None else 0.0
                rec_val = float(rec) if rec is not None else 0.0
                f1_val = float(f1_score) if f1_score is not None else 0.0
                sup_val = int(sup) if sup is not None else actual_support
                
            except Exception as e:
                print(f"Warning: Error calculating metrics for {label}: {e}")
                prec_val = 0.0
                rec_val = 0.0
                f1_val = 0.0
                sup_val = actual_support
            
            print(f"{label:<40} {prec_val:<12.4f} {rec_val:<12.4f} {f1_val:<12.4f} {sup_val}")
            
            per_label_metrics[label] = {
                'precision': prec_val,
                'recall':  rec_val,
                'f1_score': f1_val,
                'support': sup_val
            }
        
        # Calculate micro averages
        try:
            precision_micro, recall_micro, f1_micro, _ = precision_recall_fscore_support(
                y_true_ml. ravel(),
                y_pred_ml.ravel(),
                average='binary',
                zero_division=0
            )
            precision_micro = float(precision_micro) if precision_micro is not None else 0.0
            recall_micro = float(recall_micro) if recall_micro is not None else 0.0
            f1_micro = float(f1_micro) if f1_micro is not None else 0.0
        except: 
            precision_micro = 0.0
            recall_micro = 0.0
            f1_micro = 0.0
        
        print(f"\n{'Micro Average':<40} {precision_micro:<12.4f} {recall_micro:<12.4f} {f1_micro:<12.4f}")
        
        # Save results
        results = {
            'model_type': 'QLoRA',
            'base_model': self.base_model_name,
            'adapter_dir': self.adapter_dir,
            'language': self.language,
            'total_samples': len(y_true_single),
            'single_label':  {
                'precision': float(precision),
                'recall':  float(recall),
                'f1_score': float(f1),
                'classification_report': classification_report(y_true_single, y_pred_single, output_dict=True, zero_division=0)
            },
            'multi_label':  {
                'precision_micro': precision_micro,
                'recall_micro': recall_micro,
                'f1_micro': f1_micro,
                'per_label_metrics': per_label_metrics
            }
        }
        
        results_file = os.path.join(self.output_dir, f'{self.language}_qlora_evaluation_results.json')
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        predictions_file = os.path.join(self.output_dir, f'{self.language}_qlora_predictions.json')
        with open(predictions_file, 'w', encoding='utf-8') as f:
            json.dump(all_predictions, f, indent=2, ensure_ascii=False)
        
        print(f"\n{'='*70}")
        print(f"Results saved to: {results_file}")
        print(f"Predictions saved to: {predictions_file}")
        print("="*70)
        
        return results


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="QLoRA Model Evaluation with Checkpointing")
    parser.add_argument("--base_model", type=str, default="Qwen/Qwen2.5-7B-Instruct",
                       help="Base model name (Hugging Face)")
    parser.add_argument("--adapter_dir", type=str, 
                       default="/work/pi_bhatt_umass_edu/farah_urdu/qwen_bilingual_finetuned_qlora_improved/checkpoint-7750",
                       help="Directory containing LoRA adapters")
    parser.add_argument("--urdu_folder", type=str, default="./Urdu",
                       help="Folder containing Urdu test data")
    parser.add_argument("--english_folder", type=str, default="./English",
                       help="Folder containing English test data")
    parser.add_argument("--output_dir", type=str, default="./evaluation_results_qlora_bilingual",
                       help="Output directory for results")
    parser.add_argument("--batch_size", type=int, default=8,
                       help="Batch size for evaluation (default: 8)")
    parser.add_argument("--checkpoint_every", type=int, default=500,
                       help="Save checkpoint every N samples (default: 500)")
    parser.add_argument("--max_length", type=int, default=2048,
                       help="Max input length (default: 2048)")
    parser.add_argument("--no_resume", action="store_true", default=True,
                       help="Start fresh evaluation (ignore checkpoint)")
    parser.add_argument("--language", type=str, default="both", choices=["english", "urdu", "both"],
                       help="Language to evaluate (default: english)")
    parser.add_argument("--load_in_fp16", action="store_true",
                       help="Load model in FP16 instead of 4-bit (uses more memory)")
    
    args = parser.parse_args()
    
    print("="*70)
    print("QLoRA Model Evaluation")
    print("="*70)
    print(f"Base model: {args.base_model}")
    print(f"Adapter directory: {args.adapter_dir}")
    print(f"Urdu folder: {args.urdu_folder}")
    print(f"English folder: {args.english_folder}")
    print(f"Output directory: {args.output_dir}")
    print(f"Batch size: {args. batch_size}")
    print(f"Max length: {args.max_length}")
    print(f"Checkpoint every: {args.checkpoint_every} samples")
    print(f"Language: {args.language}")
    print(f"Load in 4-bit: {not args.load_in_fp16}")
    print(f"Resume:  {not args.no_resume}")
    print("="*70)
    
    evaluator = QLoRAEvaluator(
        base_model_name=args.base_model,
        adapter_dir=args. adapter_dir,
        urdu_folder=args.urdu_folder,
        english_folder=args.english_folder,
        output_dir=args.output_dir,
        checkpoint_every=args.checkpoint_every,
        batch_size=args.batch_size,
        max_length=args.max_length,
        language=args.language,
        load_in_4bit=not args.load_in_fp16,
    )
    
    results = evaluator.evaluate(resume=not args.no_resume)
    
    print("\n" + "="*70)
    print("EVALUATION COMPLETE!")
    print("="*70)
    print(f"\nFinal Results:")
    print(f"  Single-Label F1-Score: {results['single_label']['f1_score']:.4f}")
    print(f"  Multi-Label F1-Score (Micro): {results['multi_label']['f1_micro']:.4f}")
    print(f"  Total Samples Evaluated: {results['total_samples']}")
    print("="*70)


if __name__ == "__main__":
    main()