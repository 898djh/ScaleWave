import psutil
import time

def get_net_io():
    net_io = psutil.net_io_counters(pernic=True)
    return {nic: {"bytes_sent": stats.bytes_sent, "bytes_recv": stats.bytes_recv} for nic, stats in net_io.items()}

def calculate_bandwidth(sample_duration=1):
    # Get initial network IO
    start_counters = get_net_io()
    time.sleep(sample_duration)
    # Get network IO after a delay
    end_counters = get_net_io()

    # Calculate bandwidth
    bandwidth = {}
    for nic in start_counters:
        if nic in end_counters:
            sent = (end_counters[nic]["bytes_sent"] - start_counters[nic]["bytes_sent"]) / sample_duration
            received = (end_counters[nic]["bytes_recv"] - start_counters[nic]["bytes_recv"]) / sample_duration
            bandwidth[nic] = {"upload_bps": sent, "download_bps": received}
    return bandwidth

# Sample usage
if __name__ == "__main__":
    # Measure bandwidth for each network interface over a period of 1 second
    bandwidth = calculate_bandwidth(100)
    for nic, stats in bandwidth.items():
        print(f"{nic} - Upload: {stats['upload_bps']/1024:.2f} KB/s, Download: {stats['download_bps']/1024:.2f} KB/s")
