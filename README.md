# Vault PropTech Legal Assistant

AI-powered legal assistant for property documentation and services in Bangalore, Karnataka.

## Setup

1. **Install dependencies:**
```bash
pip install -r requirements.txt
```

2. **Add your API keys to `.env`:**
```bash
cp .env.example .env
# Edit .env and add:
# - GEMINI_API_KEY (required)
# - PINECONE_API_KEY (required for production)
```

3. **Migrate to Pinecone (first time only):**
```bash
# Option A: Use existing ChromaDB (local development)
python setup.py ingest

# Option B: Migrate to Pinecone (for deployment)
python setup.py migrate
```

## Usage

### Web UI (Recommended)
```bash
streamlit run app.py
```
Then open your browser to `http://localhost:8501`

### Command Line
```bash
# Ask a question
python setup.py ask "What is Khata Transfer?"

# Just retrieve chunks (no LLM)
python setup.py query "What is E-Khata?"

# Check statistics
python setup.py stats

# Run tests
python setup.py test
```

## Deployment (Vercel)

### Prerequisites
- Vercel account
- Pinecone account (free tier)

### Steps

1. **Get Pinecone API key:**
   - Sign up at https://www.pinecone.io/
   - Create a project and copy your API key

2. **Migrate to Pinecone:**
```bash
# Add PINECONE_API_KEY to .env
python setup.py migrate
```

3. **Install Vercel CLI:**
```bash
npm i -g vercel
```

4. **Set environment variables in Vercel:**
```bash
vercel env add GEMINI_API_KEY
vercel env add PINECONE_API_KEY
```

5. **Deploy:**
```bash
vercel --prod
```

### Environment Variables (Vercel Dashboard)
Add these in your Vercel project settings:
- `GEMINI_API_KEY` - Your Google Gemini API key
- `PINECONE_API_KEY` - Your Pinecone API key

## Features

- 🤖 AI-powered responses using Gemini 2.5 Flash
- 📚 RAG (Retrieval-Augmented Generation) with Pinecone
- 🎯 Intelligent query routing (legal/services/issues)
- 💬 User-friendly chat interface
- 📱 Example questions for quick start
- ☁️ Serverless deployment ready

## Knowledge Base Structure

- **L1**: Legal expertise and process guides
- **L2**: Vault services, pricing, and offerings
- **L3**: Common issues and troubleshooting

## Contact Vault PropTech

- 📞 +91 88619 50376
- 📧 info@vaultproptech.com
- 🌐 https://www.vaultproptech.com
