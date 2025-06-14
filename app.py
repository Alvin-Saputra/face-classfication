from flask import Flask, request, send_file, jsonify, make_response
from PIL import Image
import cv2
import numpy as np
from skimage.feature import graycomatrix, graycoprops
import pandas as pd
from io import BytesIO
import joblib
import bcrypt
import datetime
import pytz
from apscheduler.schedulers.background import BackgroundScheduler

from firebase import check_user, authenticate_user, change_password, get_username_by_user_id, write_attendance, get_attendance_by_id, get_absent_user, mark_absent

app = Flask(__name__)

def detect_face(img):
    # Load Haar Cascades
    face_classifier = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

    # Convert image to grayscale
    if len(img.shape) == 3:  # If image is BGR
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:  # If image is already grayscale
        gray = img

    # Detect faces
    faces = face_classifier.detectMultiScale(gray, 1.3, 5)

    # Check if no faces detected
    if len(faces) == 0:
        return None

    # Crop detected faces and save in list
    cropped_faces = []
    for (x, y, w, h) in faces:
        face_crop = gray[y:y + h, x:x + w]
        cropped_faces.append(face_crop)

    return cropped_faces

def extract_glcm_features(image):
    # Kuantisasi gambar untuk mengurangi level intensitas
    levels = 8
    image_quantized = (image // (256 // levels)).astype('uint8')

    # Definisikan jarak dan sudut
    distances = [1, 2]
    angles = [0, np.pi/4, np.pi/2, 3*np.pi/4]  # 0°, 45°, 90°, 135°

    # Hitung GLCM
    glcm = graycomatrix(image_quantized, 
                       distances=distances,
                       angles=angles,
                       levels=levels,
                       symmetric=True,
                       normed=True)

    # Ekstrak properti GLCM
    properties = ['homogeneity', 'energy', 'correlation']
    features = []

    for prop in properties:
        feature = graycoprops(glcm, prop)
        features.extend(feature.flatten())  

    return np.array(features)

def process_image(img):
    features_list = []
    
    # Detect faces
    faces = detect_face(img)
    
    if faces is None or len(faces) == 0:
        return False

    # img_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    resized_face = cv2.resize(faces[0], (128, 128))
    glcm_features = extract_glcm_features(resized_face)
    features_list.append(glcm_features)

    # else:
    #     for face in faces:
    #         # Resize face to 128x128 for consistency
    #         resized_face = cv2.resize(face, (128, 128))
            
    #         # Extract GLCM features
    #         glcm_features = extract_glcm_features(resized_face)
    #         features_list.append(glcm_features)
    
    # columns = [f'feature_{i}' for i in range(len(features_list[0]))]
    _, refs_cols, _ = joblib.load("GLCM_SVM_Face_Classification_Model.pkl")
    columns = refs_cols
    return pd.DataFrame(features_list, columns=columns)


def predict(dataframe):
    df = dataframe

    model, refs_cols, target = joblib.load("GLCM_SVM_Face_Classification_Model.pkl")
    label_encoder = joblib.load("model_label_encoder.pkl")
    standard_scaler = joblib.load("standard_scaler.pkl")

    X_new = df[refs_cols]

    X_scaled = standard_scaler.transform(X_new)

    prediction = model.predict(X_scaled)

    converted_prediction = label_encoder.inverse_transform(prediction)
    
    # Melakukan prediksi
    print("Prediction:", converted_prediction)
    
    # Optionally, return the prediction
    return converted_prediction


@app.route('/health')
def health():
    return {"status": "ok"}, 200

@app.route('/process-image', methods=['POST'])
def classify():
    try:

        # Ambil waktu saat ini di zona waktu Jakarta
        jakarta_tz = pytz.timezone("Asia/Jakarta")
        current_time = datetime.datetime.now(jakarta_tz)
        current_hour = current_time.hour
        current_day = current_time.strftime('%A')  # Mengambil nama hari dalam bahasa Inggris
        
        # Tentukan jam dan hari yang diperbolehkan
        allowed_days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]  # Misalnya hanya Senin-Jumat
        allowed_hours = range(7, 24)  # Misalnya hanya dari jam 08:00 - 17:59 WIB

        if current_day not in allowed_days or current_hour not in allowed_hours:
            return jsonify({
                "status": "error",
                "message": f"Face recognition is only allowed on weekdays from 07:00 to 16:00 WIB. Current time: {current_time.strftime('%Y-%m-%d %H:%M:%S')}"
            }), 403

        # Get image from request
        img_file = request.files['image']
        user_id = request.form['user_id']

        if not user_id or not img_file:
            return jsonify({ "status": "error",
                            "message": "image and user_id are required"}), 400
        # Convert to OpenCV format
        img = cv2.imdecode(np.frombuffer(img_file.read(), np.uint8), cv2.IMREAD_COLOR)

        if img is None:
            return jsonify({
                "status": "error",
                "message": "The uploaded file is not a valid image format (e.g. JPEG, PNG, etc)."
            }), 400
        
        dataframe = process_image(img)
        
        # Detect faces
        # faces = detect_face(img)
        
        if dataframe is False:
            return jsonify({
                    'status': 'error',
                    'message': 'No face detected in the image'
                }), 200
        
        else:
            prediction = predict(dataframe)

            expected_username = get_username_by_user_id(user_id)
            if expected_username is None:
                return jsonify({
                    'status': 'error',
                    'message': 'User ID not found in database'
                }), 400

            if(prediction.tolist()[0] == expected_username):
                attendance = write_attendance(user_id)
                if attendance['status'] == 'success':
                    return jsonify({
                        'status': 'success',
                        'prediction': prediction.tolist()[0],
                        'message': attendance['message']
                    }), 200
                else:
                    return jsonify({
                        'status': 'error',
                        'message': 'Attendance could not be recorded'
                    }), 200
            else:
                return jsonify({
                    'status': 'error',
                    'message': 'Face does not match with user'
                }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    

@app.route('/check_username', methods=['POST'])
def check_username():
        # Get username and password from request
        username = request.form['username']
        return jsonify({"status": check_user(username)}), 200


@app.route('/login', methods=['POST'])
def login():
    try:
        user_id = request.form['user_id']
        password = request.form['password'] 

        if not user_id or not password:
            return jsonify({'status': 'error', 'message': 'user_id and password are required'}), 400

        auth_result = authenticate_user(user_id, password)

        if auth_result['status'] == 'error':
            return jsonify(auth_result), 400
        
        return jsonify(auth_result), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500 
    

@app.route('/update-password', methods=['POST'])
def update_password():
    try:
        user_id = request.form['user_id']
        current_password = request.form['current_password'] 
        new_password = request.form['new_password'] 

        if not user_id or not current_password or not new_password:
            return jsonify({"error": "user_id and password are required"}), 400

        update_password_result = change_password(current_password, new_password, user_id)

        if update_password_result['status'] == 'error':
            return jsonify({'status': 'error',
                            "message": update_password_result['message']}), 200
        
        return jsonify(update_password_result), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500 
    

@app.route('/get-attendance-list', methods=['POST'])
def get_attendance():
    try:
        user_id = request.form['user_id']
      
        if not user_id :
            return jsonify({"error": "user_id are required"}), 400

        attendance_list = get_attendance_by_id(user_id)

        return jsonify(attendance_list), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500 
    

def mark_absent_user():
    try:
        absent_user = get_absent_user()

        for user_id in absent_user:
            mark_absent(user_id)

    except Exception as e:
        print(f"Error marking absent users: {str(e)}")
    
scheduler = BackgroundScheduler(timezone="Asia/Jakarta") 
scheduler.add_job(mark_absent_user, 'cron', hour=9, minute=1)  
scheduler.start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)