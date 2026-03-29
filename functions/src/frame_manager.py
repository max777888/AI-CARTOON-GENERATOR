import os
import io
import json
import base64
from urllib.parse import urlparse, unquote
from openai import OpenAI
import firebase_admin
from firebase_admin import firestore, storage
from firebase_functions import https_fn
from dotenv import load_dotenv

load_dotenv()

_openai_client = None

def _get_client():
    global _openai_client
    if _openai_client is None:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set. Check your .env file.")
        _openai_client = OpenAI(api_key=api_key)
    return _openai_client


def handle_generate_frame(req: https_fn.Request) -> https_fn.Response:

    if not firebase_admin._apps:
        firebase_admin.initialize_app(options={
            'projectId': 'ai-cartoon-generator-202-5d178',
            'storageBucket': os.environ.get("STORAGE_BUCKET"),
        })

    db = firestore.client()
    data = req.get_json()

    project_id = data.get("projectId")
    scene_id = data.get("sceneId")

    if not project_id or not scene_id:
        return https_fn.Response("Missing projectId or sceneId", status=400)

    scene_ref = db.collection("projects").document(project_id).collection("scenes").document(scene_id)

    try:
        # 1. Fetch Scene & Character Data
        scene_snap = scene_ref.get()
        if not scene_snap.exists:
            return https_fn.Response(f"Scene {scene_id} not found", status=404)
        scene = scene_snap.to_dict()

        characters_present = scene.get("characters_present", [])
        if not characters_present:
            return https_fn.Response("No characters found in scene", status=400)

        char_id = characters_present[0]
        char_ref = db.collection("projects").document(project_id).collection("characters").document(char_id)
        character = char_ref.get().to_dict()

        face_url = character.get("face_image_url")
        if not face_url:
            return https_fn.Response("Character has no face_image_url", status=400)

        print(f"face_image_url raw value: {repr(face_url)}")

        # 2. Download the face reference image via Admin SDK (handles emulator routing automatically)
        # Parse the storage path out of the URL: /v0/b/BUCKET/o/ENCODED_PATH
        parsed = urlparse(str(face_url))
        parts = parsed.path.split("/o/", 1)
        if len(parts) < 2:
            return https_fn.Response(f"Cannot parse storage path from face_image_url: {face_url}", status=400)
        storage_path = unquote(parts[1])
        print(f"Resolved storage path: {storage_path}")

        bucket = storage.bucket()
        face_bytes = io.BytesIO(bucket.blob(storage_path).download_as_bytes())
        face_bytes.name = "face.png"  # OpenAI SDK requires a name attribute on the file object

        # 3. Build the prompt — describe the scene, style drives consistency
        visual_desc = scene.get("visual_description", "")
        prompt = (
            "Create a horror-cartoon scene featuring the character from the reference image. "
            f"SCENE: {visual_desc}. "
            "STYLE: Horror-cartoon, vibrant but dark, high contrast, cinematic composition. "
            "Preserve the character's facial features and appearance exactly as shown in the reference."
        )

        # 4. Call gpt-image-1 edit endpoint — accepts the face image as a visual reference
        print(f"Painting scene {scene_id}...")
        image_response = _get_client().images.edit(
            model="gpt-image-1",
            image=face_bytes,
            prompt=prompt,
            size="1024x1024",
        )

        # gpt-image-1 returns base64-encoded image data
        image_bytes = base64.b64decode(image_response.data[0].b64_json)

        # 5. Upload to Firebase Storage — OpenAI URLs expire, so we persist to our own bucket
        blob_path = f"projects/{project_id}/scenes/{scene_id}/frame.png"
        blob = bucket.blob(blob_path)
        blob.upload_from_string(image_bytes, content_type="image/png")
        blob.make_public()
        permanent_url = blob.public_url

        # 6. Update Firestore with the permanent frame URL
        scene_ref.update({
            "frame_image_url": permanent_url,
            "status": "completed"
        })

        return https_fn.Response(json.dumps({
            "status": "success",
            "frame_url": permanent_url
        }), mimetype="application/json")

    except Exception as e:
        print(f"Generation Failed: {str(e)}")
        scene_ref.set({"status": "failed"}, merge=True)
        return https_fn.Response(f"Error: {str(e)}", status=500)
