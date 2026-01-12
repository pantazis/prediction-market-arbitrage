# Smart Matcher Quick Reference

## Installation
```bash
pip3 install sentence-transformers numpy python-dateutil
# OR
bash setup_smart_matcher.sh
```

## Basic Usage
```bash
# 1. Get market data
python3 scripts/download_markets.py --kalshi --poly --max-markets 500

# 2. Run matcher
python3 smart_matcher.py

# 3. View results
cat smart_pairs.json | jq '.[0:3]'
```

## Test
```bash
python3 test_smart_matcher.py
```

## Configuration
Edit `smart_matcher.py` line ~135:
```python
find_smart_pairs(
    kalshi_list, 
    poly_list,
    model_name='all-MiniLM-L6-v2',  # Model
    min_similarity=0.60,             # Threshold
    max_hours_diff=24                # Date window
)
```

## Key Parameters

| Parameter | Default | Range | Effect |
|-----------|---------|-------|--------|
| `min_similarity` | 0.60 | 0.50-0.80 | Higher = stricter matching |
| `max_hours_diff` | 24 | 12-72 | Date proximity window |
| `top_k` | 5 | 1-10 | Candidates per market |

## Output Structure
```json
{
  "similarity_score": 0.85,
  "time_diff_hours": 2.5,
  "kalshi": { "ticker", "title", "expiry" },
  "polymarket": { "id", "question", "expiry", "tokens" }
}
```

## Common Issues

**Missing dependencies**
```bash
pip3 install sentence-transformers
```

**No input files**
```bash
cd market_dumps/LATEST && cp *.json ../../ && cd ../..
```

**Model download slow**
```bash
# Pre-download (one-time, 80MB)
python3 -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"
```

## Files
- `smart_matcher.py` - Main implementation
- `test_smart_matcher.py` - Test suite  
- `SMART_MATCHER_README.md` - Full documentation
- `SMART_MATCHER_IMPLEMENTATION.md` - Implementation summary
- `setup_smart_matcher.sh` - Auto-setup script

## Key Features
✅ Semantic similarity (not just keywords)  
✅ Group market support (Elections, etc.)  
✅ Date proximity validation  
✅ Binary market filtering  
✅ Typo/paraphrase tolerance  
✅ Zero manual maintenance  

## Models Available

| Model | Size | Speed | Quality |
|-------|------|-------|---------|
| all-MiniLM-L6-v2 | 80MB | Fast | Good ✅ |
| all-mpnet-base-v2 | 420MB | Med | Best |
| paraphrase-MiniLM-L3-v2 | 60MB | Fastest | OK |

## Performance
- 500 markets: ~15 seconds (CPU) / ~3 seconds (GPU)
- Memory: ~100MB
- Scales: O(n*m) but parallelized

## Integration Status
- ✅ Standalone (current)
- 🔄 Engine integration (future)
- 🎯 Real-time streaming (roadmap)

---
📖 Full docs: [SMART_MATCHER_README.md](SMART_MATCHER_README.md)
