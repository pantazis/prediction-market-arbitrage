# Smart Semantic Matcher

## Overview

`smart_matcher.py` is a production-grade semantic matching engine that uses AI embeddings to find arbitrage opportunities between Polymarket and Kalshi markets.

**Key Innovation**: Replaces traditional regex/keyword filtering with deep semantic understanding using Sentence-BERT embeddings.

## Features

✅ **AI-Powered Matching** - Uses SBERT (Sentence-BERT) for semantic similarity  
✅ **Safety First** - Strict date/time proximity checks to prevent basis risk  
✅ **Group Market Support** - Handles Polymarket election subcategories  
✅ **Binary Focus** - Filters for clean Yes/No markets only  
✅ **Robust Parsing** - Handles mixed date formats and timezones  
✅ **Fast** - GPU-accelerated embeddings (falls back to CPU)  
✅ **Scalable** - No manual rule maintenance required  

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

Required packages:
- `sentence-transformers>=2.2.0`
- `numpy>=1.24.0`
- `python-dateutil>=2.9.0`

### 2. Prepare Input Data

Download market data using the existing downloader:

```bash
python scripts/download_markets.py --kalshi --poly --max-markets 500
```

Or manually place these files in your working directory:
- `kalshi_markets.json` - Kalshi market dump
- `polymarket_markets.json` - Polymarket market dump

### 3. Run the Matcher

```bash
python smart_matcher.py
```

Output:
- `smart_pairs.json` - Ranked candidate pairs

### 4. Test with Sample Data

```bash
python test_smart_matcher.py
```

This creates synthetic test data and validates the matching pipeline.

## How It Works

### 1. Filtering Stage

**Polymarket Markets:**
- ✅ `active=True`, `closed=False`
- ✅ Binary outcomes: `["Yes", "No"]`
- ✅ Valid `endDate` and `clobTokenIds`
- ✅ **NEW**: Group markets allowed (e.g., Elections)

**Kalshi Markets:**
- ✅ `status='active'`, `market_type='binary'`
- ❌ Excludes: combo, parlay, same-game, tri-fecta

### 2. Text Representation

Creates rich semantic embeddings from:

| Source | Fields Used |
|--------|-------------|
| **Polymarket** | `groupItemTitle` + `question` + `description` |
| **Kalshi** | `title` + `subtitle` + `rules_primary` |

Normalization:
- Lowercase conversion
- URL removal
- Financial term standardization (`$` → `usd`, `%` → `percent`)
- Special character removal

### 3. Semantic Matching

```python
model = SentenceTransformer('all-MiniLM-L6-v2')

# Encode all markets
kalshi_embeddings = model.encode(kalshi_texts)
poly_embeddings = model.encode(poly_texts)

# Compute cosine similarity
similarities = cosine_similarity(kalshi_embeddings, poly_embeddings)
```

**Thresholds:**
- Minimum similarity: `0.60` (60%)
- Maximum date difference: `24 hours`

### 4. Safety Layer

Hard rejection if:
- Date difference > 24 hours
- Either market missing expiration date
- Similarity score < threshold

## Configuration

Edit `smart_matcher.py` to adjust:

```python
find_smart_pairs(
    kalshi_list,
    poly_list,
    model_name='all-MiniLM-L6-v2',  # Change model
    min_similarity=0.60,             # Stricter = fewer matches
    max_hours_diff=24                # Date proximity window
)
```

### Available Models

| Model | Size | Speed | Accuracy |
|-------|------|-------|----------|
| `all-MiniLM-L6-v2` | 80MB | Fast | Good (Default) |
| `all-mpnet-base-v2` | 420MB | Medium | Excellent |
| `paraphrase-MiniLM-L3-v2` | 60MB | Very Fast | Decent |

## Output Format

`smart_pairs.json`:

```json
[
  {
    "similarity_score": 0.8532,
    "time_diff_hours": 2.5,
    "kalshi": {
      "ticker": "PRES-TRUMP-2024",
      "title": "Will Donald Trump win the 2024 Presidential Election?",
      "expiry": "2024-11-05T23:59:00+00:00",
      "yes_price": 0.45,
      "no_price": 0.53
    },
    "polymarket": {
      "id": "0x123abc...",
      "question": "Trump to win 2024 US Presidential Election?",
      "expiry": "2024-11-06T02:00:00+00:00",
      "tokens": ["0xYES", "0xNO"]
    }
  }
]
```

Sorted by `similarity_score` (descending).

## Advantages Over Regex Filtering

| Feature | Regex/Keywords | Semantic Matcher |
|---------|----------------|------------------|
| Paraphrase Detection | ❌ | ✅ |
| Typo Tolerance | ❌ | ✅ |
| Context Understanding | ❌ | ✅ |
| Manual Maintenance | 😡 High | 😊 None |
| Multilingual Support | ❌ | ✅ (50+ languages) |
| Scalability | 🐌 Poor | 🚀 Excellent |

## Performance

**Typical Run (500 markets each):**
- Model loading: ~2 seconds
- Encoding: ~10 seconds (CPU) / ~2 seconds (GPU)
- Similarity computation: <1 second
- Total: **~15 seconds**

**Memory:**
- Model: ~80MB RAM
- Embeddings cache: ~5MB per 100 markets

## Integration with Arbitrage Engine

### Current Status
Standalone candidate generator

### Future Integration
```python
# Replace existing matchers.py logic
from smart_matcher import find_smart_pairs

# In engine initialization
candidates = find_smart_pairs(kalshi_markets, poly_markets)

# Convert to Market pairs
for pair in candidates:
    kalshi_market = load_market(pair['kalshi'])
    poly_market = load_market(pair['polymarket'])
    engine.add_pair(kalshi_market, poly_market)
```

## Troubleshooting

### Model Download Fails
```bash
# Pre-download model
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"
```

### GPU Not Detected
Automatic fallback to CPU. To force GPU:
```python
import torch
model = SentenceTransformer('all-MiniLM-L6-v2', device='cuda')
```

### Memory Issues
Use smaller model or batch processing:
```python
# Process markets in chunks
for chunk in chunks(markets, size=100):
    encode_chunk(chunk)
```

## References

- [Sentence-BERT Paper](https://arxiv.org/abs/1908.10084)
- [sentence-transformers Docs](https://www.sbert.net/)
- [Model Hub](https://huggingface.co/sentence-transformers)

## License

Same as parent project.
