# Monitoring replicas for ScaleWave enabled equivalence-based services

import subprocess
import csv
import time
from datetime import datetime
import json


def get_knative_service(service_name, namespace='default'):
    # Fetch details of a specific Knative service in the specified namespace
    cmd = f"kubectl get ksvc {service_name} -n {namespace} -o json"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode == 0:
        service = json.loads(result.stdout)
        return service
    else:
        print(f"Error fetching service {service_name} in namespace {namespace}: {result.stderr}")
        return None


def get_revision_traffic_and_replicas(service, namespace='default'):
    # Placeholder for storing revision details
    revision_details = []
    if service and 'status' in service and 'traffic' in service['status']:
        # Traffic distribution
        for traffic in service['status']['traffic']:
            revision_name = traffic['revisionName']
            percent = traffic.get('percent', 0)
            # Fetch replica count for this revision (using deployment as proxy for revision)
            # deployment_name = f"{service['metadata']['name']}-{revision_name}-deployment"
            deployment_cmd = f"kubectl get deployment {revision_name}-deployment -n {namespace} -o json"
            deployment_result = subprocess.run(deployment_cmd, shell=True, capture_output=True, text=True)
            if deployment_result.returncode == 0:
                deployment = json.loads(deployment_result.stdout)
                replica_count = deployment['spec']['replicas']
            else:
                replica_count = 'Unknown'
            # Append details
            revision_details.append((service['metadata']['name'], revision_name, replica_count, percent))
    return revision_details


def record_to_csv(data, filename='replica_data_oblique.csv'):
    with open(filename, mode='a', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(data)


def main(service_name, namespace='default'):
    # Write CSV header
    with open('knative_revision_traffic.csv', mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(['Timestamp', 'Service Name', 'Revision Name', 'Replica Count', 'Traffic Percentage'])

    while True:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        service = get_knative_service(service_name, namespace)
        if service:
            revision_traffic = get_revision_traffic_and_replicas(service, namespace)
            for service_name, revision_name, replica_count, traffic_percentage in revision_traffic:
                record_to_csv([timestamp, service_name, revision_name, replica_count, traffic_percentage])
        
        time.sleep(1)


if __name__ == "__main__":
    # Specify the name of the Knative service and namespace here
    service_name = 'face-recognition-oblique'
    namespace = 'default'
    main(service_name, namespace)
