from firebase_admin import firestore
from firebase_functions import https_fn
import json

db = firestore.client()

def handle_create_project(req: https_fn.Request) -> https_fn.Response:
    data = req.get_json()
    name = data.get("name", "Untitled Movie")
    
    # Create a new project document
    new_project_ref = db.collection("projects").document()
    new_project_ref.set({
        "name": name,
        "createdAt": firestore.SERVER_TIMESTAMP,
        "status": "draft"
    })
    
    return https_fn.Response(
        json.dumps({"projectId": new_project_ref.id}), 
        mimetype="application/json"
    )