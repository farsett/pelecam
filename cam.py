import os
from fastapi import FastAPI, Response
from fastapi.responses import StreamingResponse, JSONResponse
import cv2
from cv2_enumerate_cameras import enumerate_cameras
import threading
import time
import uvicorn
import dotenv
from pydantic import BaseModel, Field


# Настройки
dotenv.load_dotenv()
FRAME_RATE = int(os.getenv('FRAME_RATE', 30))
_delay = round((1/FRAME_RATE), 2)
RESIZE_COEF = float(os.getenv('RESIZE_COEF', 1))
QUALITY = int(os.getenv('QUALITY', 90))
CH_STYLE = os.getenv('CH_STYLE', 'simple')
COLOR = os.getenv('COLOR', 'red')
_color_code = {'red': (0, 0, 255), 'green': (0, 255, 0), 'blue': (255, 0, 0)}
THICKNESS = int(os.getenv('THICKNESS', 1))

class Settings(BaseModel):
    frame_rate: int = Field(30, title="Частота кадров", description="от 1 до 60")
    resize_coef: float = Field(1, title='Коэффициент масштабирования изображения', description="от 0.1 до 5")
    quality: int = Field(90, title="Качество изображения в процентах", description="от 10 до 100")
    ch_style: str = Field('simple', title="Тип прицела", description="simple, circle, x-circle, dot")
    color: str = Field('red', title="Цвет прицела", description="red, green, blue")
    thickness: int = Field(1, title="Толщина прицела", description="от 1 до 10")

DEVICE_ID = int(os.getenv('DEVICE_ID', 0))
IP_ADDRESS = os.getenv('CAP_API_IP', '0.0.0.0')
PORT = int(os.getenv('CAM_API_PORT', 8877))

app = FastAPI(title="Camera API", version="0.2")

# Глобальная переменная для последнего кадра
latest_frame = None
lock = threading.Lock()


class Crosshair:
    def __init__(self, color=(0, 0, 255), thickness=1, style='simple'):
        self.color = color
        self.thickness = thickness
        self.style = style

    def draw(self, frame, center_x=None, center_y=None):
        if center_x is None or center_y is None:
            height, width = frame.shape[:2]
            center_x, center_y = width // 2, height // 2

        if self.style == 'simple':
            cv2.line(frame, (center_x, 0), (center_x, frame.shape[0]),
                     self.color, self.thickness)
            cv2.line(frame, (0, center_y), (frame.shape[1], center_y),
                     self.color, self.thickness)
        elif self.style == 'circle':
            cv2.circle(frame, (center_x, center_y), self.thickness*3, self.color, self.thickness)
        elif self.style == 'x-circle':
            cv2.circle(frame, (center_x, center_y), 15, self.color, self.thickness)
            cv2.line(frame, (center_x - 20, center_y), (center_x + 20, center_y),
                     self.color, self.thickness)
            cv2.line(frame, (center_x, center_y - 20), (center_x, center_y + 20),
                     self.color, self.thickness)
        elif self.style == 'dot':
            cv2.circle(frame, (center_x, center_y), self.thickness, self.color, -1)

ch = Crosshair(color=_color_code[COLOR], style=CH_STYLE, thickness=THICKNESS)

# Функция захвата видео с камеры в отдельном потоке
def capture_frames():
    global latest_frame
    camera = cv2.VideoCapture(DEVICE_ID)
    while True:
        success, frame = camera.read()
        if success:
            with lock:
                # Рисуем прицел
                ch.draw(frame)
                # Меняем размер, если необходимо
                if RESIZE_COEF != 1:
                    frame = cv2.resize(frame, [int(i * RESIZE_COEF) for i in frame.shape[:2]][::-1])
                # Конвертируем кадр в формат JPEG
                encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), QUALITY]
                _, jpeg_buffer = cv2.imencode('.jpg', frame, encode_param)
                latest_frame = jpeg_buffer.tobytes()
        time.sleep(_delay)

# Запускаем захват видео при старте API
thread = threading.Thread(target=capture_frames, daemon=True)
thread.start()


@app.get("/video", summary="Видеопоток")
def video_feed():
    """Эндпоинт для видеопотока (MJPEG) - Не работает через интерактивную документацию"""
    def generate_frames():
        global latest_frame
        while True:
            with lock:
                if latest_frame is not None:
                    frame_data = latest_frame
            if frame_data:
                # Формируем ответ для MJPEG потока
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_data + b'\r\n')
            time.sleep(_delay)
    return StreamingResponse(generate_frames(),
                             media_type="multipart/x-mixed-replace; boundary=frame")

@app.get("/screenshot", summary="Получить скриншот")
def get_screenshot():
    """Эндпоинт для получения одного скриншота"""
    global latest_frame
    with lock:
        if latest_frame is None:
            return {"error": "Камера не готова"}
        return Response(content=latest_frame, media_type="image/jpeg")

@app.get("/available_cams", summary="Получить список доступных камер", responses={
    200: {
        "description": "Возвращает текущие настройки",
        "content": {
            "application/json": {
                "example": {"0": "HD Webcam", "1": "USB Camera"}
            }
        }
    }
})
def get_available_cams():
    """
    Эндпоинт для получения списка доступных камер. Нужный ID вписать в .env, а после перезапустить сервер.

    ID : Name
    """
    return {cam.index: cam.name for cam in enumerate_cameras(cv2.CAP_MSMF)}

@app.get("/settings", summary="Получить текущие настройки", responses={
    200: {
        "description": "Возвращает текущие настройки",
        "content": {
            "application/json": {
                "example": {
                    "frame_rate": 30, "resize_coef": 1, "quality": 90, "ch_style": "simple", "color": "red", "thickness": 1}
            }
        }
    }
})
def get_settings():
    """Эндпоинт получения текущих настроек"""
    return {
        "frame_rate": FRAME_RATE,
        "resize_coef": RESIZE_COEF,
        "quality": QUALITY,
        "ch_style": CH_STYLE,
        "color": COLOR,
        "thickness": THICKNESS,
    }

@app.post("/settings", summary="Задать новые настройки", responses={
    200: {
        "description": "Возвращает сообщение об успешном изменении настроек",
        "content": {
            "application/json": {
                "example": {'message': "Настройки изменены"}
            }
        }
    },
    400: {
        "description": "Возвращает сообщение о некорректном значении",
        "content": {
            "application/json": {
                "example": {'message': "Некорректный тип прицела"}}
            }
    }
})
def set_settings(settings: Settings):
    if not 1 <= settings.frame_rate <= 60:
        return JSONResponse(content={"message": "Отправьте значение frame_rate от 1 до 60"}, status_code=400,
                        headers={"Content-Type": "application/json"})
    if not 0.1 <= settings.resize_coef <= 5:
        return JSONResponse(content={"message": "Отправьте значение resize_coef от 0.1 до 5"}, status_code=400,
                        headers={"Content-Type": "application/json"})
    if not 10 <= settings.quality <= 100:
        return JSONResponse(content={"message": "Отправьте значение quality от 0.1 до 5"}, status_code=400,
                            headers={"Content-Type": "application/json"})
    if settings.ch_style not in ['simple', 'circle', 'x-circle', 'dot']:
        return JSONResponse(content={"message": "Некорректный тип прицела"}, status_code=400,
                            headers={"Content-Type": "application/json"})
    if settings.color not in ['red', 'green', 'blue']:
        return JSONResponse(content={"message": "Некорректный цвет прицела"}, status_code=400,
                            headers={"Content-Type": "application/json"})
    if not 1 <= settings.thickness <=10:
        return JSONResponse(content={"message": "Отправьте значение thickness от 1 до 10"}, status_code=400,
                            headers={"Content-Type": "application/json"})

    global _delay, RESIZE_COEF, QUALITY, ch

    # Меняем текущие
    _delay = round((1/settings.frame_rate), 2)
    RESIZE_COEF = settings.resize_coef
    QUALITY = settings.quality
    ch.style = settings.ch_style
    ch.color = _color_code[settings.color]
    ch.thickness = settings.thickness

    # Сохраняем в .env
    dotenv_file = dotenv.find_dotenv()
    dotenv.set_key(dotenv_file, 'FRAME_RATE', str(settings.frame_rate))
    dotenv.set_key(dotenv_file, 'RESIZE_COEF', str(settings.resize_coef))
    dotenv.set_key(dotenv_file, 'QUALITY', str(settings.quality))
    dotenv.set_key(dotenv_file, 'CH_STYLE', settings.ch_style)
    dotenv.set_key(dotenv_file, 'COLOR', settings.color)
    dotenv.set_key(dotenv_file, 'THICKNESS', str(settings.thickness))

    return {'message': "Настройки изменены"}

if __name__ == "__main__":
    uvicorn.run(app, host=IP_ADDRESS, port=PORT)