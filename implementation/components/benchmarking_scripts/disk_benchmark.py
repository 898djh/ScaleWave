import subprocess
import json


def run_fio_and_parse_output(fio_params):
    # Run fio with the specified parameters and JSON output format
    result = subprocess.run(['fio', '--output-format=json'] + fio_params, capture_output=True, text=True)

    # Load the JSON output
    fio_output = json.loads(result.stdout)

    # Extract metrics of interest
    metrics = {
        'read_iops': fio_output['jobs'][0]['read']['iops'],
        'write_iops': fio_output['jobs'][0]['write']['iops'],
        'read_throughput': fio_output['jobs'][0]['read']['bw'],
        'write_throughput': fio_output['jobs'][0]['write']['bw'],
        'read_latency': fio_output['jobs'][0]['read']['lat_ns']['mean'],
        'write_latency': fio_output['jobs'][0]['write']['lat_ns']['mean']
    }
    return metrics


# Define fio parameters for a write test
write_params = [
    '--name=write_test', '--ioengine=libaio', '--iodepth=32',
    '--rw=write', '--bs=4k', '--direct=1', '--size=1G', '--numjobs=1',
    '--runtime=60', '--group_reporting'
]

# Define fio parameters for a read test
read_params = [
    '--name=read_test', '--ioengine=libaio', '--iodepth=32',
    '--rw=read', '--bs=4k', '--direct=1', '--size=1G', '--numjobs=1',
    '--runtime=60', '--group_reporting'
]

# Run write test and parse output
write_metrics = run_fio_and_parse_output(write_params)
print("Write Test Metrics:", write_metrics)

# Run read test and parse output
read_metrics = run_fio_and_parse_output(read_params)
print("Read Test Metrics:", read_metrics)
