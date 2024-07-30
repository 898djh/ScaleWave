import redis
import json


def connect_to_redis(host='localhost', port=6379, db=0):
    try:
        return redis.Redis(host=host, port=port, db=db, decode_responses=True)
    except redis.RedisError as e:
        print(f"Redis connection error: {e}")
        return None


def store_json_data(redis_connection, key, data):
    try:
        json_data = json.dumps(data)
        redis_connection.set(key, json_data)
    except (TypeError, redis.RedisError) as e:
        print(f"Error storing data in Redis: {e}")


def retrieve_json_data(redis_connection, key):
    try:
        retrieved_json_data = redis_connection.get(key)
        if retrieved_json_data:
            return json.loads(retrieved_json_data)
        else:
            print("Data not found.")
            return None
    except redis.RedisError as e:
        print(f"Error retrieving data from Redis: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON data: {e}")
        return None


if __name__ == "__main__":
    # Connect to Redis
    r = connect_to_redis()

    # r.flushdb()

    if r:
        # Your JSON data
        data = {
            "max_network_downlink": 300.59,  # from benchmarking script
            "max_network_uplink": 350.56,    # from benchmarking script
            "max_disk_read": 2909.1,    # from benchmarking script
            "max_disk_write": 556.9     # from benchmarking script
        }

        # Store JSON data in Redis under the key "user:123"
        store_json_data(r, "max_resource_benchmarks", data)

        # Retrieve the JSON data from Redis
        retrieved_data = retrieve_json_data(r, "max_resource_benchmarks")

        if retrieved_data:
            print(retrieved_data)
