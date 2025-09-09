from flask_cors import CORS
from flask import Flask, request, jsonify, send_from_directory
import subprocess
import os

app = Flask(__name__)
CORS(app)


# Directory to save generated video files
OUTPUT_FOLDER = 'outputs'
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

@app.route('/api/generate', methods=['POST'])
def generate_video():
    data = request.get_json()

    topic = data.get('topic')
    clips = data.get('clips')
    output_filename = data.get('output')

    # Build full path for output file
    output_path = os.path.join(OUTPUT_FOLDER, output_filename)

    try:
        # Call your AI agent script as a subprocess
        subprocess.run([
            'python', 'ai_agent_fact_generator.py', topic,
            '--clips', str(clips),
            '--output', output_path
        ], check=True)

        # If successful, return the path to download the video
        return jsonify({
            'success': True,
            'fileUrl': f'/outputs/{output_filename}'
        })

    except subprocess.CalledProcessError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/outputs/<filename>')
def serve_output(filename):
    # Serve the video file for download
    return send_from_directory(OUTPUT_FOLDER, filename)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
