# Semantic Kernel Agents — Integration path to Azure AI Foundry

Overview
--------
This folder demonstrates building local Semantic Kernel (SK) agents and the migration / integration path to creating corresponding Azure AI agents (Azure AI Foundry / Azure AI Agent Service). The notebooks show how local SK orchestration maps to service-side agents while preserving retrieval, provenance, and governance.

Key artifacts
-------------
- `agents/az_ai_agents.ipynb` — create `AzureAIAgent`, `AzureAIAgentSettings`, `AzureAIAgentThread`, and wire `SearchRetrievalPlugin`.
- `agents/sk_agent_orchestration_loop.ipynb` — sequential orchestration examples with SK agents.
- `agents/utils.py` — credential helpers and small utilities.

Design summary
--------------
- Local SK agents: host sequential orchestration, lightweight decision logic, and pre/post-processing.
- Azure AI agents (Foundry): created on the service for model execution, governance and scale.
- Integration path: map SK agent instructions and plugins to Azure agent definitions so service-side agents can call the same retrieval plugin and follow the same instruction set.

Semantic Kernel Agent Implementation (key features)
---------------------------------------------------
1. Short-term memory via thread object — Done  
   - Conversation and short-term state carried in `AzureAIAgentThread` / thread objects in notebooks.
2. Long-term memory — N/A  
   - Not implemented in these examples.
3. Evaluation — N/A  
   - No automated evaluation pipeline included in these notebooks.
4. Function calling via plugins — Done  
   - Retrieval and other external functions are implemented as plugins (e.g., `SearchRetrievalPlugin()`).
5. Observability — Planned  
   - Not included yet. Plan: add OpenTelemetry for local SK agents and Azure Monitor / Log Analytics for Azure AI agents.
6. Multiagent orchestration — Sequential orchestration (Done)  
   - Examples show explicit sequential orchestration (call skill/plugin → inspect → next step).
7. MCP (Multi-Client Policy) — N/A

Plugins & retrieval
-------------------
- `SearchRetrievalPlugin()` queries an Azure AI Search index and returns full fields and provenance.
- Recommended: always surface raw search results (definition, context, note, page number) and present them verbatim; allow agents to summarize without inventing facts.

Sequence: Local SK → Azure AI Foundry agents (short steps)
---------------------------------------------------------
1. Provision Azure AI (Agent Service / Foundry) and Azure Cognitive Search; load documents.  
2. Implement `SearchRetrievalPlugin` (returns full fields + provenance).  
3. Build local SK agents with sequential orchestration and thread/state handling.  
4. Create Azure agent on Foundry with the same instructions (use `AzureAIAgentSettings`, `client.agents.create_agent(...)`).  
5. Wire plugins to the Azure agent: `AzureAIAgent(..., plugins=[SearchRetrievalPlugin()])`.  
6. Use `AzureAIAgentThread` for conversation state and call `agent.invoke(...)`.  
7. Validate retrieval outputs, provenance, and thread handoffs end-to-end.

Sequential orchestration on local SK agents
------------------------------------------
- Keep orchestration explicit and deterministic: call skill/plugin → inspect results → choose next skill.  
- Use thread/state objects to pass context between steps.  
- Benefit: predictable flows and lower cloud usage for orchestration logic.

Simple architecture diagram
---------------------------
ASCII:
Local SK Agents (sequential orchestration)
  ├─> SearchRetrievalPlugin ──> Azure AI Search (index + documents)
  └─> Map instructions & state ──> Azure AI Agents (Foundry) ──> (can also call SearchRetrievalPlugin)

Optional Mermaid:
```mermaid
flowchart LR
  SK[Local SK Agents\n(sequential orchestration)]
  SRP[SearchRetrievalPlugin]
  AZSEARCH[Azure AI Search\n(index + docs)]
  AZAGENT[Azure AI Agents\n(Foundry)]
  SK --> SRP
  SRP --> AZSEARCH
  SK --> AZAGENT
  AZAGENT --> SRP