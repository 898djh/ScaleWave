import subprocess
import json


def run_command(command):
    result = subprocess.run(command, capture_output=True, text=True, shell=True)
    if result.returncode != 0:
        return None
    return result.stdout


def list_knative_services():
    # Execute 'kn service list' command with JSON output format
    command = "kn service list -o json"
    output = run_command(command)
    if output:
        # Parse the JSON output
        services = json.loads(output)
        service_list = []
        # Iterate through the services and print their details
        for service in services.get('items', []):
            service_name = service['metadata']['name']
            service_list.append(service_name)
        return service_list


def list_revisions():
    # List all revisions in JSON format
    revisions_output = run_command("kn revision list -o json")
    revision_list = []
    if revisions_output:
        revisions = json.loads(revisions_output)
        for revision in revisions.get('items', []):
            print(f"Revision: {revision['metadata']['name']}")
            revision_list.append(revision['metadata']['name'])
        return revision_list


def list_services_traffic_split():
    # List all services in JSON format
    services_output = run_command("kn service list -o json")
    if services_output:
        services = json.loads(services_output)
        revision_traffic = dict()
        for service in services.get('items', []):
            # Get the traffic split information
            traffic = service.get('status', {}).get('traffic', [])
            for route in traffic:
                revision_traffic[route.get('revisionName', 'Latest')] = route.get('percent', 0)
        return revision_traffic


def get_revisions_with_traffic_split(service_name):
    # List all revisions with their traffic split percentages for a given service
    services_output = run_command("kn service list -o json")
    if services_output:
        services = json.loads(services_output)
        revisions_traffic = dict()
        for service in services.get('items', []):
            if service['metadata'].get('name') == service_name:
                # Get the traffic split information
                traffic = service.get('status', {}).get('traffic', [])
                for route in traffic:
                    revisions_traffic[route.get('revisionName', 'Latest')] = route.get('percent', 0)
        return revisions_traffic


if __name__ == "__main__":
    print("Listing Knative services:")
    print(list_knative_services())

    for service in list_knative_services():
        print(get_revisions_with_traffic_split(service))

    print("Listing all revisions:")
    print(list_revisions())
    
    print("\nListing all services with traffic split:")
    print(list_services_traffic_split())
