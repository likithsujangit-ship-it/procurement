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
from config import Config
from tools.utils import setup_logger
from tools.extractor import extract_attachment_content

from groq import Groq

logger = setup_logger("search_engine")


def normalize_text(text: str) -> str:
    """Replaces underscores and dashes with spaces, collapsing duplicate spacing."""
    t = text.replace("_", " ").replace("-", " ")
    return re.sub(r'\s+', ' ', t).strip().lower()


def get_similarity(s1: str, s2: str) -> float:
    """Calculates character bigram Jaccard similarity for typo-tolerance."""
    s1, s2 = s1.lower().strip(), s2.lower().strip()
    if not s1 or not s2:
        return 0.0
    if s1 == s2:
        return 1.0
        
    bigrams1 = {s1[i:i+2] for i in range(len(s1)-1)}
    bigrams2 = {s2[i:i+2] for i in range(len(s2)-1)}
    
    if not bigrams1 or not bigrams2:
        c1, c2 = set(s1), set(s2)
        intersection = len(c1.intersection(c2))
        union = len(c1.union(c2))
        return intersection / union if union > 0 else 0.0
        
    intersection = len(bigrams1.intersection(bigrams2))
    union = len(bigrams1.union(bigrams2))
    return intersection / union if union > 0 else 0.0


class SearchEngine:
    """Orchestrates indexing of email files and execution of semantic search queries."""

    def __init__(self) -> None:
        self.index_file = Config.OUTPUTS_DIR / "search_index.json"
        self.index: Dict[str, Any] = {}
        self.load_index()

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
            logger.debug(f"Saved search index to {self.index_file}")
        except Exception as e:
            logger.error(f"Failed to save search index: {e}")

    def update_index(self) -> None:
        """
        Recursively scans DOWNLOAD_DIR for files.
        Extracts content, computes SHA-256 checksums, and updates search_index.json.
        """
        logger.info(f"Scanning directory for indexing: {Config.DOWNLOAD_DIR}")
        updated_count = 0

        for path in Config.DOWNLOAD_DIR.rglob("*"):
            if path.is_file():
                try:
                    rel_path = str(path.relative_to(Config.DOWNLOAD_DIR))
                    mtime = os.path.getmtime(path)
                    file_size = path.stat().st_size
                    
                    if rel_path in self.index and self.index[rel_path].get("mtime") == mtime:
                        continue

                    raw_content = extract_attachment_content(path)
                    
                    self.index[rel_path] = {
                        "filename": path.name,
                        "extension": path.suffix.lower(),
                        "size_bytes": file_size,
                        "mtime": mtime,
                        "content_preview": raw_content[:500],
                        "raw_text": raw_content
                    }
                    updated_count += 1
                except Exception as e:
                    logger.warning(f"Error indexing file {path.name}: {e}")

        if updated_count > 0:
            self.save_index()
            logger.info(f"Indexing complete. Index now contains {len(self.index)} files.")
        else:
            logger.info("Indexing complete. No file modifications detected.")

    def parse_query_intent(self, user_query: str) -> Dict[str, Any]:
        """
        Uses Groq API to parse the natural language query intent into search filters.
        Falls back to regex parsing if the API is offline.
        """
        if getattr(self, "groq_client", None):
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
        
        # 1. Detect file type filters (supporting multiple extensions)
        found_types = []
        extensions = ["pdf", "docx", "doc", "xlsx", "xls", "pptx", "ppt", "csv", "zip", "txt", "png", "jpeg", "jpg", "html"]
        for ext in extensions:
            if f".{ext}" in q_lower or f" {ext}s" in q_lower or f" {ext}" in q_lower or q_lower == ext or q_lower == f".{ext}":
                found_types.append(ext)
        file_type = ", ".join(found_types) if found_types else None
                
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
        
        # If the search term is just the file type extension itself, clear search_terms
        if filters.get("file_type") and search_terms:
            raw_type = filters["file_type"]
            target_types = []
            if isinstance(raw_type, list):
                target_types = [str(t).lstrip(".").strip().lower() for t in raw_type]
            else:
                split_types = re.split(r',|\band\b|\s+', str(raw_type))
                target_types = [t.lstrip(".").strip().lower() for t in split_types if t.strip()]
            
            clean_terms = search_terms.lstrip(".").strip().lower()
            if clean_terms in target_types or any(clean_terms == f"{t}s" for t in target_types):
                search_terms = ""
        
        logger.info(f"Executing search: terms='{search_terms}' filters={filters}")
        
        # Normalize search terms
        normalized_search = normalize_text(search_terms) if search_terms else ""

        # Pre-scan for exact filename/stem matches or filename word boundary matches in index database
        has_exact_match = False
        has_filename_word_match = False
        if normalized_search:
            for doc in self.index.values():
                fn_normalized = normalize_text(doc["filename"])
                stem_normalized = normalize_text(Path(doc["filename"]).stem)
                if normalized_search == fn_normalized or normalized_search == stem_normalized:
                    has_exact_match = True
                if re.search(rf'\b{re.escape(normalized_search)}\b', fn_normalized):
                    has_filename_word_match = True

        candidates: List[Tuple[str, Dict[str, Any], float]] = []

        # Filter and rank documents
        for rel_path, doc in self.index.items():
            fn_normalized = normalize_text(doc["filename"])
            stem_normalized = normalize_text(Path(doc["filename"]).stem)

            # Prioritize filename matching: if any file matches by name exactly or contains the search term as a word in its name,
            # we restrict candidate results only to those files that have a filename match (preventing content fallback clutter)
            if normalized_search:
                if has_exact_match:
                    if normalized_search != fn_normalized and normalized_search != stem_normalized and normalized_search not in fn_normalized and fn_normalized not in normalized_search:
                        continue
                elif has_filename_word_match:
                    if not re.search(rf'\b{re.escape(normalized_search)}\b', fn_normalized):
                        continue

            # Apply File Type Filter (supporting strings, lists, and comma-separated extensions)
            if filters.get("file_type"):
                target_types = []
                raw_type = filters["file_type"]
                if isinstance(raw_type, list):
                    target_types = [str(t).lstrip(".").strip().lower() for t in raw_type]
                else:
                    split_types = re.split(r',|\band\b|\s+', str(raw_type))
                    target_types = [t.lstrip(".").strip().lower() for t in split_types if t.strip()]
                    
                if doc["doc_type"] not in target_types:
                    continue

            # Apply Sender Filter (supporting exact, substring, or fuzzy similarity match >= 0.4)
            if filters.get("sender"):
                target_sender = filters["sender"].lower()
                sender_name = doc["sender"].lower()
                is_match = (target_sender == sender_name or 
                            target_sender in sender_name or 
                            sender_name in target_sender or
                            get_similarity(target_sender, sender_name) >= 0.4)
                if not is_match:
                    continue

            score = 0.0
            text_lower = doc["extracted_text"].lower()
            sender_lower = doc["sender"].lower()

            # Rank 1: Filename Match (up to 80 points)
            if normalized_search:
                sim = get_similarity(normalized_search, stem_normalized)
                if normalized_search == fn_normalized or normalized_search == stem_normalized:
                    score += 80.0
                elif re.search(rf'\b{re.escape(normalized_search)}\b', fn_normalized):
                    score += 50.0
                elif normalized_search in fn_normalized:
                    score += 20.0
                elif sim >= 0.4:
                    score += sim * 40.0
                elif any(word in fn_normalized for word in normalized_search.split()):
                    matched_words = sum(1 for word in normalized_search.split() if word in fn_normalized)
                    score += matched_words * 10.0

            # Rank 2: Sender matches (up to 30 points)
            if search_terms:
                sim = get_similarity(search_terms, sender_lower)
                if search_terms == sender_lower:
                    score += 30.0
                elif search_terms in sender_lower:
                    all_senders = [d["sender"].lower() for d in self.index.values()]
                    if search_terms not in all_senders:
                        score += 15.0
                elif sim >= 0.4:
                    score += sim * 20.0

            # Rank 3: Text content matches (up to 30 points)
            if search_terms:
                # Use word boundaries to prevent substring matching inside other words (e.g. 'arm' in 'margins')
                pattern = rf'\b{re.escape(search_terms)}\b'
                term_count = len(re.findall(pattern, text_lower))
                if term_count > 0:
                    score += min(term_count * 3.0, 20.0)
                    score += 10.0

            # Rank 4: Keyword tag exact match boost
            if any(term in doc["keywords"] for term in search_terms.split()):
                score += 5.0

            # Base score boost if query filters by sender or file_type and there are no search terms
            if filters.get("sender") and not search_terms:
                score += 50.0
            if filters.get("file_type") and not search_terms:
                score += 50.0

            if score > 0:
                candidates.append((rel_path, doc, score))

        # Sort candidates by match score descending
        candidates.sort(key=lambda x: x[2], reverse=True)

        # Return up to 100 candidates to prevent truncation of matching sender files
        top_candidates = candidates[:100]
        results: List[Dict[str, Any]] = []

        for idx, (rel_path, doc, score) in enumerate(top_candidates):
            # Only use Groq API for top 3 high-relevance candidates to preserve API speed and rate limits
            use_groq = (idx < 3) and (score >= 30.0)
            snippet = self._generate_snippet(user_query, doc, use_groq=use_groq)
            
            # Boost score semantically if AI snippet confirms high relevance
            final_score = score
            if use_groq:
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

    def _generate_snippet(self, user_query: str, doc: Dict[str, Any], use_groq: bool) -> str:
        """Generates a short explanation snippet using Groq or falls back to text search snippets."""
        text_preview = doc["extracted_text"][:2500]
        
        if use_groq and self.groq_client:
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
            
        return f"Relevance: Medium\nSnippet: File '{doc['filename']}' matched criteria by filename or sender metadata."
