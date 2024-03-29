from google.cloud import speech
import queue
from typing import List
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Response, Depends
from starlette.websockets import WebSocketState
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

from internal.services.speechRecognitionSerice import SpeechRecognitionService

from internal.clients.web_socket_client import WebSocketClient

from internal.handlers.pinecone_handlers import PineConeHandler

from routes.openai_routes import openai_router
from routes.call_routes import call_router
from routes.azure_speech_routes import azure_speech_router

from internal.services.text_to_speech_service import TextToSpeechService

from google_speech_wrapper import GoogleSpeechWrapper

from dotenv import load_dotenv

import asyncio

import threading

import uvicorn
import os

from google.cloud import texttospeech

load_dotenv()

app = FastAPI()

origins = [
    'http://localhost',
    'http://localhost:3000',
    'http://localhost:3001',
    'ws://localhost:3000',
    'http://localhost:8000',
    'http://localhost:8001',
    'http://localhost:8080'
]

app.add_middleware(
    CORSMiddleware,
    allow_origins='*',
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

app.include_router(openai_router)
app.include_router(call_router)
app.include_router(azure_speech_router)

os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = \
    os.path.join(os.path.dirname(__file__), 'creds',
                 'google_speech_secret_key.json')


@app.get("/")
def read_root():
    return {"Hello": "World"}


clients = {}


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: List[WebSocket] = []
        # self.speech_recognition_service = SpeechRecognitionService(self.speech_buffer)
    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)

    async def disconnect(self, websocket: WebSocket, client_id=None) -> None:
        self.active_connections.remove(websocket)

        try:
            await websocket.close()
        except Exception as e:
            print('disconnect', e)

    async def send_personal_message(self, message: str, websocket: WebSocket) -> None:
        await websocket.send_text(message)

    async def send_speech_to_text(self, message: str, websocket: WebSocket, speechRecognitionService: SpeechRecognitionService) -> None:
        speechRecognitionService.speech_buffer.write(message)
        await websocket.send_text(speechRecognitionService.recognize_speech(message))

    async def broadcast(self, message: str) -> None:
        for connection in self.active_connections:
            await connection.send_text(message)


manager = ConnectionManager()


async def get_data_loop(websocket: WebSocket, client_id: str):
    while websocket.application_state.CONNECTED == WebSocketState.CONNECTED \
    and websocket.client_state.CONNECTED == WebSocketState.CONNECTED:
        try:
            data = await websocket.receive_bytes()
            GoogleSpeechWrapper.receive_data(client_id, data)

        except Exception as e:
            print('get_data_loop', e)
            break

@app.websocket("/audio/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: int):
    await manager.connect(websocket)

    config = {
        'audio': {
            'encoding': 'LINEAR16',
            'sampleRateHertz': 16000,
            'languageCode': 'en-US',
        },
        'interimResults': True
    }

    try:
        get_data_task = asyncio.create_task(
            get_data_loop(websocket, client_id))
        speech_recognition = asyncio.create_task(
            GoogleSpeechWrapper.start_recognition_stream(websocket, client_id, config))

        await asyncio.gather(get_data_task, speech_recognition)

    except WebSocketDisconnect as websocket_disconnect:
        print('disconnecting... ', websocket_disconnect)
        await manager.disconnect(websocket, client_id)

    except Exception as e:
        print('wse', e)

    finally:
        print('disconnecting...')
        await GoogleSpeechWrapper.stop_recognition_stream(client_id)

from pydantic import BaseModel

from typing import Optional
class SpeechRequest(BaseModel):
    text: str
    voice: Optional[str]

@app.get('/text_to_speech')
async def get_text_to_speech(request: Request, data = Depends(SpeechRequest)):
    try:
        print(data)
        text = data.text
        voice = data.voice
        voice = 'en-US-Wavenet-A' if voice is None else voice
        language_code = 'en-US'

        text_to_speech_service = TextToSpeechService(voice, language_code)
        audio_content = text_to_speech_service.talk(text)

        # return StreamingResponse(audio_generator(), media_type='audio/mp3')
        return Response(content=audio_content, media_type='audio/webm;codecs=vp9,opus')

    except WebSocketDisconnect as websocket_disconect:
        print(websocket_disconect)
        return {'error': str(websocket_disconect)}

    except Exception as e:
        print(e)
        return {'error': str(e)}

if __name__ == '__main__':
    uvicorn.run('main:app', host='localhost', port=8001, reload=True)
