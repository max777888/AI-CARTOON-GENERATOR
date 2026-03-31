import os
import json
import time
import tempfile
import requests
from urllib.parse import urlparse, unquote
from google import genai
from google.genai import types
import firebase_admin
from firebase_admin import firestore, storage
from firebase_functions import https_fn
from dotenv import load_dotenv

load_dotenv()

_genai_client = None


def _get_client():
    global _genai_client
    if _genai_client is None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not set. Check your .env file.")
        _genai_client = genai.Client(api_key=api_key)
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
    tmp_path = None

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

        # 3. Write frame to a temp file — Veo's file upload API requires a local path
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp.write(frame_bytes)
            tmp_path = tmp.name

        # 4. Upload the frame to Google File API as a Veo image reference
        client = _get_client()
        print(f"Uploading reference frame for scene {scene_id}...")
        image_file = client.files.upload(file=tmp_path)

        # 5. Trigger Veo video generation using the frame as the starting image
        print(f"Generating video for scene {scene_id}...")
        operation = client.models.generate_videos(
            model="veo-2.0-generate-001",
            prompt=script_segment,
            config=types.GenerateVideosConfig(
                image=image_file,
                duration_seconds=8,
                fps=24,
                aspect_ratio="16:9",
                generate_audio=True,
            ),
        )

        # 6. Poll until Veo finishes — video generation is a long-running operation
        while not operation.done:
            print("Rendering scene video, waiting...")
            time.sleep(10)
            operation = client.operations.get(operation.name)

        # 7. Download the generated video from Google's servers
        video_uri = operation.result.generated_videos[0].video.uri
        print(f"Video ready at: {video_uri}")
        video_response = requests.get(video_uri, timeout=120)
        video_response.raise_for_status()

        # 8. Upload video to Firebase Storage for a permanent URL
        video_blob_path = f"projects/{project_id}/scenes/{scene_id}/video.mp4"
        video_blob = bucket.blob(video_blob_path)
        video_blob.upload_from_string(video_response.content, content_type="video/mp4")
        video_blob.make_public()
        permanent_video_url = video_blob.public_url

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

    finally:
        # Always clean up the temp file
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
