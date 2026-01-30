import argparse
import multiprocessing
import threading
import time
import csv
import requests
import os
import random
from datetime import datetime


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--manager_node_ip", help="IP of the manager node")
    p.add_argument("--route_url", help="Route URL obtained in Step 5")
    p.add_argument("--c", help="Concurrency value the current setup is running")
    return p.parse_args()

args = parse_args()
manager_ip = str(args.manager_node_ip).strip()
route_headers = str(args.route_url).strip().replace("http://", "").replace("https://", "").strip()
concurrency_val = str(args.c)


def read_inter_arrival_times(file_path):
    with open(file_path, newline='') as csvfile:
        reader = csv.DictReader(csvfile)
        # data = []
        # for row in reader:
        #     if float(row['inter_arrival_time']) <= 200:
        #         data.append(0.1 * float(row['inter_arrival_time']))
        #     elif 201 < float(row['inter_arrival_time']) <= 400:
        #         data.append(0.07 * float(row['inter_arrival_time']))
        #     elif 401 < float(row['inter_arrival_time']) <= 600:
        #         data.append(0.045 * float(row['inter_arrival_time']))
        #     elif 601 < float(row['inter_arrival_time']) <= 800:
        #         data.append(0.02 * float(row['inter_arrival_time']))
        #     else:
        #         data.append(0.01 * float(row['inter_arrival_time']))
        return [float(row['inter_arrival_time']) for row in reader]
        # return data


def send_request(user_id, metrics):
    try:
        request_start_time = datetime.now()
        # Simulate actual request
        filenames = ['two_people.jpg', 'ob.jpg', 'many_people.jpg', 'obama_small.jpg']
        filename = random.choice(filenames)
        headers = {'Host': f'{route_headers}'}  # Replace with your host headers
        my_img = {'image': open(filename, 'rb')}
        response = requests.post(f"http://{manager_ip}/recognize", headers=headers, files=my_img)  # Replace with your actual target URL
        status_code = response.status_code
        request_end_time = datetime.now()
        print(response.json())
    except Exception as e:
        print(f"Error for user {user_id}: {str(e)}")
        status_code = 500  # Simulate a failed request status code
        request_end_time = datetime.now()
    
    latency = (request_end_time - request_start_time).total_seconds()
    
    # Recording the request metrics
    metrics.append({
        "timestamp": request_start_time.strftime("%Y-%m-%d %H:%M:%S"),
        "user_id": user_id,
        "status_code": status_code,
        "latency": latency,
    })


def process_user(user_id, file_path, metrics):
    inter_arrival_times = read_inter_arrival_times(file_path)
    
    # Create threads for parallel execution
    threads = []
    for inter_arrival_time in inter_arrival_times:
        thread = threading.Thread(target=send_request, args=(user_id, metrics))
        thread.start()
        threads.append(thread)
        time.sleep(inter_arrival_time)  # Sleep between starting threads

    # Wait for all threads to finish
    for thread in threads:
        thread.join()


def write_metrics_to_csv(metrics, output_file):
    with open(output_file, 'w', newline='') as csvfile:
        fieldnames = ['timestamp', 'user_id', 'status_code', 'latency']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for metric in metrics:
            writer.writerow(metric)


if __name__ == "__main__":
    folder_path = os.path.join(os.getcwd(), "trace")
    output_file = f'results/output_metrics_c{concurrency_val}.csv'
    metrics = multiprocessing.Manager().list()

    processes = []

    # Process each CSV file in the directory
    for file_name in os.listdir(folder_path):
        if file_name.endswith('.csv'):
            user_id = file_name.replace(".csv", "")  # Assuming file name format "user_id.csv"
            file_path = os.path.join(folder_path, file_name)
            process = multiprocessing.Process(target=process_user, args=(user_id, file_path, metrics))
            processes.append(process)
            process.start()

    # Wait for all processes to finish
    for process in processes:
        process.join()

    # Write collected metrics to CSV
    write_metrics_to_csv(list(metrics), output_file)
