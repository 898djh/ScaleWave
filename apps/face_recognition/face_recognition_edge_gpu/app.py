import os
import face_recognition

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
	return "Hello from GPU-based Edge Face Recognition Service!"


@app.route("/recognize", methods=["POST"])
def standalone_recognition():
    # Get the image from the request
    file_stream = request.files['image']

    # Read the image and convert to array
    img = face_recognition.load_image_file(file_stream)

    # Get the face encodings from the image array
    face_locations = face_recognition.face_locations(img, number_of_times_to_upsample=0, model="cnn")
    unknown_face_encodings = face_recognition.face_encodings(img, face_locations)
    num_of_faces_detected = len(unknown_face_encodings)

    result = None
    if num_of_faces_detected > 0:
        # Run the face recognition
        result = run_recognition(unknown_face_encodings)
        
    return jsonify({'faces_found': num_of_faces_detected, 'detections': result})


if __name__ == "__main__":
    app.run(host='0.0.0.0', debug=False, port=int(os.environ.get("PORT", 8080)))
