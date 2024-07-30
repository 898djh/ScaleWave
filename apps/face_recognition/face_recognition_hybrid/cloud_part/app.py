import os
import random
import time

import face_recognition
import numpy as np

from flask import Flask, request, jsonify

app = Flask(__name__)


# Load a sample picture and learn how to recognize it.
obama_face_encoding = face_recognition.face_encodings(face_recognition.load_image_file("obama.jpg"))[0]
biden_face_encoding = face_recognition.face_encodings(face_recognition.load_image_file("biden.jpg"))[0]


def run_recognition(unknown_face_encodings):
    detected_people = []

    # Loop over each face found in the frame to see if it's someone we know.
    for face_encoding in unknown_face_encodings:
        # See if the face is a match for the known face(s)
        match = face_recognition.compare_faces([obama_face_encoding, biden_face_encoding], face_encoding)

        if match[0]:
            name = "Barack Obama"
        elif match[1]:
            name = "Joe Biden"
        else:
            name = "Unknown"
        detected_people.append(name)

    return detected_people


@app.route('/')
def index():
	return "Hello from Cloud-based Hybrid Face Recognition Service!"


@app.route("/recognize", methods=["POST"])
def hybrid_cloud_based_recognition():
    # Get the image encodings from the request and convert the list format to numpy arrays
    face_encodings = [np.array(arr_list) for arr_list in request.json['face_encodings']]

    # Run the face recognition
    result = run_recognition(face_encodings)

    # Simulate DNS resolution + network latency (remove if actually hosted in the cloud)
    latency_start_range = float(os.environ.get("LATENCY_START_RANGE", 60))
    latency_end_range = float(os.environ.get("LATENCY_END_RANGE", 100))
    network_latency = random.randint(latency_start_range, latency_end_range)/ 1000
    time.sleep(network_latency)
    
    return jsonify({'detections': result})


if __name__ == "__main__":
    app.run(host='0.0.0.0', debug=False, port=int(os.environ.get("PORT", 8080)))
