import json
import uuid
import firebase_admin
from firebase_admin import firestore
from firebase_functions import https_fn
from pydantic import BaseModel
from typing import List

# Ensure these match your actual Pydantic models
class DialogueLine(BaseModel):
    character_id: str
    text: str

class Scene(BaseModel):
    scene_number: int
    setting: str
    visual_description: str
    characters_present: List[str]
    dialogue: List[DialogueLine]
    mood: str

class ScriptAnalysis(BaseModel):
    title: str
    scenes: List[Scene]

def handle_analyze_script(req: https_fn.Request) -> https_fn.Response:
    if not firebase_admin._apps:
        firebase_admin.initialize_app()
    
    db = firestore.client()
    data = req.get_json()
    project_id = data.get("projectId")
    script_text = data.get("scriptText")

    if not project_id or not script_text:
        return https_fn.Response("Missing projectId or scriptText", status=400)

    chars_ref = db.collection("projects").document(project_id).collection("characters").stream()
    cast_list = {doc.to_dict().get("name", "Unknown"): doc.id for doc in chars_ref}
    
    try:
        raw_analysis = call_llm_for_analysis(script_text, cast_list)
        analysis = ScriptAnalysis.parse_obj(raw_analysis)
        
        # --- NEW: Track IDs for the UI ---
        created_scene_ids = []
        batch = db.batch()
        
        for scene in analysis.scenes:
            # We generate the ID manually so we can send it back to the UI
            scene_id = str(uuid.uuid4()) 
            scene_ref = db.collection("projects").document(project_id).collection("scenes").document(scene_id)
            
            # Store the data
            batch.set(scene_ref, scene.dict())
            
            # Add to our "Return List"
            created_scene_ids.append(scene_id)
        
        batch.commit()

        # --- UPDATED RESPONSE ---
        return https_fn.Response(json.dumps({
            "status": "success",
            "title": analysis.title,
            "sceneCount": len(created_scene_ids),
            "sceneIds": created_scene_ids  # The UI can now use these!
        }), mimetype="application/json")

    except Exception as e:
        return https_fn.Response(f"Analysis Failed: {str(e)}", status=500)

def call_llm_for_analysis(text, cast_list):
    """
    Mocking the LLM response so you can test the pipeline immediately.
    """
    print(f" Mocking analysis for script: {text[:50]}...")
    
    # We pretend the LLM returned this JSON
    mock_data = {
        "title": "Granny's Secret Recipe",
        "scenes": [
            {
                "scene_number": 1,
                "setting": "INT. KITCHEN - NIGHT",
                "visual_description": "Cinematic horror, low-key lighting. Granny stands by a steaming stove.",
                "characters_present": list(cast_list.values()), # Puts everyone in the scene
                "dialogue": [
                    {"character_id": list(cast_list.values())[0], "text": "The cookies are almost ready, my dear..."}
                ],
                "mood": "Terrifying"
            }
        ]
    }
    return mock_data