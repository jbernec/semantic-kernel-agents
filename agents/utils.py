import asyncio
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizableTextQuery
from azure.core.credentials import AzureKeyCredential
from azure.search.documents.models import (
    QueryType,
    QueryCaptionType,
    QueryAnswerType
)
from langgraph.graph import StateGraph, START, END
#from langgraph_checkpoint_cosmosdb import CosmosDBSaver
from azure.cosmos import exceptions, PartitionKey #CosmosClient
from azure.cosmos.aio import CosmosClient
from azure.keyvault.secrets import SecretClient
import os
import azure.identity
from azure.identity import DefaultAzureCredential
from openai import AzureOpenAI
from langchain_openai import AzureChatOpenAI
from langgraph_supervisor import  create_supervisor
from langgraph.prebuilt import  create_react_agent
import uuid
from pprint import pprint
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, AIMessageChunk
import yaml
import logging
import datetime # Add this import
from semantic_kernel.functions import kernel_function
from typing import Annotated


# Set up logging for better error tracking
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logging.getLogger().setLevel(logging.ERROR)  # Only show ERROR and CRITICAL logs
logger = logging.getLogger(__name__)

CONFIG = {
    "KEY_VAULT_NAME": "akvlab00",
    "PROMPT_DIR": os.path.join(os.path.dirname(__file__), 'prompts'),
    "INDEX_NAME": "image-verbalization-index",
}

keyVaultName = CONFIG["KEY_VAULT_NAME"]
KVUri = f"https://{keyVaultName}.vault.azure.net"

credential = DefaultAzureCredential()
client = SecretClient(vault_url=KVUri, credential=credential)

search_credential =AzureKeyCredential(client.get_secret(name="aisearch-key").value)
search_endpoint =client.get_secret(name="aisearch-endpoint").value
index_name = CONFIG["INDEX_NAME"]

"""
This code loads and sets the necessary variables for Azure services.
The variables are loaded from Azure Key Vault.
"""
# Open AI
azure_openai_endpoint=client.get_secret(name="aoai-endpoint").value
azure_openai_deployment=client.get_secret(name="aoai-deploymentname").value
azure_openai_api_key=client.get_secret(name="aoai-api-key").value
azure_openai_api_version = "2024-02-15-preview"
# Embedding
azure_openai_embedding_deployment = "text-embedding-3-small"
azure_openai_embedding_model =client.get_secret(name="aoai-embedding-model").value
azure_openai_vector_dimension = 1536

azure_openai_client = AzureOpenAI(
    api_key=azure_openai_api_key,
    api_version=azure_openai_api_version,
    azure_endpoint=azure_openai_endpoint,
)

# Service principal authentication variables
tenant_id=client.get_secret(name="tenantid").value
client_id =client.get_secret(name="clientid").value 
client_secret =client.get_secret(name="clientsecret").value
#credential = azure.identity.ClientSecretCredential(tenant_id=tenant_id, client_id=client_id, client_secret=client_secret)
credential = DefaultAzureCredential()

class SearchRetrievalPlugin:
    def __init__(self):
        # use module-level config/clients already defined in utils.py
        pass

    @kernel_function(description="Search and retrieve answers from Azure AI Search (plugin method).")
    def search_retrieval(self, user_input: Annotated[str, "The user query to search for."]) -> list:
        # copy of your existing search_retrieval() body (adjusted to use self if needed)
        query = user_input
        search_results = []
        logger.info(f"Searching for: '{query}'")

        if not search_results:
            try:
                logger.info("Querying Azure AI Search...")
                search_client = SearchClient(
                    endpoint=search_endpoint,
                    index_name=index_name,
                    credential=search_credential
                )
                vector_query = VectorizableTextQuery(
                    text=query,
                    k_nearest_neighbors=2,
                    fields="content_embedding",
                    exhaustive=True
                )

                ai_search_results = search_client.search(
                    search_text=query,
                    vector_queries=[vector_query],
                    select=["document_title", "content_text", "content_path", "locationMetadata"],
                    query_type=QueryType.SEMANTIC,
                    semantic_configuration_name='semanticconfig',
                    query_caption=QueryCaptionType.EXTRACTIVE,
                    query_answer=QueryAnswerType.EXTRACTIVE,
                    top=2
                )

                result_count = 0
                for result in ai_search_results:
                    result_count += 1
                    result_dict = {
                        "source": "Azure AI Search",
                        "document_title": result.get('document_title', ''),
                        "content_text": result.get('content_text', ''),
                        "content_path": result.get('content_path', ''),
                        "locationMetadata": result.get('locationMetadata', ''),
                        "@search.score": result.get('@search.score', 0),
                        "@search.reranker_score": result.get('@search.reranker_score', 0),
                    }
                    search_results.append(result_dict)

                logger.info(f"Found {result_count} results in Azure AI Search")
            except Exception as e:
                logger.error(f"Error querying Azure AI Search: {str(e)}")

        if search_results:
            logger.info(f"Returning {len(search_results)} total results")
            return search_results
        else:
            logger.warning("No results found in either data source")
            return [{
                "source": "No Results",
                "message": "No matching data found in available sources",
                "query": query
            }]


def search_retrieval(user_input: str) -> list:
    """
    Search and retrieve answers from both Cosmos DB chat history and Azure AI Search.
    First checks Cosmos DB for matching responses, then falls back to Azure AI Search if needed.
    
    Args:
        user_input: The user query to search for
        
    Returns:
        list: Combined search results from both sources or fallback results
    """
    query = user_input
    search_results = []
    
    # Add detailed logging to track search flow
    logger.info(f"Searching for: '{query}'")
    
    # 2. If no Cosmos DB results, try Azure AI Search
    if not search_results:
        try:
            logger.info("Querying Azure AI Search...")
            # Initialize Azure AI Search client
            search_client = SearchClient(
                endpoint=search_endpoint, 
                index_name=index_name, 
                credential=search_credential
            )
            vector_query = VectorizableTextQuery(
                text=query, 
                k_nearest_neighbors=2, 
                fields="content_embedding", 
                exhaustive=True
            )
            
            # Execute the search with semantic ranking enabled
            ai_search_results = search_client.search(
                search_text=query,
                vector_queries=[vector_query],
                select=["document_title", "content_text", "content_path", "locationMetadata"],
                query_type=QueryType.SEMANTIC,
                semantic_configuration_name='semanticconfig',
                query_caption=QueryCaptionType.EXTRACTIVE,
                query_answer=QueryAnswerType.EXTRACTIVE,
                top=2
            )
            
            # Process Azure AI Search results
            result_count = 0
            for result in ai_search_results:
                result_count += 1
                result_dict = {
                    "source": "Azure AI Search",
                    "document_title": result.get('document_title', ''),
                    "content_text": result.get('content_text', ''),
                    "content_path": result.get('content_path', ''),
                    "locationMetadata": result.get('locationMetadata', ''),
                    "@search.score": result.get('@search.score', 0),
                    "@search.reranker_score": result.get('@search.reranker_score', 0),
                }
                search_results.append(result_dict)
            
            logger.info(f"Found {result_count} results in Azure AI Search")
        except Exception as e:
            logger.error(f"Error querying Azure AI Search: {str(e)}")
    
    # 3. Return results or helpful message if nothing found
    if search_results:
        logger.info(f"Returning {len(search_results)} total results")
        return search_results
    else:
        logger.warning("No results found in either data source")
        # Return a more informative empty result
        return [{
            "source": "No Results",
            "message": "No matching data found in available sources",
            "query": query
        }]