import subprocess

def get_network_capabilities(interface):
    try:
        output = subprocess.check_output(["lshw", "-class", "network"], stderr=subprocess.STDOUT)
        lines = output.decode().split('\n')
        capturing = False
        for line in lines:
            if interface in line:
                capturing = True
            if capturing:
                if 'capacity' in line:
                    return line.strip()
    except subprocess.CalledProcessError as e:
        return f"Failed to get network capabilities: {e}"
    except FileNotFoundError:
        return "lshw not found. Please install it."

# Example usage
capabilities = get_network_capabilities('wlp0s20f3')  # Replace 'eth0' with your interface name
print(capabilities)

