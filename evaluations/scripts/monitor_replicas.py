# Monitoring replicas for standalone based services

import subprocess
import csv
import time
from datetime import datetime


def get_replica_count(service_name, namespace='default'):
    try:
        # Run kubectl command to get the replica count
        command = f"kubectl get deployment {service_name} -n {namespace} -o jsonpath='{{.spec.replicas}}'"
        # For OpenShift, you can use: command = f"kn service list {service_name} -n {namespace} -o jsonpath='{{.metadata.replicas}}'"
        
        replica_count = subprocess.check_output(command, shell=True, text=True).strip()

        return int(replica_count)
    except subprocess.CalledProcessError as e:
        print(f"Error running kubectl command: {e}")
        return None


def write_to_csv(file_path, timestamp, service_name, replica_count):
    with open(file_path, mode='a', newline='') as file:
        writer = csv.writer(file)
        writer.writerow([timestamp, service_name, replica_count])


if __name__ == "__main__":
    service_name = "face-recognition-edge-00001-deployment" # Adjust service name as needed
    namespace = "default"
    csv_file_path = "replica_data"  # Adjust the file path as needed

    print("Timestamp, Service Name, Replica Count")

    while True:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        replica_count = get_replica_count(service_name, namespace)

        if replica_count is not None:
            print(f"{timestamp}, {service_name}, {replica_count}")
            write_to_csv(csv_file_path, timestamp, service_name, replica_count)
        else:
            print(f"{timestamp}, {service_name}, Error retrieving replica count")

        time.sleep(1)  # Wait for 1 second before the next iteration
