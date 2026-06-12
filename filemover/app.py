import os
import shutil
from pathlib import Path
from flask import Flask, request, send_file, render_template_string, redirect, url_for, abort
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024 * 1024  # 10GB

UPLOAD_DIR = Path(os.environ.get('UPLOAD_DIR', '/home/phc_13/Projects3/filemover/files'))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

HTML = '''
<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>FileMover</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f0f2f5; min-height: 100vh; }
    header { background: #1d1d1f; color: white; padding: 16px 32px; display: flex; align-items: center; gap: 12px; }
    header h1 { font-size: 1.3rem; font-weight: 600; }
    .badge { background: #0071e3; color: white; font-size: 0.7rem; padding: 2px 8px; border-radius: 20px; }
    main { max-width: 900px; margin: 40px auto; padding: 0 20px; }
    .card { background: white; border-radius: 16px; padding: 28px; margin-bottom: 24px; box-shadow: 0 2px 12px rgba(0,0,0,0.08); }
    h2 { font-size: 1rem; font-weight: 600; color: #1d1d1f; margin-bottom: 16px; }
    .upload-area { border: 2px dashed #c7c7cc; border-radius: 12px; padding: 40px; text-align: center; cursor: pointer; transition: all 0.2s; }
    .upload-area:hover, .upload-area.drag { border-color: #0071e3; background: #f0f6ff; }
    .upload-area input[type=file] { display: none; }
    .upload-area p { color: #6e6e73; font-size: 0.9rem; margin-top: 8px; }
    .upload-area .icon { font-size: 2.5rem; }
    .btn { display: inline-block; padding: 10px 24px; border-radius: 8px; border: none; cursor: pointer; font-size: 0.9rem; font-weight: 500; transition: all 0.15s; }
    .btn-primary { background: #0071e3; color: white; }
    .btn-primary:hover { background: #0077ed; }
    .btn-danger { background: #ff3b30; color: white; font-size: 0.8rem; padding: 6px 14px; }
    .btn-danger:hover { background: #ff453a; }
    .btn-dl { background: #34c759; color: white; font-size: 0.8rem; padding: 6px 14px; }
    .btn-dl:hover { background: #30d158; }
    .progress { display: none; margin-top: 14px; }
    .progress-bar { height: 6px; background: #e5e5ea; border-radius: 3px; overflow: hidden; }
    .progress-fill { height: 100%; background: #0071e3; width: 0%; transition: width 0.2s; border-radius: 3px; }
    .progress-text { font-size: 0.8rem; color: #6e6e73; margin-top: 6px; }
    table { width: 100%; border-collapse: collapse; }
    th { text-align: left; padding: 10px 12px; font-size: 0.8rem; color: #6e6e73; font-weight: 500; border-bottom: 1px solid #f2f2f7; }
    td { padding: 12px; font-size: 0.9rem; border-bottom: 1px solid #f2f2f7; vertical-align: middle; }
    tr:last-child td { border-bottom: none; }
    .filename { font-weight: 500; word-break: break-all; }
    .filesize { color: #6e6e73; white-space: nowrap; }
    .actions { display: flex; gap: 8px; justify-content: flex-end; }
    .empty { text-align: center; color: #a1a1a6; padding: 40px; }
    .alert { padding: 12px 16px; border-radius: 8px; margin-bottom: 20px; font-size: 0.9rem; }
    .alert-success { background: #d1f5e0; color: #1a7431; }
    .alert-error { background: #fde8e8; color: #b91c1c; }
    .server-info { background: #f2f2f7; border-radius: 8px; padding: 14px; font-size: 0.85rem; color: #3a3a3c; }
    .server-info code { background: #e5e5ea; padding: 2px 6px; border-radius: 4px; font-family: monospace; }
  </style>
</head>
<body>
  <header>
    <span style="font-size:1.5rem">📁</span>
    <h1>FileMover</h1>
    <span class="badge">Local Network</span>
  </header>
  <main>
    {% if msg %}
    <div class="alert alert-{{ msg_type }}">{{ msg }}</div>
    {% endif %}

    <div class="card">
      <h2>서버 정보</h2>
      <div class="server-info">
        맥북 브라우저에서 <code>http://{{ host }}:5000</code> 으로 접속하세요.
        업로드 경로: <code>{{ upload_dir }}</code>
      </div>
    </div>

    <div class="card">
      <h2>파일 업로드</h2>
      <form id="uploadForm" action="/upload" method="post" enctype="multipart/form-data">
        <div class="upload-area" id="dropZone" onclick="document.getElementById('fileInput').click()">
          <div class="icon">⬆️</div>
          <strong>클릭하거나 파일을 드래그하세요</strong>
          <p>여러 파일 동시 업로드 가능 · 최대 10GB</p>
          <input type="file" id="fileInput" name="files" multiple onchange="submitForm()">
        </div>
        <div class="progress" id="progress">
          <div class="progress-bar"><div class="progress-fill" id="progressFill"></div></div>
          <div class="progress-text" id="progressText">업로드 중...</div>
        </div>
      </form>
    </div>

    <div class="card">
      <h2>업로드된 파일 ({{ files|length }}개)</h2>
      {% if files %}
      <table>
        <thead>
          <tr><th>파일명</th><th>크기</th><th style="text-align:right">작업</th></tr>
        </thead>
        <tbody>
          {% for f in files %}
          <tr>
            <td class="filename">{{ f.name }}</td>
            <td class="filesize">{{ f.size }}</td>
            <td>
              <div class="actions">
                <a href="/download/{{ f.name }}" class="btn btn-dl">⬇ 다운로드</a>
                <form action="/delete/{{ f.name }}" method="post" onsubmit="return confirm('삭제할까요?')">
                  <button type="submit" class="btn btn-danger">🗑 삭제</button>
                </form>
              </div>
            </td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
      {% else %}
      <div class="empty">업로드된 파일이 없습니다.</div>
      {% endif %}
    </div>
  </main>

  <script>
    const dropZone = document.getElementById('dropZone');
    const form = document.getElementById('uploadForm');

    dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('drag'); });
    dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag'));
    dropZone.addEventListener('drop', e => {
      e.preventDefault();
      dropZone.classList.remove('drag');
      const dt = new DataTransfer();
      [...e.dataTransfer.files].forEach(f => dt.items.add(f));
      document.getElementById('fileInput').files = dt.files;
      submitForm();
    });

    function submitForm() {
      const files = document.getElementById('fileInput').files;
      if (!files.length) return;
      const progress = document.getElementById('progress');
      const fill = document.getElementById('progressFill');
      const text = document.getElementById('progressText');
      progress.style.display = 'block';

      const formData = new FormData(form);
      const xhr = new XMLHttpRequest();
      xhr.open('POST', '/upload');
      xhr.upload.onprogress = e => {
        if (e.lengthComputable) {
          const pct = Math.round(e.loaded / e.total * 100);
          fill.style.width = pct + '%';
          text.textContent = `${pct}% (${formatBytes(e.loaded)} / ${formatBytes(e.total)})`;
        }
      };
      xhr.onload = () => { if (xhr.status === 200) location.href = '/?msg=uploaded'; };
      xhr.send(formData);
    }

    function formatBytes(b) {
      if (b < 1024) return b + ' B';
      if (b < 1048576) return (b/1024).toFixed(1) + ' KB';
      if (b < 1073741824) return (b/1048576).toFixed(1) + ' MB';
      return (b/1073741824).toFixed(2) + ' GB';
    }
  </script>
</body>
</html>
'''


def fmt_size(b):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.2f} TB"


def get_files():
    result = []
    for p in sorted(UPLOAD_DIR.iterdir()):
        if p.is_file():
            result.append({'name': p.name, 'size': fmt_size(p.stat().st_size)})
    return result


@app.route('/')
def index():
    import socket
    try:
        host = socket.gethostbyname(socket.gethostname())
    except Exception:
        host = '127.0.0.1'
    msg = request.args.get('msg', '')
    msg_type = 'success' if msg else ''
    msg_map = {'uploaded': '파일 업로드 완료!', 'deleted': '파일 삭제 완료.'}
    return render_template_string(HTML,
        files=get_files(),
        host=host,
        upload_dir=str(UPLOAD_DIR),
        msg=msg_map.get(msg, ''),
        msg_type=msg_type,
    )


@app.route('/upload', methods=['POST'])
def upload():
    uploaded = request.files.getlist('files')
    for f in uploaded:
        if f.filename:
            name = secure_filename(f.filename)
            dest = UPLOAD_DIR / name
            # avoid overwrite: append number suffix
            counter = 1
            while dest.exists():
                stem, suffix = Path(name).stem, Path(name).suffix
                dest = UPLOAD_DIR / f"{stem}_{counter}{suffix}"
                counter += 1
            f.save(dest)
    return ('', 200)


@app.route('/download/<filename>')
def download(filename):
    safe = secure_filename(filename)
    path = UPLOAD_DIR / safe
    if not path.exists():
        abort(404)
    return send_file(path, as_attachment=True)


@app.route('/delete/<filename>', methods=['POST'])
def delete(filename):
    safe = secure_filename(filename)
    path = UPLOAD_DIR / safe
    if path.exists():
        path.unlink()
    return redirect(url_for('index', msg='deleted'))


if __name__ == '__main__':
    import socket
    try:
        host = socket.gethostbyname(socket.gethostname())
    except Exception:
        host = '0.0.0.0'
    print(f"\n  FileMover 실행 중")
    print(f"  로컬:   http://127.0.0.1:8081")
    print(f"  네트워크: http://{host}:8081")
    print(f"  업로드 경로: {UPLOAD_DIR}\n")
    app.run(host='0.0.0.0', port=8081, debug=False)
