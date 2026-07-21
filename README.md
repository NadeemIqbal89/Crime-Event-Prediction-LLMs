This repository contains the source code accompanying the IEEE Access manuscript:

Crime Event Prediction and Time-Series Forecasting Using Unstructured Textual Data with Low-Resource Large Language Models

The repository provides implementations for news data collection, transformer-based crime event classification, large language model fine-tuning, and time-series forecasting experiments.
Contents
1. English News Web Scraper

Python scripts for collecting English-language news articles from publicly available online news archives.

2. Urdu News Web Scraper

Python scripts for collecting Urdu-language crime news articles from publicly available news websites.

3. BERT Model Training

Implementation for fine-tuning BERT-based models for crime event classification.

4. RoBERTa Model Training

Training and evaluation scripts for RoBERTa-based crime event classification.

5. LLaMA Fine-Tuning

Scripts and notebooks for fine-tuning LLaMA models for multilingual crime event classification.

6. Qwen Fine-Tuning

Implementation for fine-tuning Qwen models on the crime classification dataset.

7. Chronos Forecasting

Notebook implementing the Chronos time-series forecasting model for weekly crime prediction.

Dataset

The original datasets are not included in this repository because they were collected from publicly available news sources and contain processed research data.

Users may reproduce the dataset by running the provided web scrapers or adapt the code to their own data sources.


8. Forecasting Comparison Models

Notebook containing implementations of the forecasting models evaluated in the paper, together with the evaluation pipeline and comparison metrics.
