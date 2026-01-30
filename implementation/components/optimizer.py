# imports
import json
import math
import random
import sys
import time
import os
import signal
import subprocess

from utils import check_pod_status, get_node_ready_status

# Check if at least one argument is provided (first argument is the script name itself)
if len(sys.argv) > 1:
    service_name = sys.argv[1]
else:
    sys.exit()

time.sleep(1.5)

import db_client
# Connect to Redis
redis_conn = db_client.connect_to_redis()

current_pid = None
running_service_optimizers = db_client.retrieve_json_data(redis_conn, f"{service_name}_optimizer_process")

if running_service_optimizers is None:
    running_service_optimizers = []
else:
    try:
        current_pid = running_service_optimizers[-1]
        for pid in running_service_optimizers[:-1]:
            try:
                os.kill(int(pid), signal.SIGTERM)  # Send the SIGTERM signal
                running_service_optimizers.remove(pid)
            except OSError as e:
                pass
    except Exception as e:
        print('Exception: ', e)

db_client.store_json_data(redis_conn, f"{service_name}_optimizer_process", running_service_optimizers)

# Example services: [throughput, {resource_consumption}, max_count]
# services = [
#     {'throughput': 10, 'cpu': 2, 'memory': 4, 'network': 1, 'max_count': 20},
#     {'throughput': 15, 'cpu': 3, 'memory': 6, 'network': 2, 'max_count': 20},
#     {'throughput': 20, 'cpu': 5, 'memory': 10, 'network': 3, 'max_count': 20}
# ]

# Total resource capacities
# capacities = {'cpu': 50, 'memory': 100, 'network': 30}

# init.
service_index = []
services = []
services_traffic_dist_factor = {}
services_index_mapping = {}
capacities = db_client.retrieve_json_data(redis_conn, "available_cluster_resources")
# print(capacities)
service_metrics = db_client.retrieve_json_data(redis_conn, f'{service_name}')
concurrent_requests = db_client.retrieve_json_data(redis_conn, f"{service_name}_requests")
# max_rep_bound = math.ceil((concurrent_requests['total'] / 49) + 1)
total_replica_count_now = 0
target_concurrency_per_pod = 0

i = 0
for k, v in service_metrics.items():
    service_index.append(k)
    services_index_mapping[k] = i
    
    # stop selecting services that do not report any metrics (meaning the service nodes have reached its max)
    if "face-recognition-oblique-00004" in k:
        node_ready_status = get_node_ready_status('nano-desktop')
        pod_status = check_pod_status("default", "face-recognition-oblique-00004")
        print("NODE AND POD STATUS: ", node_ready_status, pod_status)
        if node_ready_status != "True" or pod_status != "Running":
            v['cpu'] = capacities['cpu']
            v['memory'] = capacities['memory']
            v['disk_read'] = capacities['disk_read']
            v['disk_write'] = capacities['disk_write']
            v['network_uplink'] = capacities['network_uplink']
            v['network_downlink'] = capacities['network_downlink']
            v['gpu'] = capacities['gpu']
            v['normalized_throughput'] = 0.000000001    # penalizing the throughput
    
    if (v['cpu'] == 0.0 and v['memory'] == 0.0 and v['disk_read'] == 0.0 and 
        v['disk_write'] == 0.0 and v['network_uplink'] == 0.0 and 
        v['network_downlink'] == 0.0 and v['gpu'] == 0.0):
        v['cpu'] = capacities['cpu']
        v['memory'] = capacities['memory']
        v['disk_read'] = capacities['disk_read']
        v['disk_write'] = capacities['disk_write']
        v['network_uplink'] = capacities['network_uplink']
        v['network_downlink'] = capacities['network_downlink']
        v['gpu'] = capacities['gpu']
        v['normalized_throughput'] = 0.000000001    # penalizing the throughput

    cpu_usage = v['cpu']
    mem_usage = v['memory']
    disk_read_usage = v['disk_read']
    disk_write_usage = v['disk_write']
    network_uplink_usage = v['network_uplink']
    network_downlink_usage = v['network_downlink']
    gpu_usage = v['gpu']

    if cpu_usage <= 0:
        cpu_required = 0
    else:
        cpu_required = capacities['cpu']/cpu_usage
    
    if mem_usage <= 0:
        mem_required = 0
    else:
        mem_required = capacities['memory']/mem_usage
    
    if disk_read_usage <= 0:
        disk_read_required = 0
    else:
        disk_read_required = capacities['disk_read']/disk_read_usage
    
    if disk_write_usage <= 0:
        disk_write_required = 0
    else:
        disk_write_required = capacities['disk_write']/disk_write_usage
    
    if network_uplink_usage <= 0:
        network_uplink_required = 0
    else:
        network_uplink_required = capacities['network_uplink']/network_uplink_usage
    
    if network_downlink_usage <= 0:
        network_downlink_required = 0
    else:
        network_downlink_required = capacities['network_downlink']/network_downlink_usage
    
    if gpu_usage <= 0:
        gpu_required = 0
    else:
        gpu_required = capacities['gpu']/gpu_usage
    
    try:
        if 'oblique-00003' in k:
            # v['max_count'] = round(min(cpu_required, mem_required, disk_read_required, 
            #                         disk_write_required, network_uplink_required, 
            #                         network_downlink_required, gpu_required))
            v['max_count'] = math.floor(min(cpu_required, 
                                            mem_required, 
                                            disk_read_required, 
                                            disk_write_required, 
                                            network_uplink_required, 
                                            network_downlink_required, 
                                            gpu_required))
        else:
            # v['max_count'] = round(min(cpu_required, mem_required, disk_read_required, 
            #                         disk_write_required, network_uplink_required, 
            #                         network_downlink_required))
            v['max_count'] = math.floor(min(cpu_required, 
                                            mem_required, 
                                            disk_read_required, 
                                            disk_write_required, 
                                            network_uplink_required, 
                                            network_downlink_required))
        
        if v['max_count'] <= 0:
            v['max_count'] = 1
        else:
            v['max_count'] += 1
    
    except Exception as e:
        v['max_count'] = 1
    
    services.append(v)

    try:
        # services_traffic_dist_factor[k] = concurrent_requests[k]/(v['current_replica']*49)
        services_traffic_dist_factor[k] = concurrent_requests[k]/(v['current_replica']*v['target_concurrency_per_pod'])
    except ZeroDivisionError:
        services_traffic_dist_factor[k] = 15
    
    total_replica_count_now += v['current_replica']
    target_concurrency_per_pod = v['target_concurrency_per_pod']

    i += 1

print("SERVICE METRICS: ", services, service_index, services_traffic_dist_factor)

# max_rep_bound = math.ceil((concurrent_requests['total'] / (total_replica_count_now * 49)) + 1)
# max_rep_bound = max(math.ceil((concurrent_requests['total'] / 49) - total_replica_count_now), 1)
max_rep_bound = max(math.ceil((concurrent_requests['total'] / target_concurrency_per_pod) - total_replica_count_now), 0) + 1
print(total_replica_count_now, max_rep_bound)


# Initialize population
def initialize_population(size):
    # return [[random.randint(0, service['max_count']) for service in services] for _ in range(size)]
    return [[random.randint(0, min(service['max_count'], 
            max_rep_bound)) for service in services] for _ in range(size)]

# Fitness function
def fitness(solution):
    # total_throughput = sum(service['throughput'] * count for service, count in zip(services, solution))
    # if concurrent_requests['total'] < 300:
    #     total_throughput = sum(-((service['latency_per_request'] * service['queued_requests']) / count) for service, count in zip(services, solution))
    # else:
    #     total_throughput = sum(service['normalized_throughput'] * count for service, count in zip(services, solution))
    total_throughput = sum(
        service['normalized_throughput'] * count for service, count in zip(services, solution))
    resource_usage = {res: 0 for res in capacities.keys()}
    total_rep_count = 0
    
    for service, count in zip(services, solution):
        for res in capacities.keys():
            resource_usage[res] += service[res] * count
        total_rep_count += count
            
    # Penalty for exceeding capacities
    penalty = sum(max(0, resource_usage[res] - capacities[res]) for res in capacities.keys())

    # queue_penalty = max(0, ((concurrent_requests['total'])-((total_rep_count+total_replica_count_now)*49)))
    return total_throughput - (penalty * 100)
    # return total_throughput - (penalty * 100) - (queue_penalty*10)  # Penalty factor to ensure staying within capacity is prioritized

# Selection
def select(population, tournament_size=4):
    best = random.choice(population)
    for _ in range(tournament_size - 1):
        cont = random.choice(population)
        if fitness(cont) > fitness(best):
            best = cont
    return best

# Crossover
def crossover(parent1, parent2):
    crossover_point = random.randint(1, len(parent1) - 1)
    child1 = parent1[:crossover_point] + parent2[crossover_point:]
    child2 = parent2[:crossover_point] + parent1[crossover_point:]
    return child1, child2

# Mutation
def mutate(solution, mutation_rate=0.02):
    for i in range(len(solution)):
        if random.random() < mutation_rate:
            # solution[i] = random.randint(0, services[i]['max_count'])
            solution[i] = random.randint(0, min(services[i]['max_count'], max_rep_bound))
    return solution

# Genetic Algorithm
def genetic_algorithm(population_size=100, generations=100):
    population = initialize_population(population_size)
    
    for _ in range(generations):
        new_population = []
        for _ in range(len(population) // 2):
            parent1 = select(population)
            parent2 = select(population)
            child1, child2 = crossover(parent1, parent2)
            new_population.append(mutate(child1))
            new_population.append(mutate(child2))
            
        population = new_population + population  # Combine new population with previous to maintain diversity
        population = sorted(population, key=lambda x: fitness(x), reverse=True)[:population_size]  # Keep best
    
    # print("POPULATION......", population)

    best_solution = max(population, key=fitness)
    return best_solution, fitness(best_solution)

# Execute the GA
best_solution, best_fitness = genetic_algorithm()
print("Best Solution:", best_solution)
print("Best Fitness (Throughput - Penalties):", best_fitness)


def run_command(command):
    result = subprocess.run(command, capture_output=True, text=True, shell=True)
    if result.returncode != 0:
        #print(f"Error running command '{' '.join(command)}': {result.stderr}")
        return None
    return result.stdout


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
                    #print(f"Revision: {route.get('revisionName', 'Latest')}, Percent: {route.get('percent', 0)}%")
                    revisions_traffic[route.get('revisionName', 'Latest')] = route.get('percent', 0)
        
        return revisions_traffic


def get_revisions(service_name: str | None = None, namespace: str | None = None) -> list[str]:
    cmd = ["kn", "revision", "list", "-o", "json"]
    if namespace:
        cmd += ["-n", namespace]

    out = subprocess.check_output(cmd, text=True)

    import json
    data = json.loads(out)

    names = []
    for item in data.get("items", []):
        name = item.get("metadata", {}).get("name", "")
        if not name:
            continue
        # Optional filter: only revisions belonging to a service
        if service_name and not name.startswith(f"{service_name}-"):
            continue
        names.append(name)

    # Sort by revision suffix number if present (…-00001, …-00002, ...)
    def rev_key(n: str):
        try:
            return int(n.split("-")[-1])
        except Exception:
            return 10**12

    return sorted(names, key=rev_key)


def set_traffic_split(service_name, revision_traffic_list):
    """
    Sets traffic split for a Knative service.

    :param service_name: Name of the Knative service.
    :param revision_traffic_list: List of tuples with revision name and traffic percentage.
    """
    try:
        # Construct the `kn service update` command with traffic split
        command = ['kn', 'service', 'update', service_name]
        for revision, percentage in revision_traffic_list:
            command.extend(['--traffic', f'{revision}={int(percentage)}'])
        print("command: ", command)

        # Execute the command
        subprocess.run(command, check=True)
        print(f"Traffic split successfully updated for service: {service_name}")
    except subprocess.CalledProcessError as e:
        print(f"Failed to update traffic split: {e}")


def scale_to_100_integers(values):
    # Calculate the total of the original list
    # total = sum(values)
    
    # # Calculate the scale factor
    # scale_factor = 100 / total
    
    # # Scale and round each element in the list by the scale factor
    # scaled_integers = [round(element * scale_factor) for element in values]

    scaled_integers = []
    summed = 0

    for i, val in enumerate(services):
        summed += (val['normalized_throughput']*values[i])
        # summed += (val['normalized_throughput']*(values[i]+val['current_replica']))

    for i, val in enumerate(values):
        perc = round(((services[i]['normalized_throughput']*val)/summed)*100)
        # perc = round(((services[i]['normalized_throughput']*(val+(services[i]['current_replica'])))/summed)*100)
        scaled_integers.append(perc)
    
    # Adjust the elements to ensure the sum is exactly 100
    while sum(scaled_integers) != 100:
        difference = 100 - sum(scaled_integers)
        if difference > 0:
            for i in range(len(scaled_integers)):
                if scaled_integers[i] + difference <= 100:
                    scaled_integers[i] += difference
                    break
        else:
            for i in range(len(scaled_integers)):
                if scaled_integers[i] + difference >= 0:  # Ensuring no value becomes negative
                    scaled_integers[i] += difference
                    break
    
    return scaled_integers


def scale_dict_values_to_100_integers(original_dict):
    # Calculate the sum of the current values
    total_sum = sum(original_dict.values())
    
    # Avoid division by zero
    if total_sum == 0:
        return original_dict
    
    # Calculate the scaling factor
    scaling_factor = 100.0 / total_sum
    
    # Scale and round the values
    scaled_rounded_dict = {key: round(value * scaling_factor) for key, value in original_dict.items()}
    
    # Adjust the rounded values so their sum is 100
    diff = 100 - sum(scaled_rounded_dict.values())
    
    # Sort items by their fractional part of the scaling to minimize rounding impact
    items = sorted(original_dict.items(), 
                key=lambda x: (round(x[1] * scaling_factor) - x[1] * scaling_factor), reverse=diff < 0)
    
    # Adjust the values to make sure the total sum is 100
    for key, value in items:
        if diff == 0:
            break
            
        if diff > 0 and scaled_rounded_dict[key] < round(value * scaling_factor) + 1:
            scaled_rounded_dict[key] += 1
            diff -= 1
        elif diff < 0 and scaled_rounded_dict[key] > round(value * scaling_factor) - 1:
            scaled_rounded_dict[key] -= 1
            diff += 1
            
    return scaled_rounded_dict


#def get_small_traffic_adjustments(prev_traffic, new_traffic, adjustment_factor=0.75):
    # Step 1: Calculate differences (b-a)
#    diff = {key: new_traffic[key] - prev_traffic[key] for key in new_traffic}

    # Step 2: Identify keys with positive and negative differences
#    negative_keys = {key: diff[key] for key in diff if diff[key] < 0}
#    positive_keys = {key: diff[key] for key in diff if diff[key] > 0}

    # Step 3: Calculate total deduction and adjust values in 'a'
#    total_deduction = 0
    
#    for key in negative_keys:
#        # deduction = abs(prev_traffic[key] * adjustment_factor)
#        if key not in services_traffic_dist_factor.keys():
#            services_traffic_dist_factor[key] = 15
#        
#        deduction = abs(prev_traffic[key] * (adjustment_factor * services_traffic_dist_factor[key]))
#        total_deduction += deduction
#        prev_traffic[key] -= deduction

    # Step 4: Distribute the deducted amount to keys with positive differences
#    total_positive_diff = sum(diff[key] for key in positive_keys)
    
#    for key in positive_keys:
#        addition = total_deduction * (diff[key] / total_positive_diff)
#        prev_traffic[key] += addition

    # Normalize to make sure sums to 100
#    total = sum(prev_traffic.values())
#    normalized_prev_traffic = {key: value / total * 100 for key, value in prev_traffic.items()}

    # Step 5: Round and adjust to sum to 100
#    rounded_prev_traffic = {key: int(value) for key, value in normalized_prev_traffic.items()}
#    rounding_error = 100 - sum(rounded_prev_traffic.values())

    # Distributing the rounding error
#    fractions = {key: normalized_prev_traffic[key] - rounded_prev_traffic[key] for key in normalized_prev_traffic}
#    sorted_keys = sorted(fractions, key=fractions.get, reverse=True)

#    for key in sorted_keys:
#        if rounding_error <= 0:
#            break
#        rounded_prev_traffic[key] += 1
#        rounding_error -= 1

    # Results
#    print("Updated and rounded dictionary 'prev_traffic':", rounded_prev_traffic)
#    return rounded_prev_traffic


def get_small_traffic_adjustments(prev_traffic, new_traffic, adjustment_factor=0.25):
    """
    Move prev_traffic toward new_traffic, but cap each key's change to at most
    adjustment_factor (default 25%) of its current contribution (prev share).
    - Handles negative values in inputs (clips to 0).
    - Normalizes both prev and new to sum to 100 before computing deltas.
    - Caps per-key delta to +/- (adjustment_factor * prev_share).
      If prev_share is ~0, allow a small cap based on target to enable ramp-up.
    - Produces non-negative integer percentages summing to 100.
    """
    EPS = 1e-9
    # Union of keys
    keys = sorted(set(prev_traffic.keys()) | set(new_traffic.keys()))

    # Sanitize negatives (traffic can't be negative); treat missing as 0
    prev = {k: max(0.0, float(prev_traffic.get(k, 0.0))) for k in keys}
    new  = {k: max(0.0, float(new_traffic.get(k, 0.0))) for k in keys}

    # Normalize both to sum to 100 (so "contribution" is comparable)
    def normalize_to_100(d):
        total = sum(d.values())
        if total <= EPS:
            # If everything is zero, split evenly
            n = len(d)
            return {k: (100.0 / n if n > 0 else 0.0) for k in d}
        return {k: (v / total) * 100.0 for k, v in d.items()}

    prev_norm = normalize_to_100(prev)
    new_norm  = normalize_to_100(new)

    # Compute desired delta and cap it per key (±25% of prev share)
    capped = {}
    for k in keys:
        desired_delta = new_norm[k] - prev_norm[k]

        # Cap is proportional to current contribution (prev share).
        # If prev share is ~0, allow some movement based on target share too
        # so a key can ramp up from 0.
        base = max(prev_norm[k], new_norm[k], 1.0)  # 1.0 avoids "stuck at 0"
        cap_abs = adjustment_factor * base

        # Apply cap
        if desired_delta > cap_abs:
            delta = cap_abs
        elif desired_delta < -cap_abs:
            delta = -cap_abs
        else:
            delta = desired_delta

        capped[k] = prev_norm[k] + delta

    # Ensure non-negative, then renormalize to 100 again
    capped = {k: max(0.0, v) for k, v in capped.items()}
    capped = normalize_to_100(capped)

    #Convert to integers summing to 100 (largest remainder method)
    floored = {k: int(capped[k]) for k in keys}
    remainder = 100 - sum(floored.values())

    # Distribute remaining points to largest fractional parts
    fracs = sorted(keys, key=lambda k: (capped[k] - floored[k]), reverse=True)
    i = 0
    while remainder > 0 and i < len(fracs):
        floored[fracs[i]] += 1
        remainder -= 1
        i += 1

    # If (rarely) we overshoot due to weird inputs, remove from smallest fractions
    while remainder < 0:
        fracs_low = sorted(keys, key=lambda k: (capped[k] - floored[k]))
        for k in fracs_low:
            if remainder == 0:
                break
            if floored[k] > 0:
                floored[k] -= 1
                remainder += 1

    return floored

# Calculate and display proportions post-solution
total = sum(best_solution)
# print(total)

if total > 0:
    # Calculate the percentage of each number
    percentages = scale_to_100_integers(best_solution)
    # print(percentages)

    optimized_traffic_distribution = dict(zip(service_index, percentages))
    print(optimized_traffic_distribution)

    current_traffic_distribution = get_revisions_with_traffic_split(service_name)

    # remove later with dynamic
    # revisions = ['face-recognition-oblique-00001', 'face-recognition-oblique-00002', 
    #             'face-recognition-oblique-00003', 'face-recognition-oblique-00004']
    revisions = get_revisions(service_name="face-recognition-oblique", namespace="default")

    for revision in revisions:
        if revision not in current_traffic_distribution.keys():
            current_traffic_distribution[revision] = 0

        if revision not in optimized_traffic_distribution.keys():
            optimized_traffic_distribution[revision] = 0

    if current_traffic_distribution != optimized_traffic_distribution:
        # Filter out items with a value of 0
        optimized_traffic_distribution = get_small_traffic_adjustments(current_traffic_distribution, 
                                                                        optimized_traffic_distribution)

        filtered_dict = {key: value for key, value in optimized_traffic_distribution.items() if value != 0}
        print("Gradual Traffic Change: ", optimized_traffic_distribution)

        if 'face-recognition-oblique-00004' in filtered_dict.keys():
            allocated_value = filtered_dict['face-recognition-oblique-00004']
            filtered_dict['face-recognition-oblique-00004'] = round(allocated_value / 8)
            no_of_services = len(filtered_dict.keys())

            if no_of_services > 1:
                equal_halves = round(allocated_value / no_of_services)
                for service, percent in filtered_dict.items():
                    if service != 'face-recognition-oblique-00004':
                        filtered_dict[service] = percent + equal_halves
                filtered_dict = scale_dict_values_to_100_integers(filtered_dict)
                
        for service, percent in filtered_dict.items():
            optimized_traffic_distribution[service] = percent
        set_traffic_split(service_name, optimized_traffic_distribution.items())

if current_pid is not None:
    running_service_optimizers.remove(current_pid)
    db_client.store_json_data(redis_conn, f"{service_name}_optimizer_process", running_service_optimizers)

time.sleep(1)
