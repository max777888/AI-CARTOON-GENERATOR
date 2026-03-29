from firebase_functions import https_fn
import firebase_admin
from firebase_admin import initialize_app
import os

# Do NOT initialize at module level
# We will initialize lazily when a function is called

def get_app():
    """Lazy initialization - only runs when needed"""
    if not firebase_admin._apps:
        try:
            # This works best with emulator + gcloud ADC
            initialize_app()
            print(" Firebase Admin initialized (using ADC)")
        except Exception:
            # Fallback for emulator
            initialize_app(options={'projectId': 'ai-cartoon-generator-202-5d178'})
            print(" Firebase Admin initialized with projectId fallback")
    return firebase_admin.get_app()


# ====================== Your Functions ======================
@https_fn.on_request()
def create_project(req: https_fn.Request) -> https_fn.Response:
    get_app()   # initialize only when this function is called
    from src.project_manager import handle_create_project
    return handle_create_project(req)


@https_fn.on_request()
def create_character(req: https_fn.Request) -> https_fn.Response:
    get_app()
    from src.character_manager import handle_create_character
    return handle_create_character(req)


@https_fn.on_request()
def update_character_refs(req: https_fn.Request) -> https_fn.Response:
    get_app()
    from src.character_manager import handle_update_character_refs
    return handle_update_character_refs(req)


@https_fn.on_request()
def upload_asset(req: https_fn.Request) -> https_fn.Response:
    try:
        # Move the import inside the try block
        from src.assets_manager import handle_upload_asset
        return handle_upload_asset(req)
        
    except Exception as e:
        # 1. Grab the full, detailed error log
        error_trace = traceback.format_exc()
        
        # 2. Print it to your terminal in bright red (figuratively)
        print("\n" + "="*50)
        print(" FATAL PYTHON CRASH DURING REQUEST ")
        print(error_trace)
        print("="*50 + "\n")
        
        # 3. Send it directly back to Postman so it stops hanging
        return https_fn.Response(f"CRASH LOG:\n{error_trace}", status=500)

@https_fn.on_request()
def analyze_script(req: https_fn.Request) -> https_fn.Response:
    from src.script_manager import handle_analyze_script
    return handle_analyze_script(req)    

@https_fn.on_request(timeout_sec=300)
def generate_frame(req: https_fn.Request) -> https_fn.Response:
    from src.frame_manager import handle_generate_frame
    return handle_generate_frame(req)