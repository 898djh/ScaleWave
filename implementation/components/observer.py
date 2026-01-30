# imports
import argparse
import os
import time
import subprocess

from prometheus_api_client import PrometheusConnect

import db_client
from utils import get_services_and_revisions

# Prometheus URL
prometheus_url = "http://localhost:9090"

# Connect to Prometheus
prometheus = PrometheusConnect(url=prometheus_url)

# Connect to Redis
redis_conn = db_client.connect_to_redis()

# Observer frequency (in seconds)
observer_frequency = '1m'

# Timer triggers in seconds
panic_timer = 6
stable_timer = 30


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--manager_node_ip", help="IP of the manager node")
    p.add_argument("--c", help="Current concurrency per pod")
    return p.parse_args()


def parse_promql_results_to_cluster_metrics(data):
    if data:
        return float(data[0]['value'][1])
    else:
        return 0


def parse_promql_results_to_eqv_metrics(component, data, equivalent_services):
    if not data:
        return None
    eqv_service_metrics = {equivalent_service: 0 for equivalent_service in equivalent_services}
    for result in data:
        for equivalent_service in equivalent_services:
            if result['metric'][component].startswith(equivalent_service):
                if component == 'deployment':
                    eqv_service_metrics[equivalent_service] += int(result['value'][1])
                else:
                    eqv_service_metrics[equivalent_service] += float(result['value'][1])
    return eqv_service_metrics


def monitor_cluster_level_resource_availability(master_instance):
    """ Fetches cluster level resource availability metrics """

    # available cpu in millicores (m)
    cpu_query = f'(sum(rate(node_cpu_seconds_total{{mode="idle", instance!="{master_instance}"}}[{observer_frequency}])) ) * 1000'
    # available memory in Mebibytes (MiB)
    memory_query = f'sum(sum(node_memory_MemAvailable_bytes{{instance!="{master_instance}"}})/1048576)'
    # available disk capacity in Mebibytes (MiB)
    disk_query = f'sum(node_filesystem_avail_bytes{{instance!="{master_instance}"}}) / 1048576'

    # available disk read capacity in Mebibytes (MiB)
    disk_read_query = f'sum(rate(node_disk_read_bytes_total{{instance!="{master_instance}"}}[{observer_frequency}])) / 1048576'
    # available disk write capacity in Mebibytes (MiB)
    disk_write_query = f'sum(rate(node_disk_written_bytes_total{{instance!="{master_instance}"}}[{observer_frequency}])) / 1048576'

    # available network downlink bandwidth in Megabits/second (Mbps)
    network_receive_query = f'sum(rate(node_network_receive_bytes_total{{instance!="{master_instance}", device!~"lo|veth.*|docker.*|flannel.*|cali.*|cbr.*"}}[{observer_frequency}])) * 8 / 1048576'
    # available network uplink bandwidth in Megabits/second (Mbps)
    network_transmit_query = f'sum(rate(node_network_transmit_bytes_total{{instance!="{master_instance}", device!~"lo|veth.*|docker.*|flannel.*|cali.*|cbr.*"}}[{observer_frequency}])) * 8 / 1048576'

    cpu_result = parse_promql_results_to_cluster_metrics(prometheus.custom_query(cpu_query))
    memory_result = parse_promql_results_to_cluster_metrics(prometheus.custom_query(memory_query))
    disk_result = parse_promql_results_to_cluster_metrics(prometheus.custom_query(disk_query))
    disk_read_result = parse_promql_results_to_cluster_metrics(prometheus.custom_query(disk_read_query))
    disk_write_result = parse_promql_results_to_cluster_metrics(prometheus.custom_query(disk_write_query))
    network_receive_result = parse_promql_results_to_cluster_metrics(prometheus.custom_query(network_receive_query))
    network_transmit_result = parse_promql_results_to_cluster_metrics(prometheus.custom_query(network_transmit_query))

    # TODO: Run this as a separate process in certain time durations and report it in memcache
    # from network_benchmark import perform_speed_test
    # max_downlink, max_uplink = perform_speed_test()

    max_resource_capacity = db_client.retrieve_json_data(redis_conn, "max_resource_benchmarks")

    if not max_resource_capacity:
        max_disk_read, max_disk_write = 2909.1, 556.9
        max_network_downlink, max_network_uplink = 300.59, 350.56
    else:
        max_disk_read = max_resource_capacity.get('max_disk_read', 2909.1)
        max_disk_write = max_resource_capacity.get('max_disk_write', 556.9)
        max_network_downlink = max_resource_capacity.get('max_network_downlink', 300.59)
        max_network_uplink = max_resource_capacity.get('max_network_uplink', 350.56)

    return {
        "cpu": cpu_result,
        "memory": memory_result,
        # "disk": disk_result,
        "disk_read": max_disk_read - disk_read_result,
        "disk_write": max_disk_write - disk_write_result,
        "network_downlink": max_network_downlink - network_receive_result,
        "network_uplink": max_network_uplink - network_transmit_result
    }


def monitor_pod_level_resource_utilization(service_name, equivalent_services):
    """ Fetches container level resource usage metrics """

    # cpu usage in millicores (m)
    cpu_query = f'sum(rate(container_cpu_usage_seconds_total{{pod=~"{service_name}.*"}}[{observer_frequency}])) by (pod) * 1000'
    
    # memory usage in Mebibytes (MiB)
    memory_query = f'sum(container_memory_usage_bytes{{pod=~"{service_name}.*"}}) by (pod) / 1048576'
    
    # disk read in Mebibytes (MiB)
    disk_read_query = f'sum(rate(container_fs_reads_bytes_total{{pod=~"{service_name}.*"}}[{observer_frequency}])) by (pod) / 1048576'
    
    # disk write in Mebibytes (MiB)
    disk_write_query = f'sum(rate(container_fs_writes_bytes_total{{pod=~"{service_name}.*"}}[{observer_frequency}])) by (pod) / 1048576'
    
    # network downlink usage in Megabits/second (Mbps)
    network_receive_query = f'sum(rate(container_network_receive_bytes_total{{pod=~"{service_name}.*"}}[{observer_frequency}])) by (pod) * 8 / 1048576'
    
    # network uplink usage in Megabits/second (Mbps)
    network_transmit_query = f'sum(rate(container_network_transmit_bytes_total{{pod=~"{service_name}.*"}}[{observer_frequency}])) by (pod) * 8 / 1048576'

    cpu_result = parse_promql_results_to_eqv_metrics('pod', prometheus.custom_query(cpu_query), equivalent_services)
    memory_result = parse_promql_results_to_eqv_metrics('pod', prometheus.custom_query(memory_query), equivalent_services)
    disk_read_result = parse_promql_results_to_eqv_metrics('pod', prometheus.custom_query(disk_read_query), equivalent_services)
    disk_write_result = parse_promql_results_to_eqv_metrics('pod', prometheus.custom_query(disk_write_query), equivalent_services)
    network_receive_result = parse_promql_results_to_eqv_metrics('pod', prometheus.custom_query(network_receive_query), equivalent_services)
    network_transmit_result = parse_promql_results_to_eqv_metrics('pod', prometheus.custom_query(network_transmit_query), equivalent_services)

    return {
        "service_name": service_name,
        "cpu_usage": cpu_result,
        "memory_usage": memory_result,
        "disk_read": disk_read_result,
        "disk_write": disk_write_result,
        "network_downlink": network_receive_result,
        "network_uplink": network_transmit_result
    }


def monitor_additional_accelerator_resources(service_name, equivalent_services):
    gpu_metrics = {}
    gpu_service_revision_number = 'oblique-00004'

    for equivalent_service in equivalent_services:
        if 'oblique-00004' in equivalent_service:   # parse by gpu tag in equivalent service name (others as FPGA can be added as such)
            gpu_util_query = f'max(max_over_time(jetson_gpu_utilization[{observer_frequency}]))'
            # gpu_mem_util_query = f'sum(rate(jetson_gpu_memory_utilization[{observer_frequency}]))'
            # gpu_util_query = 'jetson_gpu_utilization'
            # gpu_mem_util_query = 'jetson_gpu_memory_utilization'

            gpu_util_result = parse_promql_results_to_cluster_metrics(prometheus.custom_query(gpu_util_query))
            # gpu_mem_util_result = parse_promql_results_to_cluster_metrics(prometheus.custom_query(gpu_mem_util_query))
            gpu_avail = 100 - gpu_util_result
            # gpu_mem_avail = 100 - gpu_mem_util_result
            # gpu_metrics['available_gpu_resource'] = {'gpu': gpu_avail, 'gpu_mem': gpu_mem_avail}
            gpu_metrics['available_gpu_resource'] = {'gpu': gpu_avail}
        else:
            # gpu_util_result, gpu_mem_util_result = 0, 0
            gpu_util_result = 0
        
        # gpu_metrics[equivalent_service] = {'gpu_util': gpu_util_result, 'gpu_mem': gpu_mem_util_result}
        gpu_metrics[equivalent_service] = {'gpu_util': gpu_util_result}
    
    if 'available_gpu_resource' not in gpu_metrics.keys():
        # gpu_metrics['available_gpu_resource'] = {'gpu': 100, 'gpu_mem': 100}
        gpu_metrics['available_gpu_resource'] = {'gpu': 100}
    
    return gpu_metrics


def monitor_current_eqv_service_replicas(service_name, equivalent_services):
    replica_count_query = f'''sum(kube_deployment_spec_replicas{{deployment=~"{service_name}.*", 
                                    job="kube-state-metrics"}}) by (deployment)'''

    current_replica_count = parse_promql_results_to_eqv_metrics('deployment', 
                                                                prometheus.custom_query(replica_count_query), 
                                                                equivalent_services)
                                                         
    print(f"Current replica for {service_name}: ", current_replica_count)
    return current_replica_count


def monitor_current_eqv_service_throughput(service_name):
    throughput_query = f'''sum(revision_request_count{{configuration_name="{service_name}", response_code_class="2xx"}}) 
                            by (revision_name) / sum(revision_request_latencies_sum{{configuration_name="{service_name}", 
                            response_code_class="2xx"}}) by (revision_name)'''

    successful_requests_query = f'''sum(rate(revision_request_count{{configuration_name="{service_name}", 
                                    response_code_class="2xx"}}[{observer_frequency}])) by (revision_name) * 60'''
    
    total_requests_query = f'''sum(rate(revision_request_count{{configuration_name="{service_name}"}}
                                [{observer_frequency}])) by (revision_name) * 60'''
    
    request_latencies_query = f'''(sum(rate(revision_request_latencies_sum{{configuration_name="{service_name}", 
                                    response_code_class="2xx"}}[{observer_frequency}])) by (revision_name) / 1000) * 60'''
    # added activator latencies query
    activator_latencies_query = f'''(sum(rate(activator_request_latencies_sum{{configuration_name="{service_name}", 
                                    response_code_class="2xx"}}[{observer_frequency}])) by (revision_name) / 1000) * 60'''
    
    # queue depth
    # queue_depth_query = f'''sum(revision_queue_depth{{configuration_name="{service_name}"}}) by (revision_name)'''

    activator_concurrency_query = f'''sum(activator_request_concurrency{{configuration_name="{service_name}"}}) by (revision_name)'''
    autoscaler_concurrency_per_pod_query = f'''sum(autoscaler_target_concurrency_per_pod{{configuration_name="{service_name}"}}) by (revision_name)'''

    current_throughput = parse_promql_results_to_eqv_metrics('revision_name', 
                                                            prometheus.custom_query(throughput_query), 
                                                            equivalent_services)

    current_successful_requests = parse_promql_results_to_eqv_metrics('revision_name',
                                                                    prometheus.custom_query(successful_requests_query), 
                                                                    equivalent_services)

    current_total_requests = parse_promql_results_to_eqv_metrics('revision_name',
                                                                prometheus.custom_query(total_requests_query), 
                                                                equivalent_services)

    current_request_latencies = parse_promql_results_to_eqv_metrics('revision_name', 
                                                                    prometheus.custom_query(request_latencies_query), 
                                                                    equivalent_services)

    # get activator latencies (accounts the cold-start)
    current_activator_latencies = parse_promql_results_to_eqv_metrics('revision_name', 
                                                                    prometheus.custom_query(activator_latencies_query), 
                                                                    equivalent_services)
    # get queue depth
    # current_queue_length = parse_promql_results_to_eqv_metrics('revision_name', 
    #                                                             prometheus.custom_query(queue_depth_query), 
    #                                                             equivalent_services)

    current_concurrent_request = parse_promql_results_to_eqv_metrics('revision_name', 
                                                                prometheus.custom_query(activator_concurrency_query), 
                                                                equivalent_services)

    target_concurrency_per_pod = parse_promql_results_to_eqv_metrics('revision_name', 
                                                                prometheus.custom_query(autoscaler_concurrency_per_pod_query), 
                                                                equivalent_services)

    print(f"Current throughput for {service_name}: ", current_throughput)
    
    if current_activator_latencies is None:
        current_activator_latencies = {}
    if current_concurrent_request is None:
        current_concurrent_request = {}
    if target_concurrency_per_pod is None:
        target_concurrency_per_pod = {}
    
    current_revisions = list(current_throughput.keys())
    for rev in current_revisions:
        current_activator_latencies.setdefault(rev, 0)
        current_concurrent_request.setdefault(rev, 0)
        target_concurrency_per_pod.setdefault(rev, concurrency_setting)

    throughput_related_metrics = {
        "current_throughput": current_throughput,
        "current_successful_requests": current_successful_requests, 
        "current_total_requests": current_total_requests,
        "current_request_latencies": current_request_latencies,
        "current_activator_latencies": current_activator_latencies,
        # "current_queue_length": current_queue_length,
        "current_concurrent_request": current_concurrent_request,
        "target_concurrency_per_pod": target_concurrency_per_pod
    }

    return throughput_related_metrics

HOME_DIR = os.environ.get("HOME")
args = parse_args()
manager_ip = str(args.manager_node_ip).strip()
concurrency_setting = int(str(args.c).strip())

while True:
    try:
        all_services = get_services_and_revisions()
        mode = 'stable'

        for service in all_services:
            # run in parallel
            master_instance = f'{manager_ip}:9100'  # master node IP
            service_name = service['service_name']
            equivalent_services = []

            for revision in service['revisions']:
                equivalent_services.extend(revision.keys())
            print(equivalent_services)
            
            eqv_services_current_replicas = monitor_current_eqv_service_replicas(service_name, equivalent_services)
            print("Replica: ", eqv_services_current_replicas)
            
            if list(eqv_services_current_replicas.values()) != [0] * len(eqv_services_current_replicas.keys()):
                pod_level_eqv_service_metrics = monitor_pod_level_resource_utilization(service_name, equivalent_services)
                print("Pod-level Eqv Services Resource Metrics", ":", pod_level_eqv_service_metrics)
                
                service_level_gpu_metrics = monitor_additional_accelerator_resources(service_name, equivalent_services)
                print(f"GPU metrics for {service_name}: ", service_level_gpu_metrics)
                
                eqv_services_current_replicas = monitor_current_eqv_service_replicas(service_name, equivalent_services)
                print("Replica: ", eqv_services_current_replicas)
                
                cluster_level_resource_availability_metrics = monitor_cluster_level_resource_availability(master_instance)
                cluster_level_resource_availability_metrics['gpu'] = service_level_gpu_metrics['available_gpu_resource']['gpu']
                # cluster_level_resource_availability_metrics['gpu_mem'] = service_level_gpu_metrics['available_gpu_resource']['gpu_mem']
                print("Cluster-level resource metrics: ", cluster_level_resource_availability_metrics)
                
                throughput_metrics = monitor_current_eqv_service_throughput(service_name)
                # if list(eqv_services_current_replicas.values()) != [0] * len(eqv_services_current_replicas.keys()):
                print("------ Throughput Metrics----------", throughput_metrics, pod_level_eqv_service_metrics)
                if None not in throughput_metrics.values() and None not in pod_level_eqv_service_metrics.values():
                    eqv_service_throughput = throughput_metrics['current_throughput']
                    eqv_service_requests = throughput_metrics['current_successful_requests']
                    eqv_service_total_requests = throughput_metrics['current_total_requests']
                    eqv_service_latencies = throughput_metrics['current_request_latencies']
                    eqv_service_activator_latencies = throughput_metrics['current_activator_latencies']
                    # eqv_service_queue_length = throughput_metrics['current_queue_length']
                    eqv_service_concurrent_requests = throughput_metrics['current_concurrent_request']
                    eqv_service_target_concurrency_per_pod = throughput_metrics['target_concurrency_per_pod']
                    print("Eqv services throughput: ", eqv_service_throughput, 
                            eqv_service_requests, eqv_service_total_requests, 
                            eqv_service_latencies, eqv_service_activator_latencies,
                            # eqv_service_queue_length, 
                            eqv_service_concurrent_requests, eqv_service_target_concurrency_per_pod)
                    
                    db_client.store_json_data(redis_conn, "available_cluster_resources", 
                                            cluster_level_resource_availability_metrics)
                    eqv_service_metrics = {}
                    throughput_now = 0
                    service_history = db_client.retrieve_json_data(redis_conn, service_name)

                    current_requests = db_client.retrieve_json_data(redis_conn, f'{service_name}_requests')
                    if current_requests is not None:
                        prev_requests = current_requests.copy()
                    else:
                        prev_requests = {'total': 0}

                    if not service_history:
                        service_history = dict()

                    if not current_requests:
                        current_requests = {'total': 0}

                    total_concurrent_requests = 0
                    for equivalent_service in equivalent_services:
                        eq_replica_count = eqv_services_current_replicas[equivalent_service]
                        
                        if eq_replica_count == 0:
                            continue
                        
                        eq_target_concurrency_per_pod = eqv_service_target_concurrency_per_pod[equivalent_service]

                        try:
                            eq_success_rate = eqv_service_requests[equivalent_service] / eqv_service_total_requests[equivalent_service]
                        except ZeroDivisionError:
                            eq_success_rate = 0
                        # eq_queue_length = eqv_service_queue_length[equivalent_service]
                        # if eq_queue_length == 0 or eq_queue_length == 0.0:
                            # eq_queue_length = 1
                        
                        eq_concurrency = eqv_service_concurrent_requests[equivalent_service]
                        if eq_concurrency == 0 or eq_concurrency == 0.0:
                            eq_concurrency = 1

                        try:
                            eq_normalized_throughput = (eqv_service_requests[equivalent_service] / 
                                                    (eqv_service_latencies[equivalent_service] + 
                                                    eqv_service_activator_latencies[equivalent_service]))
                            # eq_normalized_throughput /= eq_concurrency
                            # eq_normalized_throughput /= eq_queue_length
                            # eq_normalized_throughput /= (eq_concurrency/(eq_replica_count*49))
                            # eq_normalized_throughput *= eq_success_rate
                        except ZeroDivisionError:
                            eq_normalized_throughput = 0
                        
                        try:
                            eq_latency_per_request = ((eqv_service_latencies[equivalent_service] + 
                                                    eqv_service_activator_latencies[equivalent_service])/
                                                    eqv_service_requests[equivalent_service])
                        except ZeroDivisionError:
                            eq_latency_per_request = 0
                        
                        # requests_in_flight = eqv_service_total_requests[equivalent_service] + eqv_service_queue_length[equivalent_service]
                        requests_in_flight = eqv_service_concurrent_requests[equivalent_service]
                        current_requests[equivalent_service] = requests_in_flight
                        # current_requests['total'] += requests_in_flight
                        total_concurrent_requests += requests_in_flight
                        
                        # not updating the cache if throughput is reported zero
                        if eq_normalized_throughput <= 0:
                            continue
                        
                        eq_normalized_throughput = max(eq_normalized_throughput, 0.00000000000001)/eq_replica_count
                        eq_throughput = max(eqv_service_throughput[equivalent_service], 0.00000000000001)/eq_replica_count
                        eq_successful_requests = eqv_service_requests[equivalent_service]/eq_replica_count
                        eq_latency = (eqv_service_latencies[equivalent_service] + eqv_service_activator_latencies[equivalent_service])/eq_replica_count
                        eq_latency_per_request_replica = max(eq_latency_per_request, 0.001)/eq_replica_count
                        eq_queued_requests = eqv_service_concurrent_requests[equivalent_service]
                        
                        eqv_service_metrics[equivalent_service] = {'throughput': eq_throughput,
                                                    'normalized_throughput': eq_normalized_throughput,
                                                    'successful_requests': eq_successful_requests,
                                                    'latency': eq_latency,
                                                    'latency_per_request': eq_latency_per_request_replica,
                                                    'queued_requests': eq_queued_requests,
                                                    'target_concurrency_per_pod': eq_target_concurrency_per_pod,
                                                    'cpu': pod_level_eqv_service_metrics['cpu_usage'][equivalent_service]/eq_replica_count,
                                                    'memory': pod_level_eqv_service_metrics['memory_usage'][equivalent_service]/eq_replica_count,
                                                    'disk_read': pod_level_eqv_service_metrics['disk_read'][equivalent_service]/eq_replica_count,
                                                    'disk_write': pod_level_eqv_service_metrics['disk_write'][equivalent_service]/eq_replica_count,
                                                    'network_downlink': pod_level_eqv_service_metrics['network_downlink'][equivalent_service]/eq_replica_count,
                                                    'network_uplink': pod_level_eqv_service_metrics['network_uplink'][equivalent_service]/eq_replica_count,
                                                    'gpu': service_level_gpu_metrics[equivalent_service]['gpu_util']/eq_replica_count,
                                                    # 'gpu_mem': service_level_gpu_metrics[equivalent_service]['gpu_mem'],
                                                    'current_replica': eq_replica_count}
                        
                        service_history[equivalent_service] = eqv_service_metrics[equivalent_service]
                        # throughput_now += eq_throughput
                        throughput_now += eq_normalized_throughput

                    # eqv_service_metrics['throughput_now'] = throughput_now    ##### check if required later ########
                    current_requests['total'] = total_concurrent_requests
                    print("Current State: ", eqv_service_metrics)

                    db_client.store_json_data(redis_conn, service_name, service_history)
                    db_client.store_json_data(redis_conn, f'{service_name}_requests', current_requests)
                    throughput_prev = redis_conn.get(f"{service_name}_throughput_prev")
                    # print("thr..", throughput_now, throughput_prev)
                    
                    if not throughput_prev:
                        throughput_prev = float(throughput_now)
                    else:
                        throughput_prev = float(throughput_prev)
                    
                    # if throughput_now > throughput_prev:
                    redis_conn.set(f"{service_name}_throughput_prev", throughput_now)

                    # add timer trigger
                    print(f"Prev Perf: {throughput_now}; Current Perf: {throughput_prev}")
                    #if throughput_now < throughput_prev:
                    EPS = 1e-9
                    if throughput_prev > EPS and throughput_now <= throughput_prev * 0.95:
                        # optimize traffic distribution
                        running_service_optimizers = db_client.retrieve_json_data(redis_conn, f"{service_name}_optimizer_process")
                        if not running_service_optimizers:
                            running_service_optimizers = []
                        print("---------------Trigerring Optimizer and Traffic Recomputations---------------")
                        process = subprocess.Popen([f'{HOME_DIR}/swenv/bin/python', f'{HOME_DIR}/ScaleWave/implementation/components/optimizer.py', service_name])
                        # Set the PID of the process
                        running_service_optimizers.append(process.pid)
                        
                        # store to cache
                        db_client.store_json_data(redis_conn, f"{service_name}_optimizer_process", running_service_optimizers)
                        time.sleep(4)
                    
                    if current_requests['total'] >= 1.5*prev_requests['total']:
                        mode = 'panic'
        
        if mode == 'panic':
            time.sleep(panic_timer)
        else:
            time.sleep(stable_timer)
    except Exception:
        continue

# while True:
#     try:
#         for service in services:
#             current_replica_count[service] = int(get_current_replicas(service))
#         # Fetch metrics for each Knative service
#         #knative_services = ["ob-face-recog-"]  # Replace with your actual Knative service names
#         #for service_name in knative_services:
#         container_metrics = fetch_container_metrics("ob-face-recog-")
#         print("Container Metrics for", ":", container_metrics)
#         print("\n")

#         # Fetch overall node metrics
#         cluster_nodes_metrics = fetch_cluster_nodes_metrics()
#         #cluster_metrics = {}
#         #for metrics in cluster_nodes_metrics.values():
#         #    print(cluster_nodes_metrics.values())
#         #    if cluster_metrics.get(metrics[0]['metric']['instance']):
#         #        cluster_metrics[metrics[0]['metric']['instance']].append(metrics[0]['value'][1])
#         #    else:
#         #        cluster_metrics[metrics[0]['metric']['instance']] = [metrics[0]['value'][1]]
#         print("Cluster Node Metrics:", cluster_nodes_metrics)
#         #print("Node Metrics: ", cluster_metrics)
        

#         print("\n")

#         cpu = container_metrics['cpu_usage']
#         mem = container_metrics['memory_usage']

#         # if cluster_node_metrics['cluster_cpu'] >= 0.9
#         if float(cluster_nodes_metrics['cluster_memory']) >= 0.85:
#             for service in services:
#                 scale_service(service, 0)
#         else:
#             if float(cluster_nodes_metrics['cluster_cpu']) < 0.8:
#                 if cpu is not None and mem is not None:
#                     min_cpu = min(cpu, key=lambda k: cpu[k])
#                     print('less cpu: ', min_cpu)
#                     scale_service(f'{min_cpu}', current_replica_count[min_cpu] + 1)
#         if float(cluster_nodes_metrics['cluster_memory']) >= 0.70:
#             if cpu is not None and mem is not None:
#                 #max_cpu = max(cpu, key=lambda k: cpu[k])
#                 max_mem = max(mem, key=lambda k: mem[k])
#                 print('high mem: ', max_mem)
#                 scale_service(f'{max_mem}', current_replica_count[max_mem] - 1)

#         # Sleep for 10 seconds
#         time.sleep(15)

#     except KeyboardInterrupt:
#         print("Exiting...")
#         break
