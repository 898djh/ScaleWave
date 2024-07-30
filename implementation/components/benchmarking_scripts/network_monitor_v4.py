import subprocess
import json

def run_iperf3(server_ip, port=5201):
    # Run iperf3 in client mode, with JSON output for easy parsing
    command = ['iperf3', '-c', server_ip, '-p', str(port), '-J']
    result = subprocess.run(command, capture_output=True, text=True)
    
    if result.returncode != 0:
        print("Error running iperf3:", result.stderr)
        return None

    # Parse the JSON output
    try:
        output = json.loads(result.stdout)
        
        # Extract upload and download rates
        upload_rate_mbps = output['end']['sum_sent']['bits_per_second'] / 1e6
        download_rate_mbps = output['end']['sum_received']['bits_per_second'] / 1e6
        
        return upload_rate_mbps, download_rate_mbps
    except json.JSONDecodeError:
        print("Could not parse iperf3 output as JSON.")
        return None

# Example usage - replace '<server_ip>' with the actual server IP or hostname
server_ip = 'speedtest.chi11.us.leaseweb.net'	# '192.168.1.195' (if local)
upload_rate, download_rate = run_iperf3(server_ip)
if upload_rate and download_rate:
    print(f"Upload Rate: {upload_rate:.2f} Mbps")
    print(f"Download Rate: {download_rate:.2f} Mbps")
