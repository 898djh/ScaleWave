# ScaleWAVE

This repository contains the codebase scripts for integrating and testing the prototype version of the ScaleWAVE runtime on top of the Knative serverless platform.

## Architecture Overview
![alt text](architecture_overview.jpg?raw=true)

## Usage
1. Install k3s
    - https://docs.k3s.io/installation/configuration

2. Install Knative Serving
    - https://knative.dev/docs/install/yaml-install/serving/install-serving-with-yaml/

3. Enable Prometheus engine 
    - https://knative.dev/docs/serving/observability/metrics/collecting-metrics/#about-the-prometheus-stack

4. Create namespace "observability"
    ```
    $ kubectl create namespace observability
    ```

5. Enable observer config
    ```
    # For GPU metrics

    $ kubectl apply -f config/observer_config/jetson-metrics-exporter-daemonset.yaml

    $ kubectl apply -f config/observer_config/service-monitor.yaml
    
    $ helm install prometheus prometheus-community/kube-prometheus-stack -n observability --values config/observer_config/prometheus_stack/prometheus_stack.values

    $ helm install \
   --generate-name --namespace observability --values config/observer_config/prometheus_stack/dcgm_exporter.values \
   gpu-helm-charts/dcgm-exporter    
   ```

6. Install dependencies and start the runtime
    ```
    $ cd implementation

    $ pip install -r requirements.txt

    $ cd components

    $ python db_client.py
    $ python observer.py
    ```

7. Apply the face-recognition equivalent functions
    ```
    $ kubectl apply -f config/apps_config/face-recognition/cloud_based_eqv.yaml

    $ kubectl apply -f config/apps_config/face-recognition/edge_cpu_based_eqv.yaml

    $ kubectl apply -f config/apps_config/face-recognition/edge_gpu_based_eqv.yaml

    $ kubectl apply -f config/apps_config/face-recognition/hybrid_based_eqv.yaml
    ```

    **Note:** Before applying, the configuration file should include the container image. For building the container image, navigate to the **apps/face_recognition** directory, change env variables according to your preference, build image for each, and then replace the image in the config files.

8. Run the script to record the metrics
    ```
    $ cd evaluations/scripts/

    $ pip install -r requirements.txt

    $ python monitor_equivalent_replicas.py # on master node

    $ python monitor_usage.py   # on worker nodes
    $ python monitor_usage_nano.py  # specifically for Jetson Nano

    $ cd simulation/

    $ python send_requests.py
    ```
