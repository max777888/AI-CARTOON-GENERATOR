from firebase_admin import firestore, storage
from firebase_functions import https_fn
import json

db = firestore.client()

def handle_create_character(req: https_fn.Request) -> https_fn.Response:
    data = req.get_json()
    project_id = data.get("projectId")
    char_name = data.get("name")
    
    # Create a document in Firestore under projects/{projectId}/characters/
    char_ref = db.collection("projects").document(project_id).collection("characters").document()
    char_ref.set({
        "name": char_name,
        "image_url": None,
        "sound_url": None,
        "description": data.get("description", "")
    })
    
    return https_fn.Response(json.dumps({"charId": char_ref.id}), mimetype="application/json")

def handle_update_character_refs(req: https_fn.Request) -> https_fn.Response:
    """Updates the Firestore doc with URLs from Cloud Storage after upload."""
    data = req.get_json()
    project_id = data.get("projectId")
    char_id = data.get("charId")
    
    # Update only the provided fields (image or sound)
    update_data = {}
    if "image_url" in data: update_data["image_url"] = data["image_url"]
    if "sound_url" in data: update_data["sound_url"] = data["sound_url"]
    
    db.collection("projects").document(project_id).collection("characters").document(char_id).update(update_data)
    return https_fn.Response("Updated successfully", status=200)