# Learning from Data – Final Project  
## Real-Time News Classification with Machine Learning and Deep Learning

---

## Project Description
This project presents a complete **learning-from-data pipeline** for multi-class text classification using **real-world, real-time scraped data**.  
Instead of relying on pre-built datasets, news articles are dynamically collected from public news websites via RSS feeds and processed into a structured dataset.

The task is formulated as a **five-class classification problem**, where each article is labeled as one of the following categories:

- Business  
- Health  
- Science  
- Technology  
- World  

Both **classical machine learning models** and a **deep learning model** are implemented, evaluated, and compared under the same experimental conditions.

---

## Dataset
- **Data source:** Real-time RSS-based web scraping from public news websites  
- **Total samples:** 2,661 news articles  
- **Class distribution:** Relatively balanced across all five categories  

### Data files
- `data/raw.jsonl`  
  Contains raw scraped articles including metadata and full text.
- `data/processed.csv`  
  Cleaned and preprocessed dataset used for modeling.

Duplicate articles are removed using URL-based checks, and the dataset can be incrementally expanded by rerunning the scraper.

---

## Project Structure
