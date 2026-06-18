"""Build a presenter video script from YouTube transcripts using LangChain + OpenAI."""
from typing import List

from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

SCRIPT_PROMPT = PromptTemplate(
    input_variables=["topic", "context"],
    template="""You are a professional video script writer. Using ONLY the YouTube transcript \
content provided below, write a compelling presenter-style video script on the topic: "{topic}".

SOURCE CONTENT (from YouTube transcripts):
{context}

Write a structured script with these sections:
1. HOOK (30 seconds): An engaging opening that immediately captures attention.
2. INTRODUCTION (1 minute): Brief, clear overview of the topic.
3. KEY POINT 1: First main insight — explain it clearly and concisely.
4. KEY POINT 2: Second main insight — with any supporting evidence from the source.
5. KEY POINT 3: Third main insight — tie it back to real-world relevance.
6. EXAMPLES & DEMONSTRATIONS: Concrete examples drawn strictly from the source material.
7. SUMMARY & CALL TO ACTION (30 seconds): Recap the key takeaways and close confidently.

RULES:
- Use ONLY information from the provided YouTube source content above.
- Write in a conversational, professional tone suitable for an AI video presenter.
- Write only the spoken words — no stage directions, no [pause] markers.
- Keep the total script under 1,500 words.

Script:""",
)


class ScriptGenerator:
    """Generate a structured video script from Documents using FAISS retrieval + GPT-4o."""

    def __init__(self):
        self.llm = ChatOpenAI(model="gpt-4o", temperature=0.7, max_tokens=2000)
        self.embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000, chunk_overlap=200
        )

    def build(self, docs: List[Document], topic: str) -> str:
        if not docs:
            raise ValueError(
                "No transcript documents to process. "
                "Ensure at least one YouTube URL has captions available."
            )

        chunks = self.splitter.split_documents(docs)
        vector_store = FAISS.from_documents(chunks, self.embeddings)
        retriever = vector_store.as_retriever(search_kwargs={"k": 15})

        relevant_docs = retriever.invoke(topic)
        context = "\n\n---\n\n".join(d.page_content for d in relevant_docs)

        chain = SCRIPT_PROMPT | self.llm | StrOutputParser()
        return chain.invoke({"topic": topic, "context": context})
