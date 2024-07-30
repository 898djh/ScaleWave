import subprocess
import json


def run_command(command):
    result = subprocess.run(command, capture_output=True, text=True, shell=True)
    if result.returncode != 0:
        #print(f"Error running command '{' '.join(command)}': {result.stderr}")
        return None
    return result.stdout


def get_services_and_revisions():
    # List all revisions with their traffic split percentages for a given service
    services_output = run_command("kn service list -o json")
    if services_output:
        services = json.loads(services_output)
        service_list = []
        for service in services.get('items', []):
            service_revisions = {'service': None, 'revisions': []}
            # Get the service name
            service_name = service.get('metadata').get('name')
            if service_name:
                # Get the traffic split information
                service_revisions['service_name'] = service_name
                traffic = service.get('status', {}).get('traffic', [])
                for route in traffic:
                    service_revisions['revisions'].append({route.get('revisionName'): route.get('percent')})
            service_list.append(service_revisions)
        return service_list


def get_node_ready_status(node_name):
    # Command to get the list of nodes in JSON format
    cmd = ['kubectl', 'get', 'nodes', '-o', 'json']

    try:
        # Execute the command
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        nodes_info = json.loads(result.stdout)

        # Parse the status of each node
        for node in nodes_info['items']:
            name = node['metadata']['name']
            if name == node_name:
                for condition in node['status']['conditions']:
                    # Check if the condition type is 'Ready'
                    if condition['type'] == 'Ready':
                        status = condition['status']
                        return status
    except subprocess.CalledProcessError as e:
        return


def check_pod_status(namespace, service):
    cmd = [
        'kubectl', 'get', 'pods',
        '--namespace', namespace,
    ]

    try:
        # Execute the kubectl command
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        all_service_statuses = []
        # Process and print the output
        lines = result.stdout.splitlines()
        for line in lines[1:]:  # Skip the header row
            if service in line:
                columns = line.split()
                name = columns[0]
                status = columns[2]  # Assuming standard output; this index might need adjustment
                all_service_statuses.append(status)
        if "Running" in all_service_statuses:
            return "Running"
    except subprocess.CalledProcessError as e:
        print(f"Failed to get pods status: {e.stderr}")


if __name__ == "__main__":
    
    print("\nListing all services with traffic split:")
    print(get_services_and_revisions())
