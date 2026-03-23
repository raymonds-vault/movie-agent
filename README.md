# 🎬 Cinemax Oracle: Agentic Movie Discovery

Cinemax Oracle is a next-generation movie assistant built with **Python** and **LangGraph**. Unlike standard linear chatbots, this agent uses a cyclic state machine to research films, verify streaming availability, and manage user watchlists with human-like reasoning.

## 🚀 Features
* **Cyclic Reasoning:** Uses LangGraph to loop back and refine searches if initial results are poor.
* **Tool Integration:** Seamlessly connects with TMDB API for metadata and OMDb for ratings.
* **Streaming Intelligence:** Identifies where movies are currently available (Netflix, Prime, Disney+, etc.).
* **Stateful Memory:** Remembers user preferences and previous queries across the entire session.

## 🛠️ Tech Stack
* **Language:** Python 3.10+
* **Orchestration:** [LangGraph](https://github.com/langchain-ai/langgraph)
* **LLM Framework:** LangChain
* **AI Models:** AWS Bedrock / OpenAI (Configurable)

## 🏗️ The Graph Architecture
The agent operates on a directed cyclic graph with the following nodes:
1.  **Categorizer:** Determines if the user wants a recommendation, a specific search, or a watchlist update.
2.  **Researcher:** Fetches deep metadata and cast information.
3.  **Availability Checker:** Checks real-time streaming status.
4.  **Final Response:** Compiles all findings into a natural language summary.

## 🚦 Getting Started

### Prerequisites
* Python 3.10 or higher
* API Keys for TMDB and your chosen LLM provider

### Installation
1. Clone the repo:
   ```bash
   git clone git@github.com:your-username/cinemax-oracle.git
   cd cinemax-oracle