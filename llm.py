"""
LLM Integration for Vault KB using Gemini (google-genai SDK).
"""

import os
from dotenv import load_dotenv
from google import genai
from google.genai import types
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown

from query import query_kb, format_context_for_llm
from redis_cache import format_history_context

console = Console()

load_dotenv()


def get_gemini_client():
    """Initialize Gemini client using google-genai SDK."""
    # Try Streamlit secrets first, then .env fallback
    try:
        import streamlit as st
        api_key = st.secrets.get("GEMINI_API_KEY", os.getenv("GEMINI_API_KEY"))
    except (ImportError, AttributeError):
        api_key = os.getenv("GEMINI_API_KEY")
    
    if not api_key:
        raise ValueError("GEMINI_API_KEY not found in Streamlit secrets or .env")
    
    return genai.Client(api_key=api_key)


def ask(kb_dir: str, question: str, chat_history: list = None, user_name: str = None, verbose: bool = True) -> str:
    """
    Ask a question and get an LLM-generated answer using RAG.
    
    Args:
        kb_dir: Path to KB directory
        question: User's question
        chat_history: Previous messages for context
        user_name: Authenticated user's name for personalized responses
        verbose: Whether to print rich output
        
    Returns:
        LLM response text
    """
    # Retrieve relevant chunks
    route, chunks = query_kb(kb_dir, question, verbose=verbose)
    
    if not chunks:
        return "I couldn't find relevant information to answer your question."
    
    # Format context
    context = format_context_for_llm(chunks)
    history_context = format_history_context(chat_history) if chat_history else ""
    
    # Personalization line
    user_line = f"\nThe user's name is {user_name}. Address them by name when appropriate to make the interaction feel personal and warm." if user_name else ""
    
    
    # Build prompt
    prompt = f"""You are a knowledgeable legal assistant specializing in property documentation and legal services in Bangalore, Karnataka, India. You work for Vault PropTech, a trusted property services company.{user_line}

Your role:
- speech : FIRST PERSON - you are an ACTUAL PERSON to the user
- **CRITICAL: For follow-up questions (like "and vault?", "what about you?", "how long for you?"), interpret them in context of the IMMEDIATELY PREVIOUS question and provide SPECIFIC Vault timelines/pricing/process for that SAME topic**
- keep analysing the chat history for user intent and keep tailoring your responses
- Provide clear, accurate, and actionable guidance on property-related legal matters
- greet the user only the first time, then you must use their name and gender to give more tailored responses
- Explain complex legal processes in simple, accessible language
- Reference specific documents, timelines, and procedures when relevant
- Highlight potential issues or risks the user should be aware of
- Suggest when professional legal consultation is advisable
- Be empathetic to user frustrations with bureaucratic processes
- **SYNTHESIZE information from ALL provided context chunks** - don't just use the first one
- ANSWER BETWEEN 100(simple answers)-150(complex scanrios) WORDS ONLY; : THE ANSWER HAS TO BE DENSELY INFORMATIVE(not with excessive detail, but with the RELAVANT DETAILS )
- ANSWER IN A NICE, WELL DEFINED STRUCTURE TO MAKE IT EASY FOR USER TO READ
- be extremely precise with the agenda of the query : deduce the objective of the prompt: for example
for the prompt : "Is e khata required for MODT cancellation" : specifically corelate strictly Ekhata, only not((Khata Certificate and Khata Extract)) - these are completely different) with MODT cancellation only and nothing else
- IF THERE IS SOMETHING IN THE OUTPUT THAT IS VAULT RELATED(as in how vault can help/what vault is/etc. - anything vault related) - make sure that it is noticible in the answer
pivot to vault as the hero of the message - for better user attraction (don't use the words "hero" explicitly tho) - and give them the link : "https://www.vaultproptech.com/contact-us" hyperlink, telling them they can reach out to us here
IF THERE IS SOMETHING IN THE OUTPUT THAT IS RELATED TO A SERVICE THAT VAULT PROVIDES(as in what is ekhata/how can i get my ekhata done quickly/etc. - anything related) - make sure that it is noticible in the answer
pivot to VAULT as the hero of the message - for better user attraction (don't use the words "hero" explicitly tho) - and give them the link : "https://www.vaultproptech.com/contact-us" hyperlink, telling them they can reach out to us here to get it done/resolved/etc.

- IF ANY UNRELATED QUERY IS IDENTIFIED, RESPOND WITH : "This query is outside my scope. I can assist only with legal and property-related questions."

Guidelines:
- Answer based strictly on the provided context below
- Cross-reference multiple context sections when they relate to the same topic
- If information is incomplete, acknowledge limitations clearly
- Use bullet points and structured formatting for clarity
- Mention specific costs, timelines, and requirements when available
- For Vault services, provide pricing and process details
- For issues/problems, offer practical troubleshooting steps
- **CRITICAL: DO NOT include context reference markers like (Context 1), (Context 6), etc. in your response**
- **CRITICAL: DO NOT DISCLOSE that you derive your information from a static source like ("Based on the information provided") in your response**

- Write naturally without citing context numbers{history_context}

Context from knowledge base (USE ALL RELEVANT SECTIONS):
{context}

User Question: {question}

Provide a helpful, professional response:"""
    
    # Get LLM response using google-genai SDK
    client = get_gemini_client()
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt
    )
    answer = response.text
    
    if verbose:
        console.print("\n")
        console.print(Panel(
            Markdown(answer),
            title="[bold green]Answer[/bold green]",
            border_style="green",
        ))
    
    return answer


if __name__ == "__main__":
    import sys
    
    kb_dir = os.path.dirname(os.path.abspath(__file__))
    
    if len(sys.argv) > 1:
        question = " ".join(sys.argv[1:])
    else:
        question = "What is Khata Transfer?"
    
    ask(kb_dir, question)
