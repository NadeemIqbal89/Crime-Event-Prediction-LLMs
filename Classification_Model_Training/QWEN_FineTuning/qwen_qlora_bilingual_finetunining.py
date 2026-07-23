# Set environment variables FIRST before any imports
import os
os.environ["HF_TOKEN"] = "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"
os.environ['HF_HOME'] = '/work/pi_bhatt_umass_edu/farah_urdu/HuggingfaceCash'
os.environ['TOKENIZERS_PARALLELISM'] = 'false'

import json
import torch
import pandas as pd
from datasets import Dataset, DatasetDict
from transformers import (
    AutoTokenizer,
    AutoModelForCausalLM,
    TrainingArguments,
    Trainer,
    DataCollatorForLanguageModeling,
    BitsAndBytesConfig,
)
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training, TaskType
from sklearn.metrics import precision_recall_fscore_support, classification_report
import numpy as np
from typing import Dict, List, Optional
import warnings
import glob
from collections import Counter
warnings.filterwarnings('ignore')

class BilingualMultiLabelFineTuner: 
    def __init__(
        self,
        model_name: str = "Qwen/Qwen2.5-7B-Instruct",
        english_folder: str = "./English",  # NEW: Separate English folder
        urdu_folder: str = "./Urdu",        # NEW: Separate Urdu folder
        output_dir: str = "/work/pi_bhatt_umass_edu/farah_urdu/qwen_bilingual_finetuned_qlora_improved",
        checkpoint_dir: Optional[str] = None,
        label_mapping_file: Optional[str] = None
    ):
        self.model_name = model_name
        self.english_folder = english_folder
        self.urdu_folder = urdu_folder
        self.output_dir = output_dir
        self.checkpoint_dir = checkpoint_dir or output_dir
        self.label_mapping_file = label_mapping_file
        
        # Check if running in distributed mode
        self.is_distributed = int(os.environ.get('WORLD_SIZE', 1)) > 1
        self.local_rank = int(os.environ.get('LOCAL_RANK', 0))
        self.world_size = int(os.environ.get('WORLD_SIZE', 1))
        
        if self.is_distributed:
            print(f"[Rank {self.local_rank}/{self.world_size}] Distributed training detected")
        
        # Extract labels dynamically with class weights for imbalanced data
        self. valid_labels = []
        self.label_mapping = {}
        self.class_weights = {}
        self._extract_labels_from_data()
        
        # Initialize tokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(
            model_name, 
            token=os.environ.get("HF_TOKEN"),
            cache_dir='/work/pi_bhatt_umass_edu/farah_urdu/HuggingfaceCash/'
        )
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer. eos_token
        
        # Set padding side to right for instruction models
        self.tokenizer.padding_side = "right"
    
    def _extract_labels_from_data(self):
        """Extract unique labels from BOTH English and Urdu datasets"""
        if self.local_rank == 0:
            print("\n" + "="*70)
            print("Extracting Labels from English + Urdu Data")
            print("="*70)
        
        # Check if label mapping file exists
        if self. label_mapping_file and os.path.exists(self. label_mapping_file):
            if self.local_rank == 0:
                print(f"Loading labels from: {self.label_mapping_file}")
            with open(self.label_mapping_file, 'r', encoding='utf-8') as f:
                labels_info = json.load(f)
                self.valid_labels = labels_info.get('normalized_labels', [])
                self.label_mapping = labels_info.get('original_to_normalized', {})
                self.class_weights = labels_info.get('class_weights', {})
            if self.local_rank == 0:
                print(f"Loaded {len(self.valid_labels)} labels")
            return
        
        # Extract from BOTH data folders
        all_labels = set()
        label_counts = Counter()
        
        file_names = ['train. json', 'validation.json', 'test.json']
        
        # NEW: Process both English and Urdu folders
        for folder_name, folder_path in [("English", self.english_folder), ("Urdu", self.urdu_folder)]:
            if self.local_rank == 0:
                print(f"\nScanning {folder_name} folder:  {folder_path}")
            
            for file_name in file_names:
                file_path = os.path.join(folder_path, file_name)
                if os.path.exists(file_path):
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            data = data if isinstance(data, list) else [data]
                            
                            for example in data:
                                labels = example.get('final_labels', [])
                                if isinstance(labels, list):
                                    for label in labels:
                                        all_labels.add(label)
                                        label_counts[label] += 1
                                elif isinstance(labels, str):
                                    all_labels.add(labels)
                                    label_counts[labels] += 1
                        
                        if self.local_rank == 0:
                            print(f"  ✓ {file_name} ({len(data)} samples)")
                    except Exception as e:
                        if self.local_rank == 0:
                            print(f"  ✗ {file_name}:  {e}")
        
        # Normalize labels
        self.label_mapping = {}
        normalized_labels = set()
        normalized_counts = Counter()
        
        for label, count in label_counts.items():
            normalized = label. strip().lower()
            self.label_mapping[label] = normalized
            normalized_labels.add(normalized)
            normalized_counts[normalized] += count
        
        self.valid_labels = sorted(list(normalized_labels))
        
        # Calculate class weights for imbalanced data
        total_count = sum(normalized_counts.values())
        num_classes = len(self.valid_labels)
        
        for label in self.valid_labels:
            count = normalized_counts. get(label, 1)
            self.class_weights[label] = total_count / (num_classes * count)
        
        # Normalize weights so minimum weight is 1.0
        min_weight = min(self.class_weights.values())
        self.class_weights = {k: v/min_weight for k, v in self.class_weights.items()}
        
        if self.local_rank == 0:
            print(f"\n{'='*70}")
            print(f"Found {len(all_labels)} original labels")
            print(f"Normalized to {len(self.valid_labels)} unique labels")
            print(f"Total samples across both languages: {sum(label_counts.values())}")
            print(f"{'='*70}")
            
            print("\nLabel Distribution & Class Weights (Combined):")
            print(f"{'Label':<40} {'Count':<10} {'Weight':<10}")
            print("-"*60)
            for label in self.valid_labels:
                count = normalized_counts.get(label, 0)
                weight = self.class_weights.get(label, 1.0)
                print(f"{label:<40} {count:<10} {weight:<10.3f}")
            
            print(f"\n{'='*70}")
            print("All Normalized Labels:")
            print(f"{'='*70}")
            for i, label in enumerate(self.valid_labels, 1):
                print(f"{i: 3d}. {label}")
            print(f"{'='*70}\n")
            
            # Save labels to file
            labels_info = {
                'all_labels': sorted(list(all_labels)),
                'normalized_labels': self.valid_labels,
                'original_to_normalized': self. label_mapping,
                'label_counts': dict(normalized_counts),
                'class_weights': self.class_weights
            }
            
            labels_file = os.path.join(self.output_dir, 'extracted_labels.json')
            os.makedirs(self.output_dir, exist_ok=True)
            with open(labels_file, 'w', encoding='utf-8') as f:
                json.dump(labels_info, f, indent=2, ensure_ascii=False)
            print(f"Labels and weights saved to: {labels_file}\n")
    
    def find_latest_checkpoint(self) -> Optional[str]:
        """Find the latest checkpoint in the output directory"""
        checkpoints = glob.glob(os. path.join(self.checkpoint_dir, "checkpoint-*"))
        if not checkpoints:
            return None
        
        checkpoints.sort(key=lambda x: int(x.split("-")[-1]))
        latest_checkpoint = checkpoints[-1]
        
        if self.local_rank == 0:
            print(f"\n{'='*70}")
            print(f"Found latest checkpoint: {latest_checkpoint}")
            print(f"{'='*70}\n")
        
        return latest_checkpoint
    
    def load_json_file(self, file_path: str) -> List[Dict]:
        """Load JSON data from file"""
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, list) else [data]
    
    def load_dataset_from_folders(self) -> Dict[str, List[Dict]]:
        """Load and merge training, validation, and test files from BOTH folders"""
        datasets = {'train': [], 'validation': [], 'test': []}
        file_mapping = {
            'train': 'train.json',
            'validation': 'validation.json',
            'test': 'test.json'
        }
        
        # NEW: Load from both English and Urdu folders and merge
        for folder_name, folder_path in [("English", self.english_folder), ("Urdu", self.urdu_folder)]:
            if self. local_rank == 0:
                print(f"\nLoading {folder_name} data from: {folder_path}")
            
            for split, file_name in file_mapping. items():
                file_path = os.path.join(folder_path, file_name)
                if os.path.exists(file_path):
                    data = self.load_json_file(file_path)
                    
                    # NEW: Add language tag to each example
                    for item in data:
                        item['language'] = folder_name. lower()
                    
                    datasets[split].extend(data)
                    
                    if self.local_rank == 0:
                        print(f"  ✓ {split}. json:  {len(data)} samples")
                else:
                    if self.local_rank == 0:
                        print(f"  ✗ {file_name} not found")
        
        # Print merged statistics
        if self.local_rank == 0:
            print(f"\n{'='*70}")
            print("Merged Dataset Statistics:")
            print(f"{'='*70}")
            for split in ['train', 'validation', 'test']:
                total = len(datasets[split])
                english_count = sum(1 for x in datasets[split] if x. get('language') == 'english')
                urdu_count = sum(1 for x in datasets[split] if x.get('language') == 'urdu')
                print(f"{split. capitalize(): <15}:  {total:>6} samples (English:  {english_count}, Urdu: {urdu_count})")
            print(f"{'='*70}\n")
        
        return datasets
    
    def normalize_labels(self, labels: List[str]) -> str:
        """Normalize labels using the extracted mapping"""
        normalized = []
        
        for label in labels:
            if label in self.label_mapping:
                norm_label = self.label_mapping[label]
            else:
                norm_label = label. strip().lower()
            
            if norm_label in self.valid_labels:
                normalized.append(norm_label)
        
        # Remove duplicates while preserving order
        seen = set()
        normalized = [x for x in normalized if not (x in seen or seen.add(x))]
        
        if not normalized and self.valid_labels:
            normalized. append(self.valid_labels[0])
        
        return ', '.join(normalized) if normalized else self.valid_labels[0] if self.valid_labels else 'other'
    
    def prepare_text_for_training(self, example: Dict) -> str:
        """
        Convert JSON example to instruction-tuning format
        Works for BOTH English and Urdu text
        """
        title = example.get('title', '')
        content = example.get('content', '')
        article = f"{title}\n\n{content}".strip()
        
        raw_labels = example.get('final_labels', [])
        if not isinstance(raw_labels, list):
            raw_labels = [raw_labels]
        
        labels = self.normalize_labels(raw_labels)
        
        # Same prompt format works for both languages (Qwen is multilingual)
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
{labels}<|im_end|>"""
        
        return prompt
    
    def create_datasets(self) -> DatasetDict:
        """Create merged datasets from English + Urdu data"""
        if self.local_rank == 0:
            print("\n" + "="*70)
            print("Creating Bilingual Datasets (English + Urdu)")
            print("="*70)
        
        data = self.load_dataset_from_folders()
        
        # Check we have training data
        if len(data['train']) == 0: 
            raise ValueError("No training data found!  Please check that train.json exists in both folders.")
        
        # Create datasets
        dataset_dict = {}
        for split in ['train', 'validation', 'test']:
            split_data = data[split]
            if split_data:
                texts = [self.prepare_text_for_training(example) for example in split_data]
                labels = [example.get('final_labels', []) for example in split_data]
                languages = [example.get('language', 'unknown') for example in split_data]
                
                df = pd.DataFrame({
                    'text': texts,
                    'labels': labels,
                    'language': languages,
                    'raw_data': split_data
                })
                dataset_dict[split] = Dataset.from_pandas(df)
                
                if self.local_rank == 0:
                    print(f"\n{split.capitalize()} dataset created:  {len(df)} samples")
        
        return DatasetDict(dataset_dict)
    
    def tokenize_function(self, examples):
        """Tokenize the text data with proper truncation"""
        tokenized = self.tokenizer(
            examples['text'],
            padding='max_length',
            truncation=True,
            max_length=2048,
            return_tensors=None
        )
        # Copy input_ids to labels for causal LM
        tokenized['labels'] = tokenized['input_ids'].copy()
        return tokenized
    
    def setup_model_for_training(self):
        """Setup model for QLoRA fine-tuning with optimized config"""
        if self.local_rank == 0:
            print(f"\nLoading model: {self.model_name}")
            print(f"Training mode: QLoRA (4-bit quantization + LoRA)")
            print(f"Training on {self.world_size} GPU(s)")
            print(f"Languages: English + Urdu (Bilingual)")
        
        # QLoRA Configuration - 4-bit quantization
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch. bfloat16,
            bnb_4bit_use_double_quant=True,
        )
        
        # Load model with 4-bit quantization
        model = AutoModelForCausalLM.from_pretrained(
            self.model_name,
            quantization_config=bnb_config,
            device_map={"": self.local_rank} if self.is_distributed else "auto",
            trust_remote_code=True,
            token=os.environ.get("HF_TOKEN"),
            cache_dir='/work/pi_bhatt_umass_edu/farah_urdu/HuggingfaceCash/',
            torch_dtype=torch.bfloat16,
        )
        
        # Prepare model for k-bit training
        model = prepare_model_for_kbit_training(model)
        
        # LoRA Configuration
        lora_config = LoraConfig(
            r=64,
            lora_alpha=128,
            target_modules=[
                "q_proj",
                "k_proj",
                "v_proj",
                "o_proj",
                "gate_proj",
                "up_proj",
                "down_proj",
            ],
            lora_dropout=0.1,
            bias="none",
            task_type=TaskType.CAUSAL_LM,
            modules_to_save=None,
        )
        
        # Apply LoRA to the model
        model = get_peft_model(model, lora_config)
        
        if self.local_rank == 0:
            model.print_trainable_parameters()
            
            trainable_params = sum(p. numel() for p in model.parameters() if p.requires_grad)
            all_params = sum(p.numel() for p in model.parameters())
            print(f"\n{'='*70}")
            print(f"QLoRA Configuration:")
            print(f"Quantization: 4-bit NF4 with double quantization")
            print(f"LoRA rank (r): {lora_config.r}")
            print(f"LoRA alpha: {lora_config.lora_alpha}")
            print(f"LoRA dropout: {lora_config. lora_dropout}")
            print(f"Target modules: {', '.join(lora_config. target_modules)}")
            print(f"Trainable params: {trainable_params: ,} || All params: {all_params: ,}")
            print(f"Trainable %: {100 * trainable_params / all_params:.4f}%")
            print(f"{'='*70}\n")
        
        return model
    
    def train(
        self,
        epochs: int = 5,
        batch_size: int = 4,
        learning_rate: float = 1e-4,
        resume_from_checkpoint: bool = True,
        save_steps: int = 250,
        save_total_limit: int = 1,
        gradient_accumulation_steps: int = 4,
        warmup_ratio: float = 0.1,
        max_length: int = 2048,
    ):
        """Fine-tune the model with QLoRA on bilingual data"""
        
        if self.local_rank == 0:
            print("\n" + "="*70)
            print("Preparing Bilingual Datasets")
            print("="*70)
        
        dataset = self.create_datasets()
        
        if self.local_rank == 0:
            print("\nTokenizing datasets...")
        
        # Get columns to remove
        columns_to_remove = dataset['train'].column_names
        
        tokenized_dataset = dataset.map(
            self.tokenize_function,
            batched=True,
            remove_columns=columns_to_remove,
            desc="Tokenizing" if self.local_rank == 0 else None
        )
        
        checkpoint = None
        if resume_from_checkpoint:
            checkpoint = self.find_latest_checkpoint()
        
        model = self.setup_model_for_training()
        
        effective_batch_size = batch_size * gradient_accumulation_steps * self.world_size
        
        if self.local_rank == 0:
            print(f"\n{'='*70}")
            print("Training Configuration")
            print(f"{'='*70}")
            print(f"Training Mode:  Bilingual QLoRA (English + Urdu)")
            print(f"Number of GPUs: {self.world_size}")
            print(f"Number of labels: {len(self.valid_labels)}")
            print(f"Training samples: {len(tokenized_dataset['train'])}")
            print(f"Validation samples: {len(tokenized_dataset. get('validation', []))}")
            print(f"Test samples:  {len(tokenized_dataset. get('test', []))}")
            print(f"Batch size per GPU: {batch_size}")
            print(f"Gradient accumulation steps: {gradient_accumulation_steps}")
            print(f"Effective batch size: {effective_batch_size}")
            print(f"Learning rate: {learning_rate}")
            print(f"Epochs: {epochs}")
            print(f"Warmup ratio: {warmup_ratio}")
            print(f"Max sequence length: {max_length}")
            print(f"Save steps: {save_steps}")
            print(f"Keep last {save_total_limit} checkpoints")
            if checkpoint:
                print(f"Resuming from:  {checkpoint}")
            print(f"{'='*70}\n")
        
        # Training arguments
        training_args = TrainingArguments(
            output_dir=self.output_dir,
            num_train_epochs=epochs,
            per_device_train_batch_size=batch_size,
            per_device_eval_batch_size=batch_size,
            gradient_accumulation_steps=gradient_accumulation_steps,
            learning_rate=learning_rate,
            
            # Multi-GPU settings
            ddp_find_unused_parameters=False if self.is_distributed else None,
            
            # Use BF16 for QLoRA
            bf16=True,
            bf16_full_eval=False,
            
            # Checkpointing
            save_strategy="steps",
            save_steps=save_steps,
            save_total_limit=save_total_limit,
            
            # Evaluation
            eval_strategy="steps",
            eval_steps=save_steps,
            load_best_model_at_end=False,
            metric_for_best_model="eval_loss",
            
            # Logging
            logging_dir=f"{self.output_dir}/logs",
            logging_strategy="steps",
            logging_steps=25,
            logging_first_step=True,
            
            # Performance
            dataloader_num_workers=4,
            dataloader_pin_memory=True,
            gradient_checkpointing=True,
            gradient_checkpointing_kwargs={"use_reentrant": False},
            
            # Warmup
            warmup_ratio=warmup_ratio,
            
            # Regularization
            max_grad_norm=0.3,
            weight_decay=0.01,
            
            # Optimizer
            optim="paged_adamw_8bit",
            
            # Learning rate schedule
            lr_scheduler_type="cosine",
            
            # Reporting
            report_to="tensorboard",
            remove_unused_columns=False,
            disable_tqdm=False if self.local_rank == 0 else True,
            
            # Additional settings
            group_by_length=False,
            length_column_name=None,
        )
        
        # Data collator
        data_collator = DataCollatorForLanguageModeling(
            tokenizer=self.tokenizer,
            mlm=False,
            pad_to_multiple_of=8,
        )
        
        trainer = Trainer(
            model=model,
            args=training_args,
            train_dataset=tokenized_dataset['train'],
            eval_dataset=tokenized_dataset.get('validation', tokenized_dataset. get('test')),
            data_collator=data_collator,
        )
        
        if self.local_rank == 0:
            print("\n" + "="*70)
            print("Starting Bilingual QLoRA Fine-Tuning")
            print("="*70 + "\n")
        
        trainer.train(resume_from_checkpoint=checkpoint)
        
        if self.local_rank == 0:
            print("\nSaving final model...")
            trainer.model.save_pretrained(self. output_dir)
            self.tokenizer.save_pretrained(self.output_dir)
            trainer.save_state()
            
            print(f"\nBilingual QLoRA adapter saved to: {self.output_dir}")
            print(f"Checkpoints saved to: {self.checkpoint_dir}")
            print("\nModel can handle both English and Urdu crime news classification!")
        
        if self.is_distributed:
            torch.distributed.barrier()
        
        return model, dataset, trainer


def main():
    """Main execution function"""
    
    config = {
        'model_name': "Qwen/Qwen2.5-7B-Instruct",
        'english_folder': "./English",
        'urdu_folder': "./Urdu",
        'output_dir': "/work/pi_bhatt_umass_edu/farah_urdu/qwen_bilingual_finetuned_qlora_improved",
        'epochs': 3,
        'batch_size': 4,
        'learning_rate': 1e-4,
        'resume_from_checkpoint': True,
        'save_steps': 250,
        'save_total_limit': 3,
        'gradient_accumulation_steps': 4,
        'warmup_ratio': 0.1,
        'max_length': 2048,
        'label_mapping_file': None,
    }
    
    finetuner = BilingualMultiLabelFineTuner(
        model_name=config['model_name'],
        english_folder=config['english_folder'],
        urdu_folder=config['urdu_folder'],
        output_dir=config['output_dir'],
        label_mapping_file=config. get('label_mapping_file')
    )
    
    if finetuner.local_rank == 0:
        print("="*70)
        print("Bilingual QLoRA Fine-Tuning (English + Urdu)")
        print("="*70)
        print(f"Model: {config['model_name']}")
        print(f"Training Mode: QLoRA (4-bit quantization + LoRA)")
        print(f"Languages: English + Urdu")
        print(f"Optimizations:  Imbalanced data handling, Multi-label support")
        print(f"English folder: {config['english_folder']}")
        print(f"Urdu folder: {config['urdu_folder']}")
        print(f"Output directory: {config['output_dir']}")
        print(f"Resume from checkpoint: {config['resume_from_checkpoint']}")
        print(f"Save last {config['save_total_limit']} checkpoints")
        print("="*70)
    
    model, dataset, trainer = finetuner.train(
        epochs=config['epochs'],
        batch_size=config['batch_size'],
        learning_rate=config['learning_rate'],
        resume_from_checkpoint=config['resume_from_checkpoint'],
        save_steps=config['save_steps'],
        save_total_limit=config['save_total_limit'],
        gradient_accumulation_steps=config['gradient_accumulation_steps'],
        warmup_ratio=config['warmup_ratio'],
        max_length=config['max_length'],
    )
    
    if finetuner.local_rank == 0:
        print("\n" + "="*70)
        print("Bilingual QLoRA Training Complete!")
        print("="*70)
        print("\nNext steps:")
        print("1. Check TensorBoard logs for training progress")
        print("2. Evaluate model on both English and Urdu test sets")
        print("3. Load model with:")
        print(f"   base_model = AutoModelForCausalLM. from_pretrained('{config['model_name']}')")
        print(f"   model = PeftModel.from_pretrained(base_model, '{config['output_dir']}')")
        print("\nThe model now supports crime classification in both English and Urdu!")


if __name__ == "__main__":
    main()