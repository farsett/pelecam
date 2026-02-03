### Установка

1. Перейдите в домашнюю директорию и склонируйте репозиторий
    ```
    git clone https://github.com/farsett/pelecam.git
    ```
2. Создайте виртуальное окружение `camenv`
   ```
   cd pelecam
   python3 -m venv camenv
   ```
3. Установите необходимые библиотеки
   ```
   source /camenv/bin/activate
   pip install fastapi uvicorn opencv-python cv2_enumerate_cameras dotenv
   ```
4. Сделайте `auto_start.sh` исполняемым и проверьте работоспособность
   ```
   sudo chmod +x auto_start.sh
   ./auto_start.sh
   ```
5. Добавьте cron-задачу на автозапуск
   ```
   sudo crontab -e
   ```
   добавив в конце:
    ```
   @reboot /путь/к/auto_start.sh
   ```
   
    ...либо создайте сервис