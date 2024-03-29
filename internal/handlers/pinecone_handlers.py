from ..services.pinecone_service import PineconeService, PineConeItem, MetaDataConfig

from ..services.openai_service import OpenAIClient

from uuid import uuid4

import typing

class PineConeHandler:
    def __init__(self) -> None:
        self.pinecone_service = PineconeService()
        self.openai_client = OpenAIClient()

    def handle_search_by_plain_text(self, text: str, index_name: str, top_k: int = 5) -> typing.List[PineConeItem]:
        # Get embeddings from openai_client
        embeddings = self.openai_client.get_embeddings(text)

        # Search for items from pinecone
        search_result = self.pinecone_service.search(
            index_name=index_name,
            query_vector=embeddings,
            top_k=top_k
        )

        # Return the results
        return search_result
    
if __name__ == '__main__':
    pc_handler = PineConeHandler()
    text = 'What is a cell?'

    index_name = 'curie-med-q-a'
    top_k = 5

    search_result = pc_handler.handle_search_by_plain_text(text, index_name, top_k)

    print(search_result)
    

