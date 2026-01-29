from fastapi import FastAPI, Response
from fastapi.responses import StreamingResponse
import cv2
import threading
import time
import uvicorn


FRAME_RATE = 30
DELAY = round((1/FRAME_RATE), 2)

app = FastAPI()

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
            cv2.circle(frame, (center_x, center_y), 10, self.color, self.thickness)
        elif self.style == 'x-circle':
            cv2.circle(frame, (center_x, center_y), 15, self.color, self.thickness)
            cv2.line(frame, (center_x - 20, center_y), (center_x + 20, center_y),
                     self.color, self.thickness)
            cv2.line(frame, (center_x, center_y - 20), (center_x, center_y + 20),
                     self.color, self.thickness)
        elif self.style == 'dot':
            cv2.circle(frame, (center_x, center_y), 4, self.color, -1)

ch = Crosshair()

# Функция захвата видео с камеры в отдельном потоке
def capture_frames():
    global latest_frame
    # Используйте 0 для камеры по умолчанию или 1, 2 для USB-камер[citation:3]
    camera = cv2.VideoCapture(0)
    while True:
        success, frame = camera.read()
        if success:
            with lock:
                # Рисуем прицел
                ch.draw(frame)
                # Конвертируем кадр в формат JPEG
                encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 90]
                _, jpeg_buffer = cv2.imencode('.jpg', frame, encode_param)
                latest_frame = jpeg_buffer.tobytes()
        time.sleep(DELAY)

# Запускаем захват видео при старте API
thread = threading.Thread(target=capture_frames, daemon=True)
thread.start()



@app.get("/video")
def video_feed():
    """Эндпоинт для видеопотока (MJPEG) - Не работает через интерактивную документацию"""
    def generate_frames():
        global latest_frame
        while True:
            with lock:
                if latest_frame is not None:
                    frame_data = latest_frame
            if frame_data:
                # Формируем ответ для MJPEG потока[citation:6]
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_data + b'\r\n')
            time.sleep(DELAY)

    return StreamingResponse(generate_frames(),
                             media_type="multipart/x-mixed-replace; boundary=frame")

@app.get("/screenshot")
def get_snapshot():
    """Эндпоинт для получения одного скриншота"""
    global latest_frame
    with lock:
        if latest_frame is None:
            return {"error": "Камера не готова"}
        return Response(content=latest_frame, media_type="image/jpeg")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8877)