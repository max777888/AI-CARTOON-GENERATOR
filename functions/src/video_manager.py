import os
import json
import time
from urllib.parse import urlparse, unquote
from google import genai
from google.genai import types
import firebase_admin
from firebase_admin import firestore, storage
from firebase_functions import https_fn
from dotenv import load_dotenv

load_dotenv()


def _storage_url(blob_path: str) -> str:
    """Returns the correct Storage URL for emulator (local) or production."""
    from urllib.parse import quote
    bucket = os.environ.get("STORAGE_BUCKET")
    encoded = quote(blob_path, safe="")
    emulator_host = os.environ.get("FIREBASE_STORAGE_EMULATOR_HOST")
    if emulator_host:
        return f"http://{emulator_host}/v0/b/{bucket}/o/{encoded}?alt=media"
    return f"https://firebasestorage.googleapis.com/v0/b/{bucket}/o/{encoded}?alt=media"


_genai_client = None


def _get_client():
    global _genai_client
    if _genai_client is None:
        _genai_client = genai.Client(
            vertexai=True,
            project=os.environ.get("PROJECT_ID"),
            location=os.environ.get("VERTEX_LOCATION", "us-central1"),
        )
    return _genai_client


def handle_generate_scene_video(req: https_fn.Request) -> https_fn.Response:

    if not firebase_admin._apps:
        firebase_admin.initialize_app(options={
            'projectId': os.environ.get("PROJECT_ID"),
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
        # 1. Fetch scene data — must have a frame already generated
        scene_snap = scene_ref.get()
        if not scene_snap.exists:
            return https_fn.Response(f"Scene {scene_id} not found", status=404)
        scene = scene_snap.to_dict()

        frame_url = scene.get("frame_image_url")
        if not frame_url:
            return https_fn.Response("Scene has no frame_image_url. Run generate_frame first.", status=400)

        script_segment = scene.get("visual_description", "")

        # 2. Download the frame image from Firebase Storage via Admin SDK
        parsed = urlparse(str(frame_url))
        parts = parsed.path.split("/o/", 1)
        if len(parts) < 2:
            return https_fn.Response(f"Cannot parse storage path from frame_image_url: {frame_url}", status=400)
        storage_path = unquote(parts[1])

        bucket = storage.bucket()
        frame_bytes = bucket.blob(storage_path).download_as_bytes()

        # 3. Trigger Veo video generation — pass frame bytes directly as types.Image
        client = _get_client()
        print(f"Generating video for scene {scene_id}...")
        operation = client.models.generate_videos(
            model="veo-2.0-generate-001",
            prompt=script_segment,
            image=types.Image(image_bytes=frame_bytes, mime_type="image/png"),
            config=types.GenerateVideosConfig(
                duration_seconds=8,
                aspect_ratio="16:9",
            ),
        )

        # 6. Poll until Veo finishes — pass the operation object (not .name) for Vertex AI
        max_wait_seconds = 480
        elapsed = 0
        while not operation.done:
            if elapsed >= max_wait_seconds:
                raise TimeoutError(f"Veo did not complete after {max_wait_seconds}s")
            print(f"Rendering scene video, elapsed={elapsed}s")
            time.sleep(15)
            elapsed += 15
            operation = client.operations.get(operation)
        print(f"Veo operation completed.")

        # 7. Extract video bytes — Vertex AI Veo returns bytes directly, not a URI
        generated_video = operation.result.generated_videos[0]
        video_bytes = generated_video.video.video_bytes
        if not video_bytes:
            raise ValueError("Veo returned no video bytes. Check Vertex AI quota and model access.")
        print(f"Video received, size={len(video_bytes)} bytes")

        # 8. Upload video to Firebase Storage for a permanent URL
        video_blob_path = f"projects/{project_id}/scenes/{scene_id}/video.mp4"
        video_blob = bucket.blob(video_blob_path)
        video_blob.upload_from_string(video_bytes, content_type="video/mp4")
        permanent_video_url = _storage_url(video_blob_path)

        # 9. Update Firestore with the permanent video URL
        scene_ref.update({
            "video_url": permanent_video_url,
            "status": "video_completed",
        })

        return https_fn.Response(json.dumps({
            "status": "success",
            "video_url": permanent_video_url,
        }), mimetype="application/json")

    except Exception as e:
        print(f"Video Generation Failed: {str(e)}")
        scene_ref.set({"status": "video_failed"}, merge=True)
        return https_fn.Response(f"Error: {str(e)}", status=500)

