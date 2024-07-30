import os
import requests
import face_recognition

from flask import Flask, request, jsonify

app = Flask(__name__)

SERVICE_URL = os.environ.get("SERVICE_URL")     # URL of the third-party cloud service provider


@app.route('/')
def index():
	return "Hello from CPU-based Hybrid Face Recognition Service!"


@app.route("/recognize", methods=["POST"])
def hybrid_edge_cpu_based_recognition():
    # Get the image from the request
    file_stream = request.files['image']

    # Read the image and convert to array
    img = face_recognition.load_image_file(file_stream)

    # Get the face encodings from the image array
    unknown_face_encodings = face_recognition.face_encodings(img)
    num_of_faces_detected = len(unknown_face_encodings)

    if num_of_faces_detected > 0:
        # Send the encodings to the cloud for recognition
        headers = {'Host': os.environ.get("HOST_HEADER", 'face-recognition.default.example.com')}
        unknown_face_encodings = [encoding.tolist() for encoding in unknown_face_encodings]

        response = requests.post(SERVICE_URL, headers=headers, json={'face_encodings': unknown_face_encodings})

        if response.status_code == 200:
            # Forward the response from the service back to the user
            results = response.json()
            results['faces_found'] = num_of_faces_detected
            return jsonify(results), 200
        else:
            # Forward any errors from the service back to the user
            return jsonify({'error': 'Failed to process provided encodings'}), response.status_code
    else:
        return jsonify({'faces_found': num_of_faces_detected, 'detections': None})


if __name__ == "__main__":
    app.run(host='0.0.0.0', debug=False, port=int(os.environ.get("PORT", 8080)))
