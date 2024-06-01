import threading
import queue
import subprocess
import os
import shutil
import telebot
from dotenv import load_dotenv

load_dotenv()
token = os.getenv('TOKEN')
bot = telebot.TeleBot(token)

INPUT_PATH = 'oemer_input'
OUTPUT_PATH = 'oemer_results'

if not os.path.exists(INPUT_PATH):
    os.makedirs(INPUT_PATH)
if not os.path.exists(OUTPUT_PATH):
    os.makedirs(OUTPUT_PATH)

# Создаем очередь для ввода пользователя
input_queue = queue.Queue()

# Состояние процессов (True, если процесс занят, иначе False)
process_states = [False, False, False]

# Блокировка для защиты доступа к process_states
lock = threading.Lock()

@bot.message_handler(commands=['start'])
def main(message): 
    bot.send_message(message.chat.id, 'привет')

@bot.message_handler(content_types=['photo'])
def get_photo(message):
    # идентификатор фотографии
    file_id = message.photo[-1].file_id
    # путь к фотографии в Tg
    tg_path = bot.get_file(file_id).file_path

    # Сохранение изображения
    downloaded_file = bot.download_file(tg_path)
    file_name = str(message.chat.id) + ".jpg"
    img_path = os.path.join(INPUT_PATH, file_name)
    with open(img_path, 'wb') as new_file:
        new_file.write(downloaded_file)

    # Помещаем путь изображения и ID пользователя в очередь
    output_dir = os.path.join(OUTPUT_PATH, str(message.chat.id))
    input_queue.put((img_path, output_dir))

# Функция для очистки выходной папки
def clear_output_dir(output_dir):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    for filename in os.listdir(output_dir):
        file_path = os.path.join(output_dir, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
        except Exception as e:
            print(f'Failed to delete {file_path}. Reason: {e}')

# Функция для запуска Docker-контейнера
def run_docker(img_path, output_dir):
    command = [
        "docker", "run", "--rm",
        "-v", f"{os.path.abspath(img_path)}:/input_image", 
        "-v", f"{os.path.abspath(output_dir)}:/output_dir", 
        "oemer_image", 
        "-o", "/output_dir", "/input_image"
    ]
    print(command)
    docker_process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = docker_process.communicate()
    if stderr:
        print(f"Error: {stderr.decode('utf-8')}")
    return docker_process

# Функция для распределения изображений по процессам и запуска потоков
def round_robin_runner():
    print(process_states)
    process_index = 0
    while True:
        img_path, output_dir = input_queue.get()
        assigned = False

        while not assigned:
            with lock:
                if not process_states[process_index]:
                    process_states[process_index] = True
                    threading.Thread(target=process_runner, args=(img_path, output_dir, process_index)).start()
                    assigned = True
                    print(process_states)
                else:
                    process_index = (process_index + 1) % len(process_states)
                    if process_index == 0 and all(process_states):
                        print("Все процессы сейчас заняты.")
                        break
        if assigned:
            process_index = (process_index + 1) % len(process_states)

# Функция для запуска процесса и обновления состояния
def process_runner(img_path, output_dir, index):
    clear_output_dir(output_dir)  # Очистка выходной папки перед запуском контейнера
    run_docker(img_path, output_dir)
    with lock:
        process_states[index] = False

# Запускаем функцию распределения процессов в отдельном потоке
threading.Thread(target=round_robin_runner, daemon=True).start()

bot.polling(non_stop=True)
