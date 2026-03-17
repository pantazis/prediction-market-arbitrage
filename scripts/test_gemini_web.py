#!/usr/bin/env python3
"""Test Gemini with Google Search grounding using new google.genai library."""

import os
from dotenv import load_dotenv
from google import genai
from google.genai.types import Tool, GoogleSearch

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    print("Error: GEMINI_API_KEY not found in .env")
    exit(1)

client = genai.Client(api_key=api_key)

print("Testing Gemini with Google Search grounding...")

# Create Google Search tool for grounding
google_search_tool = Tool(google_search=GoogleSearch())

response = client.models.generate_content(
    model="gemini-2.0-flash",
    contents="Browse polymarket.com and kalshi.com. What is ONE trending topic that appears on BOTH platforms right now? Return just the topic name.",
    config={
        "tools": [google_search_tool],
    }
)

print(f"\nResponse:\n{response.text}")

# Print grounding metadata if available
if hasattr(response, 'candidates') and response.candidates:
    candidate = response.candidates[0]
    if hasattr(candidate, 'grounding_metadata') and candidate.grounding_metadata:
        print(f"\nGrounding sources used: {len(candidate.grounding_metadata.grounding_chunks or [])} chunks")
