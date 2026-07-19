"""
AI Search Engine Module for EMAIL_AI.
Handles recursive file indexing with checksum-based caching, natural language query parsing
using Groq Llama 3.3 70B, relevance ranking, and semantic score matching.
"""

import json
import re
import os
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from groq import Groq
from config import Config
from tools.utils import setup_logger
from tools.extractor import extract_attachment_content

logger = setup_logger("search_engine")


class SearchEngine:
    """Orchestrates indexing of email files and execution of semantic search queries."""

    def __init__(self) -> None:
        self.index_file = Config.OUTPUTS_DIR / "search_index.json"
        self.index: Dict[str, Any] = {}
        self.load_index()

        # Initialize Groq client if key is configured
        if Config.GROQ_API_KEY and Config.GROQ_API_KEY != "gsk_your_groq_api_key_here":
            self.groq_client = Groq(api_key=Config.GROQ_API_KEY)
        else:
            self.groq_client = None

    def load_index(self) -> None:
        """Loads the search index from disk."""
        if self.index_file.exists():
            try:
                with open(self.index_file, "r", encoding="utf-8") as f:
                    self.index = json.load(f)
                logger.debug(f"Loaded search index containing {len(self.index)} files.")
            except Exception as e:
                logger.error(f"Failed to load search index: {e}. Starting fresh.")
                self.index = {}
        else:
            self.index = {}

    def save_index(self) -> None:
        """Saves the search index to disk."""
        try:
            with open(self.index_file, "w", encoding="utf-8") as f:
                json.dump(self.index, f, indent=2)
            logger.debug(f"Saved search index to {self.index_file.resolve()}")
        except Exception as e:
            logger.error(f"Failed to write search index to disk: {e}")

    def update_index(self) -> None:
        """
        Recursively scans reader/files/ for new or modified attachments.
        Updates the index with extracted text and keywords, skipping unchanged files.
        """
        logger.info("Starting incremental file indexing scan...")
        if not Config.DOWNLOAD_DIR.exists():
            logger.warning(f"Download directory does not exist: {Config.DOWNLOAD_DIR}")
            return

        index_changed = False
        valid_paths = set()

        # Recursively search all files under files/
        for file_path in Config.DOWNLOAD_DIR.rglob("*"):
            if not file_path.is_file() or file_path.name.startswith("."):
                continue

            # Calculate relative path to keep index portable
            try:
                rel_path = str(file_path.relative_to(Config.DOWNLOAD_DIR))
            except ValueError:
                continue

            valid_paths.add(rel_path)
            stat = file_path.stat()
            file_size = stat.st_size
            last_modified = stat.st_mtime

            # Check if file has already been indexed and is unmodified
            cached = self.index.get(rel_path)
            if cached and cached.get("file_size") == file_size and cached.get("last_modified") == last_modified:
                continue

            logger.info(f"Indexing new or modified file: {rel_path}")
            
            # Extract content using existing reader extractors
            try:
                extracted_text = extract_attachment_content(file_path)
            except Exception as e:
                logger.error(f"Failed to extract content from {rel_path}: {e}")
                extracted_text = f"[Extraction Error: {e}]"

            # Parse sender folder and timestamp folder from directory structure
            # Structure: reader/files/<sender_name>/<timestamp_folder>/<file>
            parts = file_path.relative_to(Config.DOWNLOAD_DIR).parts
            sender = parts[0] if len(parts) >= 3 else "unknown"
            timestamp_folder = parts[1] if len(parts) >= 3 else "unknown"

            # Extract human-readable downloaded time from timestamp folder name
            # Format: DD-MM-YYYY-(HH_MM_SS_mmm) -> DD-MM-YYYY HH:MM:SS
            match = re.match(r'(\d{2}-\d{2}-\d{4})-\((\d{2})_(\d{2})_(\d{2})_?\d*\)?', timestamp_folder)
            if match:
                downloaded_time = f"{match.group(1)} {match.group(2)}:{match.group(3)}:{match.group(4)}"
            else:
                downloaded_time = timestamp_folder

            # Generate basic keywords offline from text content
            words = re.findall(r'\b\w{4,15}\b', extracted_text.lower())
            keywords = list(set(words))[:15]  # Limit to top 15 words

            self.index[rel_path] = {
                "filename": file_path.name,
                "sender": sender,
                "timestamp_folder": timestamp_folder,
                "downloaded_time": downloaded_time,
                "doc_type": file_path.suffix.lower().lstrip("."),
                "extracted_text": extracted_text,
                "keywords": keywords,
                "file_size": file_size,
                "last_modified": last_modified
            }
            index_changed = True

        # Clean up files from index that were deleted from disk
        to_delete = [path for path in self.index if path not in valid_paths]
        if to_delete:
            for path in to_delete:
                logger.info(f"Removing deleted file from index: {path}")
                del self.index[path]
            index_changed = True

        if index_changed:
            self.save_index()
            logger.info(f"Indexing complete. Index now contains {len(self.index)} files.")
        else:
            logger.info("Indexing complete. No file modifications detected.")

    def parse_query_intent(self, user_query: str) -> Dict[str, Any]:
        """
        Uses Groq API to parse the natural language query intent into search filters.
        Falls back to regex parsing if the API is offline.
        """
        if self.groq_client:
            try:
                return self._parse_intent_with_groq(user_query)
            except Exception as e:
                logger.error(f"Groq query parsing failed: {e}. Falling back to keyword regex parser.")
        
        return self._parse_intent_with_regex(user_query)

    def _parse_intent_with_groq(self, user_query: str) -> Dict[str, Any]:
        """Calls Groq Llama 3.3 70B to parse query intent to JSON."""
        system_prompt = (
            "You are an expert search engine query parsing module.\n"
            "Your task is to parse a user's natural language request and extract search parameters. "
            "Respond ONLY with a valid JSON object. Do not include markdown formatting or explanations.\n\n"
            "The JSON object must contain the following keys exactly:\n"
            "- 'search_terms': string (the core keyword search terms, e.g. 'Aadhaar card', 'invoice', 'python')\n"
            "- 'filters': dict containing:\n"
            "  - 'sender': string or null (if user filters by sender, e.g. 'google', 'mittavenkatasaisujan')\n"
            "  - 'file_type': string or null (if filtering by extension, e.g. 'pdf', 'docx', 'xlsx')\n"
            "  - 'date_filter': string or null (relative date keywords like 'yesterday', 'today', or null)\n"
        )
        
        response = self.groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_query}
            ],
            temperature=0.0,
            response_format={"type": "json_object"}
        )
        
        raw_content = response.choices[0].message.content.strip()
        logger.debug(f"Groq intent parse result: {raw_content}")
        return json.loads(raw_content)

    def _parse_intent_with_regex(self, user_query: str) -> Dict[str, Any]:
        """Fallback query parsing using regex."""
        logger.debug("Running regex fallback query parser.")
        q_lower = user_query.lower()
        
        # 1. Detect file type filters
        file_type = None
        extensions = ["pdf", "docx", "doc", "xlsx", "xls", "pptx", "ppt", "csv", "zip", "txt", "png", "jpeg", "jpg"]
        for ext in extensions:
            if f"{ext}s" in q_lower or f" {ext}" in q_lower:
                file_type = ext
                break
                
        # 2. Detect sender filters (e.g. "from google", "by amazon")
        sender = None
        sender_match = re.search(r'\b(?:from|by|sent by)\s+([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z0-9.-]+|\w+)', user_query, re.IGNORECASE)
        if sender_match:
            sender = sender_match.group(1).split("@")[0].strip().lower()

        # 3. Clean search terms (strip action prefixes like "find", "search", "show")
        search_terms = re.sub(
            r'\b(?:find|search|show|where is|get|look for|documents?|files?)\b',
            '',
            user_query,
            flags=re.IGNORECASE
        ).strip()
        
        # Strip sender references from search terms
        if sender_match:
            search_terms = search_terms.replace(sender_match.group(0), "")
        if file_type:
            # strip "pdfs" or "pdf"
            search_terms = re.sub(rf'\b{file_type}s?\b', '', search_terms, flags=re.IGNORECASE)
            
        search_terms = re.sub(r'\s+', ' ', search_terms).strip()

        return {
            "search_terms": search_terms or user_query,
            "filters": {
                "sender": sender,
                "file_type": file_type,
                "date_filter": "yesterday" if "yesterday" in q_lower else None
            }
        }

    def search(self, user_query: str) -> List[Dict[str, Any]]:
        """
        Executes a search query.
        Updates index automatically, parses query filters, ranks documents, and returns results.
        """
        # Always update index before search to capture any new downloads
        self.update_index()

        # Parse query filters
        intent = self.parse_query_intent(user_query)
        search_terms = intent.get("search_terms", "").lower()
        filters = intent.get("filters", {})
        
        logger.info(f"Executing search: terms='{search_terms}' filters={filters}")
        
        candidates: List[Tuple[str, Dict[str, Any], float]] = []

        # Filter and rank documents
        for rel_path, doc in self.index.items():
            # Apply File Type Filter
            if filters.get("file_type") and doc["doc_type"] != filters["file_type"]:
                continue

            # Apply Sender Filter
            if filters.get("sender"):
                target_sender = filters["sender"].lower()
                if target_sender not in doc["sender"].lower():
                    continue

            score = 0.0
            filename_lower = doc["filename"].lower()
            text_lower = doc["extracted_text"].lower()
            sender_lower = doc["sender"].lower()

            # Rank 1: Filename matches (Weight 40%)
            if search_terms:
                if search_terms == filename_lower or search_terms == Path(filename_lower).stem:
                    score += 40.0
                elif search_terms in filename_lower:
                    score += 20.0

            # Rank 2: Sender matches (Weight 35%)
            if search_terms:
                if search_terms == sender_lower:
                    score += 35.0
                elif search_terms in sender_lower:
                    score += 25.0

            # Rank 3: Text content matches (Weight 40%)
            if search_terms:
                # Count frequency of search terms in text
                term_count = text_lower.count(search_terms)
                if term_count > 0:
                    # Give points based on occurrence count, capped at 30
                    score += min(term_count * 5.0, 30.0)
                    
                    # Boost if terms appear close to each other or as a exact phrase
                    if search_terms in text_lower:
                        score += 10.0

            # Rank 4: Keyword tag exact match boost
            if any(term in doc["keywords"] for term in search_terms.split()):
                score += 10.0

            # Base score boost if query filters by sender and there are no search terms
            if filters.get("sender") and not search_terms:
                score += 50.0

            if score > 0:
                candidates.append((rel_path, doc, score))

        # Sort candidates by match score descending
        candidates.sort(key=lambda x: x[2], reverse=True)

        # Truncate to top 5 candidates for semantic snippet evaluation to save API tokens
        top_candidates = candidates[:5]
        results: List[Dict[str, Any]] = []

        for rel_path, doc, score in top_candidates:
            # Generate AI snippet explaining the match
            snippet = self._generate_ai_snippet(user_query, doc)
            
            # Boost score semantically if AI snippet confirms high relevance
            final_score = score
            if "relevance: high" in snippet.lower():
                final_score = min(score + 10.0, 100.0)
            elif "relevance: low" in snippet.lower():
                final_score = max(score - 10.0, 5.0)

            results.append({
                "filename": doc["filename"],
                "sender": doc["sender"],
                "downloaded_time": doc["downloaded_time"],
                "timestamp_folder": doc["timestamp_folder"],
                "doc_type": doc["doc_type"],
                "relative_path": rel_path,
                "full_path": str(Config.DOWNLOAD_DIR / rel_path),
                "score": round(final_score, 1),
                "snippet": snippet.split("\n")[-1].replace("Snippet: ", "").replace("Explanation: ", "").strip()
            })

        # Sort final results by score again
        results.sort(key=lambda x: x["score"], reverse=True)
        return results

    def _generate_ai_snippet(self, user_query: str, doc: Dict[str, Any]) -> str:
        """Generates a short explanation snippet using Groq or falls back to text search snippets."""
        text_preview = doc["extracted_text"][:2500]
        
        if self.groq_client:
            try:
                system_prompt = (
                    "You are a search result snippet summarizer. "
                    "Analyze the provided document text preview and user query. "
                    "Determine if the file matches the query. "
                    "Respond with exactly two lines:\n"
                    "Line 1: 'Relevance: [High/Medium/Low]'\n"
                    "Line 2: 'Snippet: [1-2 sentences explaining why the document matched or what it is about]'"
                )
                user_prompt = (
                    f"User Query: {user_query}\n"
                    f"Filename: {doc['filename']}\n"
                    f"Text Context:\n{text_preview}\n"
                )
                
                response = self.groq_client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.0,
                    max_tokens=150
                )
                return response.choices[0].message.content.strip()
            except Exception as e:
                logger.error(f"Groq snippet generation failed: {e}")

        # Fallback snippet generator (regex-based context locator)
        q_words = user_query.lower().split()
        match_pos = -1
        for word in q_words:
            if len(word) > 3:
                pos = text_preview.lower().find(word)
                if pos != -1:
                    match_pos = pos
                    break
                    
        if match_pos != -1:
            start = max(0, match_pos - 60)
            end = min(len(text_preview), match_pos + 120)
            snippet_text = text_preview[start:end].replace("\n", " ").strip()
            return f"Relevance: Medium\nSnippet: ...{snippet_text}..."
            
        return f"Relevance: Medium\nSnippet: File '{doc['filename']}' matched criteria by filename metadata."
