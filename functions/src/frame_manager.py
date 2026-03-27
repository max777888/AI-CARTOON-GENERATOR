import os
import json
from openai import OpenAI
import firebase_admin
from firebase_admin import firestore
from firebase_functions import https_fn
from dotenv import load_dotenv 

load_dotenv() 

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))


def handle_generate_frame(req: https_fn.Request) -> https_fn.Response:

    if not firebase_admin._apps:
        try:
            firebase_admin.initialize_app()
        except Exception:
            # Fallback specifically for your local emulator setup
            firebase_admin.initialize_app(options={'projectId': 'ai-cartoon-generator-202-5d178'})

    db = firestore.client()
    data = req.get_json()
    
    project_id = data.get("projectId")
    scene_id = data.get("sceneId")

    if not project_id or not scene_id:
        return https_fn.Response("Missing projectId or sceneId", status=400)

    try:
        # 1. Fetch Scene & Character Data
        scene_ref = db.collection("projects").document(project_id).collection("scenes").document(scene_id)
        scene = scene_ref.get().to_dict()
        
        # We assume the first character in the list is the focus
        char_id = scene["characters_present"][0]
        char_ref = db.collection("projects").document(project_id).collection("characters").document(char_id)
        character = char_ref.get().to_dict()

        # 2. Construct the "Consistent Prompt"
        # We reference the face_image_url so DALL-E 'sees' the character
        face_url = character.get("face_image_url")
        visual_desc = scene.get("visual_description")
        
        final_prompt = f"Based on this character reference: {face_url}, create a cinematic cartoon scene. " \
                       f"SCENE DESCRIPTION: {visual_desc}. " \
                       f"STYLE: Horror-cartoon, vibrant but dark, high contrast, consistent with the character's face."

        # 3. Call DALL-E 3
        print(f" Painting scene {scene_id}...")
        response = client.images.generate(
            model="dall-e-3",
            prompt=final_prompt,
            size="1024x1024",
            quality="standard",
            n=1,
        )

        generated_url = response.data[0].url

        # 4. Update Firestore with the new frame
        scene_ref.update({
            "frame_image_url": generated_url,
            "status": "completed"
        })

        return https_fn.Response(json.dumps({
            "status": "success",
            "frame_url": generated_url
        }), mimetype="application/json")

    except Exception as e:
        print(f" Generation Failed: {str(e)}")
        return https_fn.Response(f"Error: {str(e)}", status=500)