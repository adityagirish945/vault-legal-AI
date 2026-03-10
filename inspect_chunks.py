#!/usr/bin/env python3
"""Quick script to inspect ChromaDB chunks and find the large collections."""

import chromadb

def inspect_collections():
    client = chromadb.PersistentClient(path="./chroma_db")
    collections = client.list_collections()
    
    for collection in collections:
        coll = client.get_collection(collection.name)
        count = coll.count()
        
        # Get first 5 chunks to inspect
        result = coll.get(limit=5, include=['documents', 'metadatas'])
        
        print(f"\n{'='*60}")
        print(f"Collection: {collection.name}")
        print(f"Total chunks: {count}")
        print(f"{'='*60}")
        
        for i, (doc, meta) in enumerate(zip(result['documents'], result['metadatas'])):
            print(f"\nChunk {i+1}:")
            print(f"Metadata: {meta}")
            print(f"Content preview: {doc[:200]}...")
            print(f"Content length: {len(doc)} chars")

if __name__ == "__main__":
    inspect_collections()