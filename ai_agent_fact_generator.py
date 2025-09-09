import os
import sys
import argparse
import time
import shutil
import subprocess
import google.generativeai as genai
from moviepy.editor import VideoFileClip, concatenate_videoclips
from gtts import gTTS
import random
import textwrap
import json 

# --- Configuration & Pre-flight Checks ---
API_KEY = os.getenv("GOOGLE_API_KEY")
if API_KEY:
    genai.configure(api_key=API_KEY)


HISTORY_FILE = "fact_history.json"

def check_ffmpeg():
    if shutil.which("ffmpeg") is None:
        print("❌ ERROR: ffmpeg not found. Please install it to run this script.")
        sys.exit(1)

# Helper functions to manage fact history ---
def load_history():
    """Loads the fact history from the JSON file."""
    if not os.path.exists(HISTORY_FILE):
        return {}
    try:
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        print(" Warning: Could not read history file. Starting fresh.")
        return {}

def save_history(history_data):
    """Saves the updated fact history to the JSON file."""
    try:
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(history_data, f, indent=4)
    except IOError as e:
        print(f"❌ Error: Could not save history file. {e}")

# --- Core Functions ---


def get_facts_from_gemini(topic: str, num_facts: int) -> list[str]:
    """Generates a list of NEW facts, avoiding previously used ones."""
    if not API_KEY:
        print(" GOOGLE_API_KEY not set. Cannot generate facts.")
        return []

    print(f" Generating {num_facts} NEW facts about '{topic}'...")

    # Step 1: Load the history of used facts
    history = load_history()
    previous_facts = history.get(topic, [])

    # Step 2: Create a smarter prompt that tells the AI what to avoid
    prompt = f"List {num_facts} new, short, interesting facts about {topic}. Each fact should be a single sentence. IMPORTANT: Separate each fact with '|||'."
    if previous_facts:
        avoid_list = "\n".join(f"- {fact}" for fact in previous_facts)
        prompt += f"\n\nCrucially, DO NOT repeat any of the following facts that have already been used:\n{avoid_list}"

    try:
        model = genai.GenerativeModel('gemini-1.5-flash-latest')
        response = model.generate_content(prompt)
        
        new_facts_raw = response.text.strip().split('|||')
        new_facts = [fact.strip().lstrip('*- 1234567890. ') for fact in new_facts_raw if fact.strip()]
        
        # Step 3: Update and save the history with the new facts
        history.setdefault(topic, []).extend(new_facts)
        save_history(history)
        
        return new_facts
    except Exception as e:
        print(f"❌ Error generating facts. The API returned the following error: {e}")
        return []

def generate_tts_audio(text: str, output_filename: str) -> bool:
    print(f"   - Generating TTS audio for the fact...")
    try:
        tts = gTTS(text=text, lang='en', slow=False)
        tts.save(output_filename)
        return True
    except Exception as e:
        print(f"   - ❌ Failed to generate TTS audio: {e}")
        return False

def generate_mock_background(prompt: str, output_filename: str) -> bool:
    print(f"   - Generating mock background for: '{prompt}'...")
    try:
        r = lambda: random.randint(0, 100)
        random_color = f'#{r():02x}{r():02x}{r():02x}'
        ffmpeg_command = [
            'ffmpeg', '-y', '-f', 'lavfi',
            '-i', f'color=c={random_color}:s=720x1280:d=8',
            '-vf', 'noise=alls=10:allf=t', '-pix_fmt', 'yuv420p',
            output_filename
        ]
        subprocess.run(ffmpeg_command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception as e:
        print(f"   - ❌ Error generating background: {e}")
        return False

def generate_fact_video_clip(fact_text: str, visual_prompt: str, clip_index: int) -> str | None:
    final_clip_name = f"temp_clip_{clip_index}.mp4"
    background_clip_name = f"background_{clip_index}.mp4"
    audio_clip_name = f"audio_{clip_index}.mp3"
    text_filename = f"fact_{clip_index}.txt"
    if not generate_tts_audio(fact_text, audio_clip_name): return None
    if not generate_mock_background(visual_prompt, background_clip_name):
        if os.path.exists(audio_clip_name): os.remove(audio_clip_name)
        return None
    print(f"   - Combining video, audio, and text for clip {clip_index + 1}...")
    try:
        wrapped_text = "\n".join(textwrap.wrap(fact_text, width=30))
        with open(text_filename, 'w', encoding='utf-8') as f:
            f.write(wrapped_text)
        text_filter = f"drawtext=fontcolor=white:fontsize=45:x=(w-text_w)/2:y=(h-text_h)/2:box=1:boxcolor=black@0.6:boxborderw=15:alpha='if(lt(t,1),t,1)':textfile='{text_filename}'"
        ffmpeg_command = [
            'ffmpeg', '-y',
            '-i', background_clip_name, '-i', audio_clip_name,
            '-vf', text_filter, '-c:v', 'libx264', '-c:a', 'aac', '-shortest',
            final_clip_name
        ]
        subprocess.run(ffmpeg_command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        os.remove(background_clip_name)
        os.remove(audio_clip_name)
        os.remove(text_filename)
        return final_clip_name
    except Exception as e:
        print(f"❌ Failed to combine final clip: {e}")
        if os.path.exists(background_clip_name): os.remove(background_clip_name)
        if os.path.exists(audio_clip_name): os.remove(audio_clip_name)
        if os.path.exists(text_filename): os.remove(text_filename)
        return None

def stitch_clips(clip_files: list, output_filename: str):
    print(f"\n Stitching {len(clip_files)} narrated clips together...")
    try:
        clips = [VideoFileClip(file) for file in clip_files]
        final_clip = concatenate_videoclips(clips, method="compose")
        final_clip.write_videofile(output_filename, codec="libx264", audio_codec="aac", logger=None)
        for clip in clips: clip.close()
        print(f" Final video saved as {output_filename}")
    except Exception as e:
        print(f"❌ Error during video stitching: {e}")

def cleanup_temp_files(files: list):
    print("🧹 Cleaning up temporary files...")
    for file in files:
        try: os.remove(file)
        except OSError: pass

# --- Main Execution ---
if __name__ == "__main__":
    check_ffmpeg()
    parser = argparse.ArgumentParser(description="AI Fact Video Generator with Text-to-Speech.")
    parser.add_argument("topic", type=str, help="The topic to generate facts about ")
    parser.add_argument("--clips", type=int, default=3, help="Number of fact clips to generate.")
    parser.add_argument("--output", type=str, default="output.mp4", help="Name of the final output file.")
    args = parser.parse_args()
    facts = get_facts_from_gemini(args.topic, args.clips)
    
    if facts:
        temp_clips = [generate_fact_video_clip(fact, f"Visuals for {args.topic}", i) for i, fact in enumerate(facts)]
        valid_clips = [c for c in temp_clips if c]#Keeps only successfully created clips.
        if valid_clips:
            stitch_clips(valid_clips, args.output)
            cleanup_temp_files(valid_clips)

    print("\nProcess finished.")