import threading
import queue
import subprocess
import os
import shutil

# Создаем очередь для ввода пользователя
input_queue = queue.Queue()

# Список папок для вывода
output_dirs = ['output1', 'output2', 'output3']

# Убедитесь, что папки для вывода существуют
for output_dir in output_dirs:
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

# Состояние процессов (True, если процесс занят, иначе False)
process_states = [False, False, False]

# Блокировка для защиты доступа к process_states
lock = threading.Lock()

# Функция для очистки выходной папки
def clear_output_dir(output_dir):
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

# Функция для обработки ввода пользователя
def process_input():
    while True:
        img_path = input("Введите путь к изображению: ")
        input_queue.put(img_path)

# Функция для распределения изображений по процессам и запуска потоков
def round_robin_runner():
    print(process_states)
    process_index = 0
    while True:
        img_path = input_queue.get()
        assigned = False

        while not assigned:
            with lock:
                if not process_states[process_index]:
                    process_states[process_index] = True
                    threading.Thread(target=process_runner, args=(img_path, output_dirs[process_index], process_index)).start()
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

# Запускаем поток для обработки ввода пользователя
threading.Thread(target=process_input, daemon=True).start()

# Запускаем функцию распределения процессов
round_robin_runner()
