from http.server import BaseHTTPRequestHandler, HTTPServer
from email.parser import BytesParser
from email.policy import default
import subprocess
import os
import json
import urllib.parse
import mimetypes

# Render par FFmpeg ka command
FFMPEG = "ffmpeg"

# Render ke liye
HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", "10000"))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)


class VixoraHandler(BaseHTTPRequestHandler):

    def send_json(self, data, status=200):
        response = json.dumps(data).encode("utf-8")

        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        self.wfile.write(response)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):

        if self.path != "/process":
            self.send_json(
                {"success": False, "message": "Invalid request"},
                404
            )
            return

        try:
            content_type = self.headers.get("Content-Type", "")
            length = int(self.headers.get("Content-Length", 0))

            body = self.rfile.read(length)

            headers = (
                f"Content-Type: {content_type}\r\n"
                "MIME-Version: 1.0\r\n\r\n"
            ).encode()

            message = BytesParser(policy=default).parsebytes(
                headers + body
            )

            video_data = None
            filename = "vixora_video.mp4"
            action = "TRIM"
            value = "10"

            for part in message.iter_parts():

                disposition = part.get("Content-Disposition", "")

                if 'name="file"' in disposition:

                    video_data = part.get_payload(
                        decode=True
                    )

                    uploaded_name = part.get_filename()

                    if uploaded_name:
                        filename = os.path.basename(
                            uploaded_name
                        )

                elif 'name="action"' in disposition:

                    action = part.get_content().strip()

                elif 'name="value"' in disposition:

                    value = part.get_content().strip()

            if not video_data:

                self.send_json({
                    "success": False,
                    "message": "Video upload nahi mila."
                })

                return

            filename = os.path.basename(filename)

            input_file = os.path.join(
                UPLOAD_DIR,
                filename
            )

            with open(input_file, "wb") as f:
                f.write(video_data)

            base_name = os.path.splitext(filename)[0]

            output_file = os.path.join(
                OUTPUT_DIR,
                base_name + "_VIXORA.mp4"
            )

            command = [
                FFMPEG,
                "-y",
                "-i",
                input_file
            ]

            # TRIM
            if action == "TRIM":

                seconds = int(
                    float(value or 10)
                )

                command += [
                    "-t",
                    str(seconds),
                    "-c:v",
                    "libx264",
                    "-preset",
                    "ultrafast",
                    "-c:a",
                    "aac",
                    "-threads",
                    "2",
                    output_file
                ]

            # REMOVE AUDIO
            elif action == "REMOVE_AUDIO":

                command += [
                    "-c:v",
                    "copy",
                    "-an",
                    output_file
                ]

            # SPEED
            elif action == "SPEED":

                speed = float(value or 2)

                if speed < 0.5:
                    speed = 0.5

                if speed > 2:
                    speed = 2

                command += [
                    "-filter:v",
                    f"setpts={1 / speed}*PTS",
                    "-filter:a",
                    f"atempo={speed}",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "ultrafast",
                    "-c:a",
                    "aac",
                    "-threads",
                    "2",
                    output_file
                ]

            # RESIZE
            elif action == "RESIZE":

                resize_map = {
                    "4K": 2160,
                    "1080p": 1080,
                    "1080": 1080,
                    "720p": 720,
                    "720": 720,
                    "480p": 480,
                    "480": 480
                }

                height = resize_map.get(
                    str(value).strip(),
                    1080
                )

                command += [
                    "-vf",
                    f"scale=-2:{height}",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "ultrafast",
                    "-c:a",
                    "aac",
                    "-threads",
                    "2",
                    output_file
                ]

            else:

                self.send_json({
                    "success": False,
                    "message": "Command supported nahi hai."
                })

                return

            result = subprocess.run(
                command,
                capture_output=True,
                text=True
            )

            if result.returncode != 0:

                self.send_json({
                    "success": False,
                    "message": result.stderr[-1500:]
                })

                return

            download_name = os.path.basename(
                output_file
            )

            self.send_json({
                "success": True,
                "message": "VIXORA editing complete!",
                "download": "/download/" +
                urllib.parse.quote(download_name)
            })

        except Exception as e:

            self.send_json({
                "success": False,
                "message": str(e)
            })

    def do_GET(self):

        # Download edited video
        if self.path.startswith("/download/"):

            name = urllib.parse.unquote(
                self.path[len("/download/"):]
            )

            name = os.path.basename(name)

            file_path = os.path.join(
                OUTPUT_DIR,
                name
            )

            if not os.path.exists(file_path):

                self.send_error(404)
                return

            size = os.path.getsize(file_path)

            self.send_response(200)

            self.send_header(
                "Content-Type",
                "video/mp4"
            )

            self.send_header(
                "Content-Length",
                str(size)
            )

            self.send_header(
                "Content-Disposition",
                f'attachment; filename="{name}"'
            )

            self.end_headers()

            with open(file_path, "rb") as f:

                while True:

                    chunk = f.read(1024 * 1024)

                    if not chunk:
                        break

                    self.wfile.write(chunk)

            return

        # Simple health check
        if self.path == "/health":

            self.send_json({
                "success": True,
                "message": "VIXORA server is running!"
            })

            return

        self.send_json({
            "success": True,
            "message": "VIXORA backend is live!"
        })


print("==============================")
print("      VIXORA CLOUD ENGINE")
print("==============================")
print("FFmpeg:", FFMPEG)
print("Host:", HOST)
print("Port:", PORT)

server = HTTPServer(
    (HOST, PORT),
    VixoraHandler
)

server.serve_forever()
