import subprocess
import json


def list_nodes_status():
    # Command to get the list of nodes in JSON format
    cmd = ['kubectl', 'get', 'nodes', '-o', 'json']

    try:
        # Execute the command
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        nodes_info = json.loads(result.stdout)

        print("Listing nodes with their statuses:")
        
        # Parse and print the status of each node
        for node in nodes_info['items']:
            name = node['metadata']['name']
            for condition in node['status']['conditions']:
                # Check if the condition type is 'Ready'
                if condition['type'] == 'Ready':
                    status = condition['status']
                    break
            print(f"Node: {name}, Ready: {status}")
    except subprocess.CalledProcessError as e:
        print(f"Failed to get nodes status: {e.stderr}")

if __name__ == "__main__":
    list_nodes_status()
