"""Private Bubble media adapter. No model weights or credentials in source."""
import concurrent.futures
import hashlib
import hmac
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import sqlite3
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(os.environ.get('STUDIO_DATA_DIR', '/tmp/studio-media'))
ROOT.mkdir(parents=True, exist_ok=True)
TOKEN = os.environ.get('STUDIO_ADAPTER_TOKEN', '')
PUBLIC = os.environ.get('RENDER_EXTERNAL_URL', os.environ.get('STUDIO_PUBLIC_URL', '')).rstrip('/')
CALLBACK = os.environ.get('BUBBLE_CALLBACK_URL', '')
CALLBACK_TOKEN = os.environ.get('BUBBLE_API_TOKEN', '')
WAN = 'https://zerogpu-aoti-wan2-2-fp8da-aoti-faster.hf.space'
LIP = 'https://hugging-apps-lip-forcing.hf.space'
POOL = concurrent.futures.ThreadPoolExecutor(max_workers=1)
DB_LOCK = threading.Lock()
MAX_DOWNLOAD = 256 * 1024 * 1024
HOSTS = ('cdn.bubble.io', 'hf.space', 'huggingface.co', 'hf.co', 'amazonaws.com', 'onrender.com')


class MediaError(ValueError):
    pass


def number(value, name, minimum=0, maximum=1800):
    try:
        result = float(value or 0)
    except (ValueError, TypeError):
        raise MediaError(f'Invalid {name}') from None
    if not math.isfinite(result) or not minimum <= result <= maximum:
        raise MediaError(f'{name} is outside supported limits')
    return result


def safe_url(url):
    p = urllib.parse.urlsplit(url)
    host = (p.hostname or '').lower()
    if p.scheme != 'https' or p.username or p.password or p.port not in (None, 443):
        raise MediaError('Media must use HTTPS without embedded credentials')
    if not any(host == s or host.endswith('.' + s) for s in HOSTS):
        raise MediaError('Media host is not in the approved download host list')
    try:
        addresses = socket.getaddrinfo(host, 443)
    except OSError:
        raise MediaError('Media host could not be resolved') from None
    if any(not ipaddress.ip_address(x[4][0]).is_global for x in addresses):
        raise MediaError('Private network media URLs are forbidden')
    return url


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        safe_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


OPENER = urllib.request.build_opener(SafeRedirect)


def download(url, destination):
    safe_url(url)
    size = 0
    try:
        with OPENER.open(url, timeout=60) as response, open(destination, 'wb') as out:
            while True:
                data = response.read(1024 * 1024)
                if not data:
                    break
                size += len(data)
                if size > MAX_DOWNLOAD:
                    raise MediaError('Media file exceeds the 256 MB input limit')
                out.write(data)
    except (urllib.error.URLError, TimeoutError, OSError):
        raise MediaError('Media download failed or expired; refresh its share URL') from None
    if not size:
        raise MediaError('Downloaded media is empty')
    return size


def command(args, timeout=1200):
    try:
        p = subprocess.run(args, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise MediaError('Media processing exceeded its time limit') from None
    if p.returncode:
        # FFmpeg diagnostics can contain private signed URLs; keep them internal.
        raise MediaError('Media processing failed: check the input format and timeline')
    return p.stdout


def probe(path):
    data = json.loads(command(['ffprobe', '-v', 'error', '-count_frames',
        '-show_entries', 'stream=codec_type,codec_name,width,height,r_frame_rate,nb_read_frames,duration:format=duration',
        '-of', 'json', str(path)], timeout=120))
    streams = data.get('streams', [])
    video = next((s for s in streams if s.get('codec_type') == 'video'), {})
    fps = video.get('r_frame_rate', '0/1').split('/')
    return {'duration': float(data.get('format', {}).get('duration', 0)),
            'frames': int(video.get('nb_read_frames', 0) or 0),
            'fps': int(fps[0]) / max(1, int(fps[1])) if len(fps) == 2 else 0,
            'width': int(video.get('width', 0)), 'height': int(video.get('height', 0)),
            'has_audio': any(s.get('codec_type') == 'audio' for s in streams)}


def legacy_rows(text, marker):
    rows = []
    for line in re.split(r'(?m)^' + marker + '=', text)[1:]:
        fields = re.split(r' \| ([a-z_]+)=', line.strip())
        row = {'id': fields[0]}
        row.update({fields[i]: fields[i + 1].strip() for i in range(1, len(fields) - 1, 2)})
        if 'trim' in row:
            values = row['trim'].split('..', 1)
            row['trim_in'] = values[0]
            row['trim_out'] = values[1] if len(values) > 1 else 0
        rows.append(row)
    return rows


def manifest(payload):
    if isinstance(payload, dict):
        value = payload
    else:
        try:
            value = json.loads(payload)
        except (ValueError, TypeError):
            match = re.match(r'Target:\s*([\d.]+) seconds,\s*([\d.]+) fps,\s*(.*?)\s*\nSHOTS\s*\n(.*?)\nAUDIO\s*\n(.*)', str(payload), re.S)
            if not match:
                raise MediaError('Assembly payload must be a JSON manifest or a studio timeline manifest') from None
            duration, fps, resolution, shots, audio = match.groups()
            value = {'duration': duration, 'fps': fps, 'resolution': resolution,
                     'shots': legacy_rows(shots, 'shot'), 'audio': legacy_rows(audio, 'track')}
    if not isinstance(value, dict):
        raise MediaError('Manifest must be an object')
    fps = int(number(value.get('fps', 24), 'FPS', 1, 60))
    resolution = str(value.get('resolution', '1920x1080'))
    dims = re.search(r'(\d{3,4})\s*[x×]\s*(\d{3,4})', resolution)
    if not dims:
        resolution = {'1080p': '1920x1080', '720p': '1280x720'}.get(resolution.lower(), resolution)
        dims = re.fullmatch(r'(\d+)x(\d+)', resolution)
    if not dims:
        raise MediaError('Resolution must specify width x height')
    width, height = map(int, dims.groups())
    if min(width, height) < 240 or width * height > 1920 * 1080 or width % 2 or height % 2:
        raise MediaError('Resolution must be even, between 240p and 1080p')
    shots = value.get('shots', [])
    audio = value.get('audio', [])
    if not isinstance(shots, list) or not 1 <= len(shots) <= 80 or not isinstance(audio, list) or len(audio) > 100:
        raise MediaError('Provide 1–80 shots and no more than 100 audio tracks')
    cursor = 0
    for shot in shots:
        if not isinstance(shot, dict) or not shot.get('source'):
            raise MediaError('Every shot needs an actual video source; missing footage is never replaced')
        shot['frames'] = round(number(shot.get('duration'), 'shot duration', .05, 600) * fps)
        start = number(shot.get('start', cursor / fps), 'shot start')
        if abs(round(start * fps) - cursor) > 0:
            raise MediaError('Shots must be contiguous and ordered; close timeline gaps and overlaps')
        transition = str(shot.get('transition', '')).strip().lower()
        if transition not in ('', 'cut', 'none', 'hard cut'):
            raise MediaError('This worker supports cuts; other transitions require a supported renderer')
        shot['trim_in'] = number(shot.get('trim_in'), 'trim in')
        if shot.get('trim_out') and number(shot['trim_out'], 'trim out') > 0:
            if number(shot['trim_out'], 'trim out') - shot['trim_in'] + 1/fps < shot['frames']/fps:
                raise MediaError('Shot trim range is shorter than the requested duration')
        cursor += shot['frames']
    target = round(number(value.get('duration', cursor / fps), 'target duration', .05, 600) * fps)
    if cursor != target:
        raise MediaError(f'Timeline has {cursor} frames but target requires {target}')
    if not audio and not value.get('allow_silent', False):
        raise MediaError('Add an audio track or explicitly allow a silent export')
    for track in audio:
        if not isinstance(track, dict) or not track.get('source'):
            raise MediaError('Every audio track requires an actual audio source')
        track['start'] = number(track.get('start'), 'audio start', 0, target/fps)
        track['trim_in'] = number(track.get('trim_in'), 'audio trim in')
        track['gain'] = number(track.get('gain', 1), 'audio gain', 0, 2)
        track['trim_out'] = number(track.get('trim_out'), 'audio trim out')
    return dict(value, shots=shots, audio=audio, fps=fps, width=width, height=height, frames=target, duration=target/fps)


def ffmpeg_args():
    return ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin', '-y', '-threads', '1', '-filter_threads', '1']


def assemble(value, folder, fetch=download):
    m = manifest(value)
    source_bytes = 0
    def bounded_fetch(url, destination):
        nonlocal source_bytes
        fetch(url, destination)
        source_bytes += destination.stat().st_size
        if source_bytes > 512 * 1024 * 1024:
            raise MediaError('Combined source media exceeds the 512 MB job limit')
        if sum(p.stat().st_size for p in folder.iterdir() if p.is_file()) > 1024 * 1024 * 1024:
            raise MediaError('Job exceeds the 1 GB scratch storage limit')
    fps, width, height = m['fps'], m['width'], m['height']
    segments = []
    for index, shot in enumerate(m['shots']):
        src = folder / f'shot-{index}.input'
        bounded_fetch(shot['source'], src)
        info = probe(src)
        seconds = shot['frames'] / fps
        if not info['frames'] or info['duration'] + 1/fps < shot['trim_in'] + seconds:
            raise MediaError('A shot source is missing video or is too short for its trim and duration')
        filters = f'fps={fps},scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p'
        if shot.get('caption'):
            caption_file = folder / f'caption-{index}.txt'
            caption_file.write_text(str(shot['caption'])[:4000], encoding='utf-8')
            start = number(shot.get('caption_start'), 'caption start', 0, seconds)
            end = number(shot.get('caption_end', seconds), 'caption end', start, seconds)
            filters += f",drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf:textfile={caption_file}:fontcolor=white:fontsize=36:box=1:boxcolor=black@0.6:x=(w-tw)/2:y=h-th-60:enable='between(t,{start},{end})'"
        segment = folder / f'segment-{index}.mp4'
        command(ffmpeg_args() + ['-protocol_whitelist', 'file,pipe', '-ss', str(shot['trim_in']), '-i', str(src),
                '-vf', filters, '-frames:v', str(shot['frames']), '-an', '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '20', str(segment)])
        if probe(segment)['frames'] != shot['frames']:
            raise MediaError('A normalized shot failed its frame-count check')
        segments.append(segment)
        src.unlink(missing_ok=True)
    listing = folder / 'concat.txt'
    listing.write_text(''.join(f"file '{path.name}'\n" for path in segments), encoding='utf-8')
    video = folder / 'video.mp4'
    command(ffmpeg_args() + ['-f', 'concat', '-safe', '1', '-i', str(listing), '-c', 'copy', str(video)])
    args = ffmpeg_args() + ['-i', str(video)]
    mix_filters = []
    for index, track in enumerate(m['audio']):
        src = folder / f'audio-{index}.input'
        bounded_fetch(track['source'], src)
        info = probe(src)
        if not info['has_audio'] or info['duration'] <= track['trim_in']:
            raise MediaError('An audio source is missing audio or its trim starts past the end')
        end = track['trim_out'] or info['duration']
        if end <= track['trim_in'] or end > info['duration'] + .05:
            raise MediaError('Audio trim range is invalid')
        args += ['-i', str(src)]
        delay = round(track['start'] * 1000)
        mix_filters.append(f'[{index+1}:a]atrim=start={track["trim_in"]}:end={end},asetpts=PTS-STARTPTS,volume={track["gain"]},adelay={delay}|{delay}[a{index}]')
    out = folder / 'output.mp4'
    if mix_filters:
        mix_filters.append(''.join(f'[a{i}]' for i in range(len(m['audio']))) + f'amix=inputs={len(m["audio"])}:normalize=0,apad,atrim=duration={m["duration"]}[mix]')
        args += ['-filter_complex_threads', '1', '-filter_complex', ';'.join(mix_filters), '-map', '0:v:0', '-map', '[mix]', '-c:a', 'aac']
    else:
        args += ['-an', '-map', '0:v:0']
    command(args + ['-c:v', 'copy', '-t', str(m['duration']), '-movflags', '+faststart', str(out)])
    result = probe(out)
    if (result['frames'] != m['frames'] or result['width'] != width or result['height'] != height
            or abs(result['fps'] - fps) > .001 or abs(result['duration'] - m['duration']) > .06
            or (bool(m['audio']) and not result['has_audio'])):
        raise MediaError('Final output failed media verification')
    return out, result


def gradio(base, endpoint, data):
    headers = {'Content-Type': 'application/json'}
    hf_token = os.environ.get('HF_TOKEN')
    if hf_token:
        headers['Authorization'] = 'Bearer ' + hf_token
    req = urllib.request.Request(base + '/gradio_api/call/' + endpoint,
            data=json.dumps({'data': data}).encode(), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            event_id = json.load(response)['event_id']
        req = urllib.request.Request(base + '/gradio_api/call/' + endpoint + '/' + event_id, headers=headers)
        with urllib.request.urlopen(req, timeout=420) as response:
            event = ''
            for raw in response:
                line = raw.decode().strip()
                if line.startswith('event:'):
                    event = line[6:].strip()
                elif line.startswith('data:') and event in ('complete', 'error'):
                    payload = json.loads(line[5:].strip())
                    if event == 'error':
                        raise MediaError('GPU provider failed or its free quota/time limit was exceeded')
                    return payload
    except (urllib.error.URLError, TimeoutError, KeyError):
        raise MediaError('GPU provider request failed or timed out') from None
    raise MediaError('GPU provider ended without a completed output')


def file_data(url):
    safe_url(url)
    return {'path': url, 'url': url, 'meta': {'_type': 'gradio.FileData'}}


def output_url(value):
    if isinstance(value, dict):
        for key in ('url', 'video', 'audio'):
            if value.get(key):
                try:
                    return output_url(value[key])
                except MediaError:
                    pass
    elif isinstance(value, list):
        for item in value:
            try:
                return output_url(item)
            except MediaError:
                pass
    elif isinstance(value, str) and value.startswith('https://'):
        return safe_url(value)
    raise MediaError('GPU response has no downloadable media URL')


def db():
    c = sqlite3.connect(ROOT / 'jobs.sqlite3', timeout=30)
    c.row_factory = sqlite3.Row
    c.execute('CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, source_job TEXT, digest TEXT, status TEXT, result TEXT, error TEXT, created REAL, callback_error TEXT)')
    return c


def update(job_id, **fields):
    with DB_LOCK, db() as c:
        c.execute('UPDATE jobs SET ' + ','.join(k + '=?' for k in fields) + ' WHERE id=?', [*fields.values(), job_id])


def get_job(job_id):
    with db() as c:
        row = c.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone()
    if not row:
        return None
    return dict(row)


def signed_output(job_id, expiry=None):
    expiry = expiry or int(time.time() + 86400)
    signature = hmac.new(TOKEN.encode(), f'{job_id}:{expiry}'.encode(), hashlib.sha256).hexdigest()
    return f'{PUBLIC}/files/{job_id}?expires={expiry}&signature={signature}'


def notify(job_id, request, status, result=None, error=''):
    if not CALLBACK or not CALLBACK_TOKEN:
        update(job_id, callback_error='Authenticated Bubble callback is not configured; poll the job endpoint')
        return
    # Never forward the Bubble administrator token to a client-supplied URL.
    target = urllib.parse.urlsplit(CALLBACK)
    if target.scheme != 'https' or not (target.hostname or '').endswith('.bubbleapps.io'):
        update(job_id, callback_error='Invalid fixed Bubble callback host')
        return
    body = dict(job_id=request['job'], provider_id=job_id, status=status, error=error)
    if result:
        body.update({k: result[k] for k in ('duration', 'frames', 'fps', 'width', 'height')})
        body['output'] = signed_output(job_id)
    req = urllib.request.Request(CALLBACK, data=json.dumps(body).encode(),
            headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + CALLBACK_TOKEN})
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            if not 200 <= response.status < 300:
                raise MediaError('Callback refused')
    except Exception:
        update(job_id, callback_error='Bubble callback failed; output remains available through authenticated polling')


def process(job_id, request):
    folder = ROOT / job_id
    folder.mkdir(exist_ok=True)
    try:
        if get_job(job_id)['status'] == 'Cancelled':
            return
        update(job_id, status='Processing')
        kind = request['kind']
        payload = request['payload']
        if kind in ('Assembly', 'MP4'):
            path, measured = assemble(payload, folder)
        else:
            if isinstance(payload, str):
                payload = json.loads(payload)
            if not isinstance(payload, dict):
                raise MediaError('GPU operations require a structured JSON payload')
            if kind == 'Video':
                source = payload.get('image_url', '')
                duration = number(payload.get('duration', 1), 'GPU duration', .5, 5)
                response = gradio(WAN, 'generate_video', [file_data(source), str(payload.get('prompt', ''))[:4000],
                        4, str(payload.get('negative_prompt', 'distorted face, deformed hands, text, watermark')),
                        duration, 1, 1, int(payload.get('seed', 42)), False])
            elif kind == 'Lip Sync':
                response = gradio(LIP, 'lip_sync', [file_data(payload.get('video_url', '')), file_data(payload.get('audio_url', '')), int(payload.get('seed', 42))])
            else:
                raise MediaError('Unsupported operation')
            path = folder / 'output.mp4'
            download(output_url(response), path)
            measured = probe(path)
            if not measured['frames'] or (kind == 'Lip Sync' and not measured['has_audio']):
                raise MediaError('GPU output failed media verification')
        if get_job(job_id)['status'] == 'Cancelled':
            return
        update(job_id, status='Completed', result=json.dumps(measured))
        notify(job_id, request, 'Completed', measured)
    except Exception as exc:
        error = str(exc) if isinstance(exc, MediaError) else 'Media processing failed; check the request manifest and provider availability'
        if get_job(job_id)['status'] != 'Cancelled':
            update(job_id, status='Failed', error=error)
            notify(job_id, request, 'Failed', error=error)
    finally:
        for path in folder.iterdir():
            if path.name != 'output.mp4':
                path.unlink(missing_ok=True)


def enqueue(request):
    if not isinstance(request, dict) or not isinstance(request.get('job'), str) or not request['job'] or len(request['job']) > 150:
        raise MediaError('A source job identifier is required')
    if request.get('kind') not in ('Assembly', 'MP4', 'Video', 'Lip Sync'):
        raise MediaError('Supported operations: Assembly, MP4, Video, Lip Sync')
    if request['kind'] in ('Assembly', 'MP4'):
        manifest(request.get('payload'))  # Reject bad timelines before queueing.
    elif not isinstance(request.get('payload'), dict):
        try:
            request['payload'] = json.loads(request['payload'])
        except (KeyError, ValueError, TypeError):
            raise MediaError('GPU payload must be JSON, not an unstructured prompt') from None
    digest = hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()
    with DB_LOCK, db() as c:
        # Signed output links last 24 hours. Expired, inactive outputs are reclaimed.
        expired = c.execute("SELECT id FROM jobs WHERE created<? AND status NOT IN ('Queued','Processing')", (time.time() - 86400,)).fetchall()
        for expired_job in expired:
            shutil.rmtree(ROOT / expired_job['id'], ignore_errors=True)
            c.execute('DELETE FROM jobs WHERE id=?', (expired_job['id'],))
        if sum(p.stat().st_size for p in ROOT.rglob('*') if p.is_file()) > 2 * 1024 * 1024 * 1024:
            raise MediaError('Scratch storage is full; archive and remove previous outputs before retrying')
        row = c.execute("SELECT * FROM jobs WHERE source_job=? AND digest=? AND status IN ('Queued','Processing','Completed')", (request['job'], digest)).fetchone()
        if row:
            return row['id']
        if c.execute("SELECT count(*) FROM jobs WHERE status IN ('Queued','Processing')").fetchone()[0] >= 4:
            raise MediaError('Worker queue is full; retry after an existing job finishes')
        job_id = secrets.token_hex(16)
        c.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?)', (job_id, request['job'], digest, 'Queued', '{}', '', time.time(), ''))
    POOL.submit(process, job_id, request)
    return job_id


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # Access paths can contain signed media URLs.

    def send_json(self, code, payload):
        raw = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(raw)

    def authorized(self):
        supplied = self.headers.get('Authorization', '')
        return bool(TOKEN) and hmac.compare_digest(supplied, 'Bearer ' + TOKEN)

    def do_GET(self):
        parsed = urllib.parse.urlsplit(self.path)
        if parsed.path == '/health':
            return self.send_json(200, {'status': 'ok', 'ffmpeg': bool(shutil.which('ffmpeg')), 'authenticated': bool(TOKEN),
                    'callback_configured': bool(CALLBACK and CALLBACK_TOKEN), 'storage': 'ephemeral',
                    'operations': ['Assembly', 'MP4', 'Video', 'Lip Sync']})
        match = re.fullmatch(r'/files/([a-f0-9]{32})', parsed.path)
        if match:
            values = urllib.parse.parse_qs(parsed.query)
            expiry = values.get('expires', [''])[0]
            signature = values.get('signature', [''])[0]
            expected = hmac.new(TOKEN.encode(), f'{match[1]}:{expiry}'.encode(), hashlib.sha256).hexdigest()
            if not TOKEN or not expiry.isdigit() or int(expiry) < time.time() or not hmac.compare_digest(signature, expected):
                return self.send_json(403, {'error': 'Invalid or expired media signature'})
            path = ROOT / match[1] / 'output.mp4'
            job = get_job(match[1])
            if not path.is_file() or not job or job['status'] != 'Completed':
                return self.send_json(404, {'error': 'Output is unavailable'})
            self.send_response(200)
            self.send_header('Content-Type', 'video/mp4')
            self.send_header('Content-Length', str(path.stat().st_size))
            self.end_headers()
            with path.open('rb') as source:
                shutil.copyfileobj(source, self.wfile)
            return
        if not self.authorized():
            return self.send_json(401, {'error': 'Authentication required'})
        match = re.fullmatch(r'/jobs/([a-f0-9]{32})', parsed.path)
        job = get_job(match[1]) if match else None
        if not job:
            return self.send_json(404, {'error': 'Unknown job'})
        measured = json.loads(job['result'])
        return self.send_json(200, dict(job_id=job['id'], status=job['status'], error=job['error'],
                output=signed_output(job['id']) if job['status'] == 'Completed' else '',
                callback_error=job['callback_error'], **measured))

    def do_POST(self):
        if not self.authorized():
            return self.send_json(401, {'error': 'Authentication required'})
        if self.path != '/jobs':
            return self.send_json(404, {'error': 'Unknown endpoint'})
        try:
            length = int(self.headers.get('Content-Length', 0))
            if not 1 <= length <= 1024 * 1024:
                return self.send_json(413, {'error': 'Manifest size must be 1 byte to 1 MB'})
            job_id = enqueue(json.loads(self.rfile.read(length)))
            job = get_job(job_id)
            return self.send_json(202, {'job_id': job_id, 'status': job['status']})
        except (ValueError, TypeError) as exc:
            return self.send_json(422, {'error': str(exc) if isinstance(exc, MediaError) else 'Malformed JSON manifest'})


if __name__ == '__main__':
    if not TOKEN:
        raise SystemExit('STUDIO_ADAPTER_TOKEN must be set; service refuses unauthenticated operation')
    with db() as c:
        c.execute("UPDATE jobs SET status='Failed',error='Worker restarted before completion; submit the job again' WHERE status IN ('Queued','Processing')")
    server = ThreadingHTTPServer(('0.0.0.0', int(os.environ.get('PORT', 10000))), Handler)
    server.serve_forever()
