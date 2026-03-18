"""
Semantic Markdown Chunker for Vault KB.

Splits markdown documents by headers (H1, H2, H3) and applies secondary
character-level splitting for oversized chunks. Filters noise sections.
"""

import hashlib
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)


@dataclass
class Chunk:
    """A single chunk of text with metadata."""
    text: str
    metadata: dict = field(default_factory=dict)
    chunk_id: str = ""

    def __post_init__(self):
        if not self.chunk_id:
            self.chunk_id = hashlib.md5(
                (self.text + str(sorted(self.metadata.items()))).encode()
            ).hexdigest()


# Sections to filter out (noise from scraped web pages)
NOISE_PATTERNS = [
    r"^#+\s*Other Blogs",
    r"^#+\s*Request a Service",
    r"^#+\s*Common Keywords Found in Reviews",
    r"^#+\s*Secure your property",
    r"^#+\s*Google Rating",
]

# Repeated testimonial patterns
TESTIMONIAL_NAMES = [
    "Arvind Nair", "Dharmendra", "Sunil M.S", "Rasik Hegde"
]


def _is_noise_section(text: str) -> bool:
    """Check if text is a noise section that should be filtered."""
    for pattern in NOISE_PATTERNS:
        if re.search(pattern, text, re.MULTILINE):
            return True
    return False


def _is_duplicate_testimonial(text: str) -> bool:
    """Check if chunk is just repeated testimonials."""
    testimonial_count = sum(1 for name in TESTIMONIAL_NAMES if name in text)
    # If text is mostly testimonials (multiple names, short text)
    non_testimonial = text
    for name in TESTIMONIAL_NAMES:
        non_testimonial = non_testimonial.replace(name, "")
    if testimonial_count >= 2 and len(non_testimonial.strip()) < 200:
        return True
    return False


def _clean_text(text: str) -> str:
    """Clean up chunk text."""
    # Remove excessive blank lines
    text = re.sub(r'\n{4,}', '\n\n\n', text)
    # Remove escaped markdown characters (from L3 file)
    text = text.replace('\\#', '#').replace('\\*', '*')
    text = text.replace('\\-', '-').replace('\\.', '.')
    text = text.replace('\\[', '[').replace('\\]', ']')
    return text.strip()


def chunk_markdown(
    content: str,
    source_file: str,
    level: str,
    service: str = "",
    max_chunk_size: int = 3000,
    chunk_overlap: int = 100,
) -> list[Chunk]:
    """
    Chunk a markdown document using header-based semantic splitting.

    Args:
        content: Raw markdown text.
        source_file: Path to the source file (for metadata).
        level: KB level (L1, L2, L3).
        service: Service name (e.g., "Khata Transfer").
        max_chunk_size: Max characters per chunk after secondary split.
        chunk_overlap: Overlap for secondary character splitting.

    Returns:
        List of Chunk objects with metadata.
    """
    # Define headers to split on
    headers_to_split_on = [
        ("#", "h1"),
        ("##", "h2"),
        ("###", "h3"),
    ]

    # Primary split by markdown headers
    md_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=headers_to_split_on,
        strip_headers=False,
    )

    header_chunks = md_splitter.split_text(content)

    # Secondary splitter for oversized chunks
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=max_chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    chunks = []
    seen_hashes = set()

    for hc in header_chunks:
        text = hc.page_content
        header_meta = hc.metadata  # e.g., {"h1": "...", "h2": "..."}

        # Filter noise
        if _is_noise_section(text):
            continue
        if _is_duplicate_testimonial(text):
            continue

        # Clean text
        text = _clean_text(text)

        # Skip very short chunks
        if len(text.strip()) < 50:
            continue

        # Build metadata
        meta = {
            "source_file": source_file,
            "level": level,
            "service": service,
            **header_meta,
        }

        # Secondary split if too large
        if len(text) > max_chunk_size:
            sub_chunks = text_splitter.split_text(text)
            for i, sub_text in enumerate(sub_chunks):
                sub_text = sub_text.strip()
                if len(sub_text) < 50:
                    continue

                content_hash = hashlib.md5(sub_text[:300].encode()).hexdigest()
                if content_hash in seen_hashes:
                    continue
                seen_hashes.add(content_hash)

                chunk_meta = {**meta, "sub_chunk": i}
                chunks.append(Chunk(text=sub_text, metadata=chunk_meta))
        else:
            content_hash = hashlib.md5(text[:300].encode()).hexdigest()
            if content_hash in seen_hashes:
                continue
            seen_hashes.add(content_hash)

            chunks.append(Chunk(text=text, metadata=meta))

    return chunks


def load_and_chunk_l1(kb_dir: str) -> list[Chunk]:
    """
    Load and chunk all L1 documents.

    Merges all source files per service directory, then chunks.
    """
    l1_dir = Path(kb_dir) / "L1"
    all_chunks = []

    if not l1_dir.exists():
        return all_chunks

    for service_dir in sorted(l1_dir.iterdir()):
        if not service_dir.is_dir() or service_dir.name.startswith('.'):
            continue

        service_name = service_dir.name

        # Merge all source files for this service
        merged_content = ""
        source_files = []
        for md_file in sorted(service_dir.glob("*.md")):
            with open(md_file, 'r', encoding='utf-8') as f:
                file_content = f.read()
            merged_content += f"\n\n---\n\n{file_content}"
            source_files.append(str(md_file.relative_to(kb_dir)))

        if not merged_content.strip():
            continue

        source_ref = "; ".join(source_files)
        chunks = chunk_markdown(
            content=merged_content,
            source_file=source_ref,
            level="L1",
            service=service_name,
        )
        all_chunks.extend(chunks)

    return all_chunks


def load_and_chunk_l2(kb_dir: str) -> list[Chunk]:
    """Load and chunk all L2 documents."""
    l2_dir = Path(kb_dir) / "L2"
    all_chunks = []

    if not l2_dir.exists():
        return all_chunks

    for md_file in sorted(l2_dir.glob("*.md")):
        with open(md_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Derive service name from filename
        service_name = md_file.stem.replace('_', ' ').title()
        source_file = str(md_file.relative_to(kb_dir))

        chunks = chunk_markdown(
            content=content,
            source_file=source_file,
            level="L2",
            service=service_name,
        )
        all_chunks.extend(chunks)

    return all_chunks


def load_and_chunk_l3(kb_dir: str) -> list[Chunk]:
    """Load and chunk all L3 documents."""
    l3_dir = Path(kb_dir) / "L3"
    all_chunks = []

    if not l3_dir.exists():
        return all_chunks

    for md_file in sorted(l3_dir.glob("*.md")):
        with open(md_file, 'r', encoding='utf-8') as f:
            content = f.read()

        source_file = str(md_file.relative_to(kb_dir))

        chunks = chunk_markdown(
            content=content,
            source_file=source_file,
            level="L3",
            service="Discrepancy & Pain Points",
        )
        all_chunks.extend(chunks)

    return all_chunks


def load_and_chunk_l4(kb_dir: str) -> list[Chunk]:
    """Load and chunk all L4 legal drafting documents."""
    l4_dir = Path(kb_dir) / "L4"
    all_chunks = []

    if not l4_dir.exists():
        return all_chunks

    for md_file in sorted(l4_dir.glob("*.md")):
        with open(md_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Derive deed name from filename
        deed_name = md_file.stem.replace('_', ' ').replace('-', ' ').title()
        source_file = str(md_file.relative_to(kb_dir))

        chunks = chunk_markdown(
            content=content,
            source_file=source_file,
            level="L4",
            service=deed_name,
        )
        all_chunks.extend(chunks)

    return all_chunks


def load_and_chunk_l5(kb_dir: str) -> list[Chunk]:
    """Load and chunk all L5 internal SOP documents."""
    l5_dir = Path(kb_dir) / "L5"
    all_chunks = []

    if not l5_dir.exists():
        return all_chunks

    for md_file in sorted(l5_dir.glob("*.md")):
        with open(md_file, 'r', encoding='utf-8') as f:
            content = f.read()

        doc_name = md_file.stem.replace('_', ' ').replace('-', ' ').title()
        source_file = str(md_file.relative_to(kb_dir))

        chunks = chunk_markdown(
            content=content,
            source_file=source_file,
            level="L5",
            service=doc_name,
        )
        all_chunks.extend(chunks)

    return all_chunks


if __name__ == "__main__":
    """Quick test: chunk and print stats."""
    kb_dir = os.path.dirname(os.path.abspath(__file__))

    print("=== L1 Chunking ===")
    l1_chunks = load_and_chunk_l1(kb_dir)
    print(f"L1: {len(l1_chunks)} chunks")
    if l1_chunks:
        print(f"  Sample: {l1_chunks[0].text[:100]}...")
        print(f"  Metadata: {l1_chunks[0].metadata}")

    print("\n=== L2 Chunking ===")
    l2_chunks = load_and_chunk_l2(kb_dir)
    print(f"L2: {len(l2_chunks)} chunks")
    if l2_chunks:
        print(f"  Sample: {l2_chunks[0].text[:100]}...")
        print(f"  Metadata: {l2_chunks[0].metadata}")

    print("\n=== L3 Chunking ===")
    l3_chunks = load_and_chunk_l3(kb_dir)
    print(f"L3: {len(l3_chunks)} chunks")
    if l3_chunks:
        print(f"  Sample: {l3_chunks[0].text[:100]}...")
        print(f"  Metadata: {l3_chunks[0].metadata}")

    print("\n=== L4 Chunking ===")
    l4_chunks = load_and_chunk_l4(kb_dir)
    print(f"L4: {len(l4_chunks)} chunks")
    if l4_chunks:
        print(f"  Sample: {l4_chunks[0].text[:100]}...")
        print(f"  Metadata: {l4_chunks[0].metadata}")

    print("\n=== L5 Chunking ===")
    l5_chunks = load_and_chunk_l5(kb_dir)
    print(f"L5: {len(l5_chunks)} chunks")
    if l5_chunks:
        print(f"  Sample: {l5_chunks[0].text[:100]}...")
        print(f"  Metadata: {l5_chunks[0].metadata}")
