# Clausea Crawler Documentation

## Overview

The Clausea Crawler is a sophisticated, AI-powered web crawler specifically designed to discover and extract legal documents (privacy policies, terms of service, data processing agreements, etc.) from websites. It combines intelligent URL scoring, content analysis, and legal document detection to efficiently find relevant legal content across the web.

### Key Features

- **Intelligent URL Scoring**: Prioritizes URLs likely to contain legal documents based on path patterns, anchor text, and keywords
- **Multiple Crawling Strategies**: Supports BFS (breadth-first), DFS (depth-first), and best-first search strategies
- **Legal Document Detection**: Uses both rule-based and AI-powered analysis to identify legal content
- **Robots.txt Compliance**: Respects robots.txt rules with configurable exceptions
- **Per-Domain Rate Limiting**: Prevents overwhelming target servers while allowing concurrent requests to different domains
- **Browser Support**: Optional headless browser rendering for JavaScript-heavy sites
- **Comprehensive Error Handling**: Automatic retries with exponential backoff for transient errors
- **Memory Efficient**: Processes products sequentially with memory monitoring

## Architecture

The crawler consists of two main components:

1. **ClauseaCrawler** (`src/crawler.py`): Core crawling engine that discovers and fetches web pages
2. **LegalDocumentPipeline** (`src/pipeline.py`): High-level pipeline that orchestrates crawling, AI analysis, and document storage

```
┌─────────────────────────────────────────────────────────────┐
│                  LegalDocumentPipeline                       │
│  (Orchestrates: Crawling → Analysis → Storage)              │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                      ClauseaCrawler                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │ URL Scorer   │  │ Content      │  │ Robots.txt    │     │
│  │              │  │ Analyzer     │  │ Checker       │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │ Rate         │  │ Browser      │  │ URL Queue     │     │
│  │ Limiter      │  │ Support      │  │ Management    │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
└─────────────────────────────────────────────────────────────┘
```

## Core Components

### 1. ClauseaCrawler

The main crawler class that handles web page discovery and fetching.

#### Initialization

```python
crawler = ClauseaCrawler(
    max_depth=4,                    # Maximum crawl depth
    max_pages=1000,                 # Maximum pages to crawl
    max_concurrent=10,               # Concurrent requests limit
    delay_between_requests=1.0,     # Delay between requests (seconds)
    timeout=30,                     # Request timeout (seconds)
    allowed_domains=["example.com"], # Restrict to specific domains
    respect_robots_txt=True,         # Respect robots.txt
    strategy="bfs",                  # "bfs", "dfs", or "best_first"
    use_browser=False,               # Use headless browser for JS sites
    proxy=None,                      # Optional proxy URL
    allowed_paths=[r"/legal/.*"],    # Optional path allowlist (regex)
    denied_paths=[r"/blog/.*"],     # Optional path denylist (regex)
)
```

#### Key Methods

- `crawl(base_url)`: Main crawling method that starts from a base URL
- `fetch_page(session, url)`: Fetches and processes a single page with retry logic
- `should_crawl_url(url, base_url, depth)`: Determines if a URL should be crawled
- `normalize_url(url)`: Normalizes URLs by removing fragments and trailing slashes

### 2. URLScorer

Scores URLs based on their likelihood of containing legal documents.

#### Scoring Factors

1. **High-Value Patterns** (weighted 6.0-8.0):

   - `privacy-policy`, `terms-of-service`, `cookie-policy`
   - `data-processing-addendum`, `subprocessors`
   - `gdpr`, `ccpa`

2. **Path Patterns** (weighted 3.0-5.0):

   - `/legal/`, `/privacy/`, `/terms/`, `/policy/`
   - `/company/legal/`, `/policies/privacy/`
   - Common legal document paths

3. **Anchor Text** (1.5x multiplier):

   - If anchor text contains legal keywords, score is boosted
   - Example: Link with text "Privacy Policy" gets higher score

4. **URL Keywords**:
   - Legal keywords in URL path/query: `privacy`, `terms`, `legal`, `gdpr`, etc.
   - Negative keywords reduce score: `blog`, `news`, `product`

#### Example Scoring

```python
scorer = URLScorer()

# High score: explicit privacy policy URL
score1 = scorer.score_url("https://example.com/privacy-policy")
# Score: ~8.0

# Medium score: legal section
score2 = scorer.score_url("https://example.com/legal/terms")
# Score: ~4.5

# Low score: blog post
score3 = scorer.score_url("https://example.com/blog/article")
# Score: ~0.0
```

### 3. ContentAnalyzer

Analyzes page content to determine if it's a legal document.

#### Analysis Process

1. **Quick Check**: Fast regex pattern matching for legal keywords
2. **Content Metrics**: Word count, character count, legal content density
3. **Legal Indicators**: Checks for 50+ legal phrases and keywords
4. **Title Analysis**: Bonus scoring for legal terms in page title
5. **Metadata Analysis**: Checks meta tags for legal document indicators

#### Legal Indicators

The analyzer looks for phrases like:

- "by using this service, you agree to these terms"
- "we collect your personal data"
- "this policy describes how we"
- "data processing addendum"
- "subprocessor list"
- "data subject rights"
- "lawful basis for processing"
- And 40+ more legal document patterns

#### Classification Result

```python
is_legal, score, indicators = analyzer.analyze_content(
    content="...",
    title="Privacy Policy",
    metadata={...}
)

# Returns:
# - is_legal: bool (True if document is legal)
# - score: float (0-10 confidence score)
# - indicators: list[str] (matched patterns and metrics)
```

### 4. RobotsTxtChecker

Checks robots.txt compliance before crawling URLs.

#### Features

- **Caching**: LRU cache for robots.txt files (max 1000 domains)
- **User-Agent Matching**: Supports wildcard patterns (`*`, `bot`, `crawler`)
- **Path Pattern Matching**: Handles wildcards and trailing patterns
- **Allow/Disallow Priority**: More specific rules override general ones

#### Example

```python
checker = RobotsTxtChecker()
can_fetch, reason = await checker.can_fetch(session, url)

if not can_fetch:
    logger.warning(f"Blocked by robots.txt: {reason}")
```

### 5. DomainRateLimiter

Per-domain rate limiting that allows concurrent requests to different domains.

#### How It Works

- Each domain has its own lock and last-request timestamp
- Requests to the same domain are serialized with configurable delay
- Different domains can be crawled concurrently
- Prevents overwhelming individual servers

```python
limiter = DomainRateLimiter(delay_between_requests=1.0)
await limiter.rate_limit("https://example.com/page1")  # Waits if needed
await limiter.rate_limit("https://other.com/page1")     # No wait (different domain)
```

## Crawling Strategies

### Breadth-First Search (BFS)

**Default strategy**. Crawls pages level by level, exploring all pages at depth N before moving to depth N+1.

**Use Cases:**

- Finding legal documents near the homepage
- Comprehensive site coverage
- When legal docs are typically 1-2 clicks from homepage

**Implementation:**

- Uses `deque` (double-ended queue) for FIFO ordering
- Processes all URLs at current depth before next depth

### Depth-First Search (DFS)

Crawls deeply into one path before backtracking.

**Use Cases:**

- Deep legal document sections
- When you want to fully explore one area before moving on
- Testing specific document hierarchies

**Implementation:**

- Uses `list` as stack for LIFO ordering
- Follows one path to max depth before exploring others

### Best-First Search

Prioritizes URLs with highest legal relevance scores.

**Use Cases:**

- Finding legal documents quickly
- When you want the most relevant pages first
- Limited crawl budget (fewer pages)

**Implementation:**

- Uses `heapq` (priority queue) with negative scores (min-heap)
- Always processes highest-scoring URLs first
- Most efficient for legal document discovery

#### Strategy Comparison

| Strategy   | Speed           | Coverage | Best For         |
| ---------- | --------------- | -------- | ---------------- |
| BFS        | Medium          | High     | General crawling |
| DFS        | Fast (early)    | Medium   | Deep sections    |
| Best-First | Fast (targeted) | Targeted | Legal docs only  |

## URL Filtering and Validation

### Domain Restrictions

```python
# Only crawl specific domains
crawler = ClauseaCrawler(allowed_domains=["example.com", "subdomain.example.com"])

# Follow external links (default: False)
crawler = ClauseaCrawler(follow_external_links=True)
```

### Path Filtering

```python
# Only crawl paths matching patterns
crawler = ClauseaCrawler(
    allowed_paths=[r"/legal/.*", r"/privacy.*"],
    denied_paths=[r"/blog/.*", r"/admin/.*"]
)
```

### Automatic Skipping

The crawler automatically skips:

- Binary files (`.pdf`, `.jpg`, `.png`, `.gif`, `.css`, `.js`)
- Anchor links (`#section`)
- Protocol links (`mailto:`, `tel:`, `javascript:`)
- API endpoints (`/api/`, `/ajax/`)
- Search pages (`/search?`)

### URL Normalization

URLs are normalized to prevent duplicates:

- Removes fragments (`#section`)
- Removes trailing slashes (except root)
- Converts to lowercase for comparison
- Preserves query parameters

## Content Extraction

### HTML Processing

1. **Parse with BeautifulSoup**: Extracts structured content
2. **Remove Scripts/Styles**: Strips `<script>` and `<style>` tags
3. **Text Extraction**: Gets clean text content
4. **Markdown Conversion**: Converts HTML to Markdown using `markdownify`
5. **Metadata Extraction**: Extracts title, meta tags, headers, canonical URLs
6. **Link Discovery**: Finds all `<a href>` links with anchor text

### Plain Text Support

The crawler also handles `text/plain` content:

- Uses content as-is for text
- Extracts title from first few lines or URL
- No link extraction (plain text has no links)

### Browser Rendering

For JavaScript-heavy sites, the crawler can use Playwright:

```python
crawler = ClauseaCrawler(use_browser=True)
```

**When Browser is Used:**

- `use_browser=True` is set
- Content is very short (< 500 chars) - likely needs JS
- Content contains "javascript is required" messages

**Browser Features:**

- Blocks heavy resources (images, fonts, CSS) for speed
- Waits for `networkidle` to ensure content is loaded
- Extracts content after JavaScript execution

## Error Handling and Retries

### Retryable Errors

The crawler automatically retries on:

- Network errors (connection failures, DNS issues)
- Timeout errors
- Server errors (5xx HTTP status)
- Rate limiting (429 HTTP status)

### Non-Retryable Errors

These errors are not retried:

- Client errors (4xx except 429)
- Content type errors
- Robots.txt blocks

### Retry Configuration

```python
crawler = ClauseaCrawler(
    max_retries=3,  # Default: 3 attempts
    timeout=30      # Request timeout
)
```

**Retry Behavior:**

- Exponential backoff: 2s, 4s, 8s, max 10s
- Uses `tenacity` library for retry logic
- Logs all retry attempts

## Legal Document Pipeline

The `LegalDocumentPipeline` integrates the crawler with AI analysis and database storage.

### Pipeline Flow

```
1. Get Products from Database
   ↓
2. For each Product:
   ├─ Create ClauseaCrawler (configured for product)
   ├─ Crawl base URLs
   ├─ For each CrawlResult:
   │   ├─ Detect Locale (LLM)
   │   ├─ Classify Document (LLM)
   │   ├─ Detect Regions (LLM)
   │   ├─ Extract Effective Date (LLM)
   │   └─ Extract Title
   └─ Store Documents (with deduplication)
```

### Document Analyzer

The `DocumentAnalyzer` class provides AI-powered analysis:

#### Locale Detection

1. Checks metadata (`og:locale`, `lang` attribute)
2. Falls back to LLM analysis of text content
3. Returns locale code (e.g., `en-US`, `fr-FR`)

#### Document Classification

Classifies documents into categories:

- `privacy_policy`
- `terms_of_service`
- `cookie_policy`
- `data_processing_agreement`
- `gdpr_policy`
- And more...

#### Region Detection

Determines geographic scope:

- Global documents
- Region-specific (US, EU, UK, etc.)
- Based on governing law clauses, compliance frameworks

#### Effective Date Extraction

Extracts document effective dates:

1. Static extraction from metadata and common patterns
2. LLM analysis if static extraction fails
3. Returns ISO format (`YYYY-MM-DD`)

### Document Storage

Documents are stored with intelligent deduplication:

```python
# Check for existing document by URL
existing = await document_service.get_document_by_url(db, url)

if existing:
    # Compare content hashes
    if content_changed:
        # Update existing document
        await document_service.update_document(db, document)
    else:
        # Skip duplicate
        pass
else:
    # Create new document
    await document_service.store_document(db, document)
```

## Configuration Examples

### Basic Crawling

```python
from src.crawler import ClauseaCrawler

crawler = ClauseaCrawler(
    max_depth=3,
    max_pages=100,
    strategy="bfs"
)

results = await crawler.crawl("https://example.com")
```

### Legal Document Discovery

```python
crawler = ClauseaCrawler(
    max_depth=4,
    max_pages=500,
    strategy="best_first",  # Prioritize legal URLs
    min_legal_score=2.0,     # Minimum relevance score
    respect_robots_txt=True
)

results = await crawler.crawl("https://example.com")
legal_docs = [r for r in results if r.legal_score >= 3.0]
```

### Product-Specific Crawling

```python
from src.pipeline import LegalDocumentPipeline

pipeline = LegalDocumentPipeline(
    max_depth=4,
    max_pages=1000,
    crawler_strategy="bfs",
    concurrent_limit=10,
    delay_between_requests=1.0,
    respect_robots_txt=True,
    use_browser=True,  # For JS-heavy sites
    max_parallel_products=3  # Process 3 products concurrently
)

stats = await pipeline.run()
```

### Custom Domain Restrictions

```python
crawler = ClauseaCrawler(
    allowed_domains=["example.com", "legal.example.com"],
    follow_external_links=False,  # Stay within allowed domains
    allowed_paths=[r"/legal/.*", r"/privacy.*"],
    denied_paths=[r"/blog/.*"]
)
```

### Browser Rendering

```python
crawler = ClauseaCrawler(
    use_browser=True,  # Enable Playwright
    timeout=60,        # Longer timeout for JS execution
    proxy="http://user:pass@proxy.example.com:8080"  # Optional proxy
)
```

## Performance Considerations

### Memory Management

- **Sequential Product Processing**: Processes products one at a time to manage memory
- **Memory Monitoring**: Tracks peak memory usage during crawls
- **Cache Limits**: LRU caches with size limits (robots.txt: 1000, URL scorer: 10000)
- **Resource Cleanup**: Closes browser instances and file handlers after use

### Network Optimization

- **Connection Pooling**: Reuses HTTP connections with `aiohttp.TCPConnector`
- **Concurrent Requests**: Configurable concurrency (default: 10)
- **Per-Domain Rate Limiting**: Prevents overwhelming individual servers
- **Request Batching**: Processes URLs in batches for efficiency

### Database Efficiency

- **Bulk Operations**: Stores documents in batches
- **Smart Updates**: Only updates documents when content changes (hash comparison)
- **Deduplication**: Prevents storing duplicate documents

### Performance Metrics

The pipeline tracks comprehensive statistics:

```python
stats = await pipeline.run()

# Access metrics:
stats.companies_processed
stats.total_urls_crawled
stats.legal_documents_found
stats.processing_time_seconds
stats.total_tokens  # LLM usage
stats.total_cost    # LLM cost
```

## Logging

### File Logging

Each crawl session can write to a dedicated log file:

```python
crawler = ClauseaCrawler(
    log_file_path="logs/20240101_123456_company_crawl.log"
)
```

### Log Levels

- **INFO**: High-level progress, crawl statistics
- **DEBUG**: URL scoring, queue operations, detailed decisions
- **WARNING**: Failed URLs, robots.txt blocks, retries
- **ERROR**: Critical failures, exceptions

### Structured Logging

Uses `structlog` for structured, JSON-compatible logs:

- Request IDs for tracing
- Product context
- Document metadata
- Performance metrics

## Best Practices

### 1. Respect Rate Limits

```python
# Conservative settings for production
crawler = ClauseaCrawler(
    delay_between_requests=2.0,  # 2 seconds between requests
    max_concurrent=5,             # Lower concurrency
    respect_robots_txt=True
)
```

### 2. Use Appropriate Strategy

- **Best-First**: When you need legal docs quickly
- **BFS**: For comprehensive coverage
- **DFS**: For deep exploration of specific sections

### 3. Configure Domain Restrictions

Always restrict to allowed domains to avoid crawling unintended sites:

```python
crawler = ClauseaCrawler(
    allowed_domains=["example.com"],
    follow_external_links=False
)
```

### 4. Monitor Resource Usage

```python
# Enable memory monitoring
pipeline = LegalDocumentPipeline(...)
stats = await pipeline.run()

# Check memory usage
logger.info(f"Peak memory: {stats.peak_memory_mb}MB")
```

### 5. Handle Errors Gracefully

The crawler handles errors automatically, but you should:

- Monitor failed URLs
- Check robots.txt compliance
- Review rate limiting if getting 429 errors

## Troubleshooting

### Common Issues

#### 1. No Legal Documents Found

**Possible Causes:**

- URLs not scoring high enough (check `min_legal_score`)
- Content analyzer too strict (check `legal_score` in results)
- Legal docs at deeper levels (increase `max_depth`)

**Solutions:**

```python
# Lower minimum score
crawler = ClauseaCrawler(min_legal_score=0.0)

# Increase depth
crawler = ClauseaCrawler(max_depth=5)

# Use best-first strategy
crawler = ClauseaCrawler(strategy="best_first")
```

#### 2. Too Many Failed URLs

**Possible Causes:**

- Rate limiting (429 errors)
- Network timeouts
- Invalid URLs

**Solutions:**

```python
# Increase delays
crawler = ClauseaCrawler(delay_between_requests=2.0)

# Increase timeout
crawler = ClauseaCrawler(timeout=60)

# Check robots.txt
crawler = ClauseaCrawler(respect_robots_txt=True)
```

#### 3. Memory Issues

**Possible Causes:**

- Too many concurrent requests
- Large documents
- Processing too many products in parallel

**Solutions:**

```python
# Reduce concurrency
crawler = ClauseaCrawler(max_concurrent=5)

# Process fewer products in parallel
pipeline = LegalDocumentPipeline(max_parallel_products=1)
```

#### 4. JavaScript-Heavy Sites

**Possible Causes:**

- Content loaded via JavaScript
- Single-page applications

**Solutions:**

```python
# Enable browser rendering
crawler = ClauseaCrawler(use_browser=True)
```

## API Reference

### ClauseaCrawler

#### Methods

- `async crawl(base_url: str) -> list[CrawlResult]`: Main crawling method
- `async fetch_page(session, url: str) -> CrawlResult`: Fetch single page
- `should_crawl_url(url: str, base_url: str, depth: int) -> bool`: Check if URL should be crawled
- `normalize_url(url: str) -> str`: Normalize URL
- `generate_potential_legal_urls(base_url: str) -> list[str]`: Generate common legal URLs

#### Properties

- `visited_urls: set[str]`: Set of crawled URLs
- `failed_urls: set[str]`: Set of failed URLs
- `results: list[CrawlResult]`: List of crawl results
- `stats: CrawlStats`: Crawl statistics

### CrawlResult

```python
class CrawlResult(BaseModel):
    url: str                    # Final URL after redirects
    title: str                  # Page title
    content: str                # Raw text content
    markdown: str               # Markdown format
    metadata: dict[str, Any]    # Extracted metadata
    status_code: int            # HTTP status code
    success: bool               # Whether crawl succeeded
    error_message: str | None  # Error message if failed
    legal_score: float          # Legal relevance score (0-10)
    discovered_links: list[dict[str, str]]  # Links with anchor text
```

### LegalDocumentPipeline

#### Methods

- `async run(products: list[Product] | None = None) -> ProcessingStats`: Run complete pipeline
- `async _process_product(product: Product) -> list[Document]`: Process single product
- `async _process_crawl_result(result: CrawlResult, product: Product) -> Document | None`: Process crawl result

## Examples

### Example 1: Simple Crawl

```python
import asyncio
from src.crawler import ClauseaCrawler

async def main():
    crawler = ClauseaCrawler(
        max_depth=3,
        max_pages=50,
        strategy="bfs"
    )

    results = await crawler.crawl("https://example.com")

    print(f"Crawled {len(results)} pages")
    for result in results:
        if result.success:
            print(f"✅ {result.title}: {result.url} (Score: {result.legal_score:.1f})")

asyncio.run(main())
```

### Example 2: Legal Document Discovery

```python
import asyncio
from src.crawler import ClauseaCrawler

async def main():
    crawler = ClauseaCrawler(
        max_depth=4,
        max_pages=200,
        strategy="best_first",  # Prioritize legal URLs
        min_legal_score=2.0
    )

    results = await crawler.crawl("https://example.com")

    # Filter legal documents
    legal_docs = [r for r in results if r.legal_score >= 3.0]

    print(f"Found {len(legal_docs)} legal documents:")
    for doc in sorted(legal_docs, key=lambda x: x.legal_score, reverse=True):
        print(f"  📄 {doc.title}")
        print(f"     URL: {doc.url}")
        print(f"     Score: {doc.legal_score:.1f}")

asyncio.run(main())
```

### Example 3: Full Pipeline

```python
import asyncio
from src.pipeline import LegalDocumentPipeline

async def main():
    pipeline = LegalDocumentPipeline(
        max_depth=4,
        max_pages=1000,
        crawler_strategy="bfs",
        concurrent_limit=10,
        delay_between_requests=1.0,
        respect_robots_txt=True,
        use_browser=True
    )

    stats = await pipeline.run()

    print(f"✅ Processed {stats.products_processed} products")
    print(f"📄 Found {stats.legal_documents_stored} legal documents")
    print(f"⏱️  Time: {stats.processing_time_seconds:.1f}s")
    print(f"💰 Cost: ${stats.total_cost:.4f}")

asyncio.run(main())
```

## Conclusion

The Clausea Crawler is a powerful, production-ready system for discovering and extracting legal documents from websites. It combines intelligent URL scoring, content analysis, and AI-powered classification to efficiently find relevant legal content while respecting web standards and rate limits.

For questions or issues, refer to the code documentation or contact the development team.
