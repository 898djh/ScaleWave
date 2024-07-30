# Monitor resource usage (GPU, CPU, memory, network, disk)

import csv
import time
import psutil
import GPUtil

# Function to initialize previous disk and network usage for calculating deltas
def init_prev_usage():
    disk_io = psutil.disk_io_counters()
    net_io = psutil.net_io_counters(pernic=True)
    prev_disk_read = disk_io.read_bytes
    prev_disk_write = disk_io.write_bytes
    prev_net = {nic: (io.bytes_sent, io.bytes_recv) for nic, io in net_io.items()}
    return prev_disk_read, prev_disk_write, prev_net

# Function to calculate and update disk and network usage
def calculate_usage(prev_disk_read, prev_disk_write, prev_net, interface='wlp0s20f3'):
    # Disk I/O
    disk_io = psutil.disk_io_counters()
    disk_read = disk_io.read_bytes - prev_disk_read
    disk_write = disk_io.write_bytes - prev_disk_write
    # Network I/O
    net_io = psutil.net_io_counters(pernic=True)
    if interface in net_io:
        net_upload = net_io[interface].bytes_sent - prev_net[interface][0]
        net_download = net_io[interface].bytes_recv - prev_net[interface][1]
    else:
        net_upload, net_download = 0, 0  # Default to 0 if interface not found
    # Update previous values for next calculation
    prev_disk_read = disk_io.read_bytes
    prev_disk_write = disk_io.write_bytes
    prev_net[interface] = (net_io[interface].bytes_sent, net_io[interface].bytes_recv)
    return disk_read, disk_write, net_upload, net_download, prev_disk_read, prev_disk_write, prev_net

# Initialize previous usage values
prev_disk_read, prev_disk_write, prev_net = init_prev_usage()

filename = "system_metrics.csv"
with open(filename, mode='w', newline='') as file:
    writer = csv.writer(file)
    writer.writerow(['Timestamp', 'CPU Usage (%)', 'Memory Usage (%)', 'Disk Read (bytes/s)', 'Disk Write (bytes/s)', 'Network Upload (bytes/s)', 'Network Download (bytes/s)', 'GPU Usage (%)', 'GPU Memory Used (MB)'])

    while True:
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
        cpu_usage = psutil.cpu_percent()
        memory_usage = psutil.virtual_memory().percent
        disk_read, disk_write, net_upload, net_download, prev_disk_read, prev_disk_write, prev_net = calculate_usage(prev_disk_read, prev_disk_write, prev_net)
        gpu_usage, gpu_memory_used = 0, 0  # Initialize GPU usage and memory used
        gpus = GPUtil.getGPUs()
        if gpus:
            gpu = gpus[0]  # Assuming monitoring the first GPU
            gpu_usage = gpu.load * 100  # Convert to percentage
            gpu_memory_used = gpu.memoryUsed
        
        writer.writerow([timestamp, cpu_usage, memory_usage, disk_read, 
                        disk_write, net_upload, net_download, gpu_usage, gpu_memory_used])
        time.sleep(1)
