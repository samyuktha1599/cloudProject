import os
import pyrebase
from flask import Flask, request, redirect, send_file, render_template, session, flash
from google.cloud import storage
import google.generativeai as genai
import json 


firebase_config = {
    "apiKey": "AIzaSyDe7fjQsfUsaw0gQ6lO3cOif7X8xYS1g28",
    "authDomain": "cloud-project-firebase.firebaseapp.com",
    "databaseURL": "https://cloud-project-firebase-default-rtdb.firebaseio.com",
    "projectId": "cloud-project-firebase",
    "storageBucket": "cloud-project-firebase.appspot.com",
    "messagingSenderId": "857920893176",
    "appId": "1:857920893176:web:cffe8b68f8b4f66cd98b0d",
    "measurementId": "G-KBH87VLKRR"
}


firebase = pyrebase.initialize_app(firebase_config)
auth = firebase.auth()
db = firebase.database()  
storage_bucket = firebase.storage() 


genai.configure(api_key="AIzaSyCETRmLLLqmtOgxlRCiI97HdOqZ_pZlTvw")


os.makedirs('files', exist_ok=True)
bucket_name = "images2_buc"

app = Flask(__name__)
app.secret_key = os.urandom(24)  


def upload_blob(bucket_name, file, destination_blob_name):
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(destination_blob_name)
    blob.upload_from_file(file)

def download_blob(bucket_name, source_blob_name, destination_file_name):
    """Downloads a blob from the bucket."""
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(source_blob_name)
    blob.download_to_filename(destination_file_name)



def list_blobs(bucket_name):
    storage_client = storage.Client()
    blobs = storage_client.list_blobs(bucket_name)
    return [blob.name for blob in blobs]

def sync_local_with_gcs(user_id):
    """Sync local files with Google Cloud Storage."""
    user_dir = os.path.join('files', user_id)
    gcs_files = list_blobs(bucket_name)  
    
   
    if not os.path.exists(user_dir):
        os.makedirs(user_dir)

    
    local_files = os.listdir(user_dir)
    
    
    for gcs_file in gcs_files:
        if gcs_file.startswith(user_id):  
            filename = gcs_file.split('/')[-1]  
            local_file_path = os.path.join(user_dir, filename)

            if not os.path.exists(local_file_path):
                
                download_blob(bucket_name, gcs_file, local_file_path)
                print(f"Downloaded {filename} from GCS to {local_file_path}")

    
    for local_file in local_files:
        local_file_path = os.path.join(user_dir, local_file)
        gcs_file_path = f"{user_id}/{local_file}"
        if gcs_file_path not in gcs_files:
            
            os.remove(local_file_path)
            print(f"Deleted local file: {local_file_path}")


@app.route('/')
def index():
    if 'user_id' in session:
        user_id = session['user_id']
        sync_local_with_gcs(user_id)  
        all_files = list_files(user_id)
        
       
        image_files = [file for file in all_files if file.lower().endswith(('.png', '.jpg', '.jpeg'))]
        
        return render_template('index.html', files=image_files)
    else:
        return render_template('login.html')


@app.route('/login', methods=["POST"])
def login():
    email = request.form['email']
    password = request.form['password']
    
    try:
        user = auth.sign_in_with_email_and_password(email, password)
        session['user_id'] = user['localId']  
        return redirect('/')
    except Exception as e:
        flash("Login failed: " + str(e))
        return redirect('/')

@app.route('/logout', methods=['POST'])
def logout():
    session.pop('user_id', None)  
    return redirect('/')  

@app.route('/signup', methods=["POST"])
def signup():
    signup_email = request.form['signup_email']
    signup_password = request.form['signup_password']
    
    try:
       
        user = auth.create_user_with_email_and_password(signup_email, signup_password)
        flash("Signup successful! You can now log in.")
        return redirect('/')
    except Exception as e:
        flash("Signup failed: " + str(e))
        return redirect('/')


@app.route('/upload', methods=["POST"])
def upload():
    if 'user_id' not in session:
        return redirect('/') 

    user_id = session['user_id']
    file = request.files['form_file']
    filename = file.filename

   
    user_image_blob_path = f"{user_id}/{filename}"  
    upload_blob(bucket_name, file, user_image_blob_path)  

    
    local_image_path = os.path.join('files', user_id, filename)
    download_blob(bucket_name, user_image_blob_path, local_image_path)  

    
    description_text_file_name = generate_description(local_image_path, user_id)

    
    local_text_file_path = os.path.join('files', user_id, description_text_file_name)
    user_description_blob_path = f"{user_id}/{description_text_file_name}"  
    
    with open(local_text_file_path, "rb") as text_file:
        upload_blob(bucket_name, text_file, user_description_blob_path)  

    return redirect("/")








@app.route('/files')
def list_files(user_id):
    user_directory = os.path.join('files', user_id)
    if os.path.exists(user_directory):
        return os.listdir(user_directory)
    return []

@app.route('/files/view/<filename>')
def view_file(filename):
    if 'user_id' not in session:
        return redirect('/')  

    user_id = session['user_id']
    user_directory = os.path.join('files', user_id)
    description_filename = f"{os.path.splitext(filename)[0]}.txt"
    description_file_path = os.path.join(user_directory, description_filename)

    title = "No title available"
    description = "No description available."

    if os.path.exists(description_file_path):
        with open(description_file_path, 'r') as f:
            file_content = f.read().strip()
            cleaned_content = file_content.replace("```json", "").replace("```", "").strip()

            try:
                data = json.loads(cleaned_content)
                title = data.get("title", "No title available")
                description = data.get("description", "No description available")
            except json.JSONDecodeError as e:
                print(f"JSON Decode Error: {e}")
                description = "Invalid JSON format."

    return render_template('view_file.html', filename=filename, title=title, description=description)

@app.route('/files/<filename>')
def get_file(filename):
    if 'user_id' not in session:
        return redirect('/')  

    user_id = session['user_id']
    local_file_path = os.path.join('files', user_id, filename)

   
    if not os.path.exists(local_file_path):
        gcs_file_path = f"{user_id}/{filename}"
        download_blob(bucket_name, gcs_file_path, local_file_path)

    return send_file(local_file_path)


@app.route('/files/text/<filename>')
def get_text_file(filename):
    if 'user_id' not in session:
        return redirect('/')  

    user_id = session['user_id']
    local_text_file_path = os.path.join('files', user_id, f"{filename.rsplit('.', 1)[0]}.txt")

   
    if not os.path.exists(local_text_file_path):
        gcs_file_path = f"{user_id}/{filename.rsplit('.', 1)[0]}.txt"
        download_blob(bucket_name, gcs_file_path, local_text_file_path)

    return send_file(local_text_file_path)



def generate_description(image_path, user_id):
    """Generate description for the uploaded image using Gemini AI and upload it to GCS."""
    
    file = genai.upload_file(image_path, mime_type="image/jpeg")
    
    generation_config = {
        "temperature": 1,
        "top_p": 0.95,
        "top_k": 64,
        "max_output_tokens": 8192,
        "response_mime_type": "text/plain",
    }

    model = genai.GenerativeModel(
        model_name="gemini-1.5-flash",
        generation_config=generation_config,
    )

    chat_session = model.start_chat(
        history=[
            {
                "role": "user",
                "parts": [
                    file,
                    "For this image, provide a title and a short description in JSON format.",
                ],
            }
        ]
    )

    response = chat_session.send_message("Please provide the title and description.")
    description_text = response.text

    
    text_file_name = os.path.basename(image_path).rsplit('.', 1)[0] + '.txt'  
    
    
    local_text_file_path = os.path.join('files', user_id, text_file_name)
    with open(local_text_file_path, "w") as desc_file:
        desc_file.write(description_text)

    return text_file_name  


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
