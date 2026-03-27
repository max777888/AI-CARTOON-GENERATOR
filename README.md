# AI-CARTOON-GENERATOR
This project is an end-to-end, automated video production platform. 
It leverages multimodal generative AI to transform raw creative assets—simple text scripts, static images, and short audio clips—into fully synthesized animated movies.
By combining large language models for scene direction, voice cloning for dialogue, and advanced image-to-video generation for the visuals the application acts as an AI director. 
It automates the complex pipeline of storyboarding, voice acting, and animation, allowing users to produce custom video content purely from foundational reference materials.


backend will consist of six core subsystems:

1 Authentication & Users
2 Project Management (cartoons, characters, scripts)
3 Voice Cloning Service (reference → synthetic voice)
4 Character Processing (face → style model)
5 Script Processing (Gemini → scenes JSON)
6 Video Generation Pipeline (Veo + job queue + renderer)

These services run on:

Firebase Auth → secure + easy
Cloud Functions → API endpoints, microservice style
Cloud Storage → user uploads, generated assets
Firestore → structured project data
Vertex AI → Gemini, Imagen, Voice, Veo
Cloud Tasks → asynchronous rendering queues


The Client User Flow

1. Authentication & Workspace Setup

Action: The user logs into the application and creates a new "Movie Project."
Behind the Scenes: Firebase Auth handles the secure login. Firestore initializes a new structured document for the project to track all subsequent assets and metadata.

2. Character Creation & Asset Upload
Action: The user creates a new "Character" profile within their project.
Action (Visuals): They upload several reference images of a specific face to define how the character should look.
Backend trigger: Cloud Storage saves the images. The Character Processing service (via Vertex AI/Imagen) trains or tunes a style model based on these faces.
Action (Audio): They upload a short audio sample of the target voice for this character.
Backend trigger: The Voice Cloning Service processes the sample to generate a synthetic voice profile ready for text-to-speech dialogue.

3. Script Ingestion

Action: The user uploads or types out the story script, indicating which characters are speaking and describing the actions.
Behind the Scenes: The Script Processing service takes over. A model like Gemini parses the raw text script and breaks it down into a highly structured scenes.json file. 
This JSON file dictates exactly who is speaking, what the background looks like, and what actions are happening frame-by-frame.

4. Generation & Rendering
Action: The user clicks "Generate Movie."
Behind the Scenes: The Video Generation Pipeline orchestrates the heavy lifting.
It matches the parsed dialogue from the JSON to the cloned voices.
It matches the scene descriptions to the processed character faces.
It sends these combined prompts to Veo (via Vertex AI) to generate the video clips.
Because this takes time, Cloud Tasks handles the asynchronous queuing, updating the database as each scene finishes.

5. Final Delivery
Action: The user receives a notification that the movie is ready and can play or download the final MP4.
Behind the Scenes: The frontend retrieves the compiled video file directly from Cloud Storage.
