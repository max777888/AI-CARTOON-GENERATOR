import firebase_admin
from firebase_admin import storage, firestore
from firebase_functions import https_fn
import os
import json

def handle_upload_asset(req: https_fn.Request) -> https_fn.Response:
    # 1. Initialize with explicit Project ID to stop the "Universe Mismatch"
    if not firebase_admin._apps:
        firebase_admin.initialize_app(options={
            'projectId': 'ai-cartoon-generator-202-5d178',
            'storageBucket': 'ai-cartoon-generator-202-5d178.firebasestorage.app'
        })

    db = firestore.client()

    if not req.files:
        return https_fn.Response("No files uploaded", status=400)
    
    project_id = req.form.get("projectId")
    character_id = req.form.get("characterId")
    file = req.files.get("file")
    
    if not all([project_id, character_id, file]):
        return https_fn.Response("Missing fields", status=400)

    # 2. Prepare for upload
    ext = os.path.splitext(file.filename)[1].lower()
    is_image = ext in ['.png', '.jpg', '.jpeg']
    folder = "images" if is_image else "audio"
    blob_path = f"projects/{project_id}/characters/{character_id}/{folder}/{file.filename}"

    try:
        # Use the specific bucket name to force the emulator to find it
        bucket = storage.bucket('ai-cartoon-generator-202-5d178.firebasestorage.app') 
        blob = bucket.blob(blob_path)
        
        # Ensure we read the file from the start
        file.seek(0)
        file_data = file.read()
        
        blob.upload_from_string(
            file_data,
            content_type=file.content_type
        )

        # 3. Emulator-friendly URL Logic
        try:
            blob.make_public()
            public_url = blob.public_url
        except Exception:
            # Local Emulator URL format
            public_url = f"http://127.0.0.1:9199/v0/b/{bucket.name}/o/{blob_path.replace('/', '%2F')}?alt=media"

        # 4. Use .set with merge=True to prevent 404 hangs
        char_ref = db.collection("projects").document(project_id).collection("characters").document(character_id)
        
        field_to_update = "face_image_url" if is_image else "voice_ref_url"
        
        # This is where it was hanging. .set is much safer locally.
        char_ref.set({field_to_update: public_url}, merge=True)

        return https_fn.Response(
            json.dumps({"status": "success", "url": public_url}), 
            status=200, 
            mimetype="application/json"
        )

    except Exception as e:
        # Catch any actual error and return it to Postman immediately
        return https_fn.Response(f"Error: {str(e)}", status=500)