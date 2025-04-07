import firebase_admin
from firebase_admin import credentials, firestore
import bcrypt
import os
import json
import datetime
import pytz

# Ambil JSON dari environment variable
firebase_creds_json = os.getenv('FIREBASE_CREDENTIALS')

if firebase_creds_json:
    firebase_creds_dict = json.loads(firebase_creds_json)  # Konversi JSON string menjadi dictionary
    cred = credentials.Certificate(firebase_creds_dict)  # Gunakan dictionary langsung
    firebase_admin.initialize_app(cred)
else:
    raise ValueError("FIREBASE_CREDENTIALS environment variable is not set")


# cred = credentials.Certificate('./credentials.json')
# firebase_admin.initialize_app(cred)

# Mendapatkan referensi ke Firestore
db = firestore.client()

def check_user(username):
        user_ref = db.collection("users").where("username", "==", username).get()
        if user_ref:
            return 'Success'
        else :
            return 'Failed'
        

def get_username_by_user_id(user_id):
    user_ref = db.collection("users").where("user_id", "==", user_id).get()
    user_doc = user_ref[0].to_dict()
    username = user_doc.get('username')

    return username

def authenticate_user(user_id, password):
    try:
        user_ref = db.collection("users").where("user_id", "==", user_id).get()
        if not user_ref:
            return {'status': 'error', 'message': 'User not found'}

        # Ambil data pengguna
        user_doc = user_ref[0].to_dict()
        stored_password = user_doc.get('password')
        username = user_doc.get('username')
        user_id = user_doc.get('user_id')

        # Verifikasi password
        if not bcrypt.checkpw(password.encode('utf-8'), stored_password.encode('utf-8')):
            return {'status': 'error', 'message': 'Invalid credentials'}
        
        return {'status': 'success', 'message': 'Login successful', 'username': username, 'user_id': user_id}

    except Exception as e:
        return {'status': 'error', 'message': str(e)}
    
def change_password(current_password, new_password, user_id):
    try:
        user_ref = db.collection("users").where("user_id", "==", user_id).get()
        if not user_ref:
            return {'status': 'error', 'message': 'User not found'}

        # Ambil data pengguna
        user_doc = user_ref[0].to_dict()
        stored_password = user_doc.get('password')

        # Verifikasi password
        if not bcrypt.checkpw(current_password.encode('utf-8'), stored_password.encode('utf-8')):
            return {'status': 'error', 'message': 'Old Password is incorrect'}
        
        if current_password == new_password:
            return {'status': 'error', 'message': 'Try a different new password'}
        
         # Hash password baru
        hashed_new_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

        # Dapatkan ID dokumen
        doc_id = user_ref[0].id  

        # Update password di Firestore
        db.collection("users").document(doc_id).update({'password': hashed_new_password})

        return {'status': 'success', 'message': 'Password changed successfully'}
    
    

    except Exception as e:
        return {'status': 'error', 'message': str(e)}
    
def write_attendance(user_id):
    try:
        # Ambil data pengguna
        user_ref = db.collection("attendance")
        user_ref.add({
            'user_id': user_id,
            'created_at': firestore.SERVER_TIMESTAMP,
            'status': 'present'
        })

        return {'status': 'success', 'message': 'Attendance marked successfully'}

    except Exception as e:
        return {'status': 'error', 'message': str(e)}
    

def get_attendance_by_id(user_id):
    try:
        # Ambil data pengguna
        user_ref = db.collection("attendance").where("user_id", "==", user_id).get()
        attendance_list = []
        for doc in user_ref:
            attendance_list.append(doc.to_dict())

        return {'status': 'success', 'message': 'Successfully Fetch Attendance History', 'attendance_data': 
                attendance_list}

    except Exception as e:
        return {'status': 'error', 'message': str(e)}
    

def get_absent_user():
   JAKARTA_TZ = pytz.timezone('Asia/Jakarta')

   users_ref = db.collection("users").get()
   all_users = [doc.to_dict().get("user_id") for doc in users_ref]

   now = datetime.datetime.now(JAKARTA_TZ)  # Waktu saat ini dalam WIB
   today = now.replace(hour=0, minute=0, second=0, microsecond=0)
   
   attendance_ref = db.collection("attendance")\
            .where("created_at", ">=", today)\
            .get()
   
   present_users = [doc.to_dict().get("user_id") for doc in attendance_ref]
   absent_users = [user_id for user_id in all_users if user_id not in present_users]

   return absent_users

def mark_absent(user_id):
    db.collection("attendance").add({
                "user_id": user_id,
                "created_at": firestore.SERVER_TIMESTAMP,
                "status": "absent"
            })
