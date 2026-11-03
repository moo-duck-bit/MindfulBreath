"""
MindfulBreath web bridge
GDX 호흡벨트(Go Direct Respiration Belt, USB) → 로컬 서버(SSE) → 웹 UI

사용법:
    python web/server.py            # 실제 호흡벨트(USB) 사용
    python web/server.py --demo     # 벨트 없이 가상 호흡 신호로 UI 확인
    python web/server.py --port 8000 --sensor 1 --period 50

브라우저에서 http://localhost:8000 접속
"""
import argparse
import csv
import json
import math
import os
import queue
import random
import threading
import time
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STOP = threading.Event()  # 종료 시 벨트 연결을 정상적으로 끊기 위한 신호
STATIC_DIR = os.path.join(BASE_DIR, 'static')
DATA_DIR = os.path.join(os.path.dirname(BASE_DIR), 'data')
CONTENT_DIR = os.path.join(os.path.dirname(BASE_DIR), 'docs', 'content')  # main.py와 같은 ./content/<부위>/<번호>.jpg


def content_index():
    """부위별 프레임 파일 목록 (main.py처럼 번호순 정렬)"""
    index = {}
    if os.path.isdir(CONTENT_DIR):
        for part in sorted(os.listdir(CONTENT_DIR)):
            folder = os.path.join(CONTENT_DIR, part)
            if os.path.isdir(folder):
                files = [f for f in os.listdir(folder) if f.split('.')[0].isdigit()]
                index[part] = sorted(files, key=lambda x: int(x.split('.')[0]))
    return index


class Hub:
    """센서 샘플을 연결된 모든 브라우저(SSE 구독자)에게 전달"""

    def __init__(self):
        self.lock = threading.Lock()
        self.subscribers = []
        self.status = {'connected': False, 'source': 'none', 'device': None, 'message': '초기화 중'}

    def subscribe(self):
        q = queue.Queue(maxsize=500)
        with self.lock:
            self.subscribers.append(q)
        return q

    def unsubscribe(self, q):
        with self.lock:
            if q in self.subscribers:
                self.subscribers.remove(q)

    def publish(self, event, payload):
        msg = f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
        with self.lock:
            for q in self.subscribers:
                try:
                    q.put_nowait(msg)
                except queue.Full:
                    pass

    def set_status(self, **kwargs):
        self.status.update(kwargs)
        self.publish('status', self.status)


class SessionLog:
    """main.py와 동일하게 Timestamp, Force Value를 CSV로 저장 + UI 이벤트 로그"""

    def __init__(self, tag):
        os.makedirs(DATA_DIR, exist_ok=True)
        stamp = time.strftime('%Y%m%d_%H%M%S')
        self.force_path = os.path.join(DATA_DIR, f'force_{stamp}_{tag}.csv')
        self.event_path = os.path.join(DATA_DIR, f'events_{stamp}_{tag}.csv')
        self._force_file = open(self.force_path, 'w', newline='')
        self._force = csv.writer(self._force_file)
        self._force.writerow(['Timestamp', 'Force Value'])
        self._event_file = open(self.event_path, 'w', newline='', encoding='utf-8-sig')
        self._event = csv.writer(self._event_file)
        self._event.writerow(['Timestamp', 'Event', 'Detail'])
        self.lock = threading.Lock()

    def force(self, t, value):
        with self.lock:
            self._force.writerow([t, value])
            self._force_file.flush()

    def event(self, name, detail):
        with self.lock:
            self._event.writerow([time.time(), name, json.dumps(detail, ensure_ascii=False)])
            self._event_file.flush()


def pick_device(devices):
    """USB 우선, 없으면 신호가 가장 강한 블루투스 GDX-RB"""
    usb = [d for d in devices if d.type == 'USB']
    if usb:
        return usb[0]
    ble = [d for d in devices if str(d.name or '').startswith('GDX-RB')] or devices
    return max(ble, key=lambda d: int(d.rssi or -999)) if ble else None


def gdx_reader(hub, log, sensor_id, period_ms, use_usb, use_ble):
    """USB/블루투스로 GDX 호흡벨트를 찾고, 끊기면 다시 찾는다."""
    import asyncio
    from godirect import GoDirect

    asyncio.set_event_loop(asyncio.new_event_loop())  # godirect BLE(bleak)는 스레드에 이벤트 루프가 필요
    link = ' / '.join(n for n, on in (('USB', use_usb), ('블루투스', use_ble)) if on)

    while not STOP.is_set():
        godirect = GoDirect(use_ble=use_ble, use_usb=use_usb)
        device = None
        try:
            hub.set_status(connected=False, source='gdx', device=None, message=f'호흡벨트({link}) 찾는 중… 전원을 확인하세요')
            device = pick_device(godirect.list_devices())
            if device is None:
                time.sleep(2)
                continue
            hub.set_status(message=f'{device.name or "GDX"} ({device.type}) 연결 중…')
            try:
                opened = device.open(auto_start=False)
            except Exception as e:
                if 'Characteristic' in str(e) and 'not found' in str(e):
                    # 다른 프로그램(Graphical Analysis 등)이 벨트의 데이터 채널을 점유한 경우
                    raise RuntimeError('벨트가 다른 프로그램에 연결되어 있습니다. '
                                       'Graphical Analysis에서 센서 연결을 해제하거나 앱을 종료하세요') from e
                raise
            if not opened:
                raise RuntimeError('장치를 열 수 없습니다')
            device.enable_sensors([sensor_id])  # 1: Force (N)
            device.start(period=period_ms)
            sensor = device.get_enabled_sensors()[0]
            name = f'{device.name or "GDX"} ({device.type})'
            print(f'[GDX] connected: {name} / {sensor.sensor_description} ({sensor.sensor_units})')
            hub.set_status(connected=True, source='gdx', device=name,
                           message=f'{sensor.sensor_description} ({sensor.sensor_units}) 수신 중')

            fails = 0
            while not STOP.is_set():
                if device.read():
                    fails = 0
                    for value in sensor.values:
                        t = time.time()
                        log.force(t, value)
                        hub.publish('force', {'t': t, 'force': value})
                    sensor.clear()
                else:
                    fails += 1
                    if fails >= 3:
                        raise RuntimeError('데이터 수신 실패')
        except Exception as e:
            msg = str(e) or type(e).__name__
            print(f'[GDX] {msg}')
            hub.set_status(connected=False, message=f'{msg} — 다시 연결 시도 중')
            time.sleep(3)
        finally:
            if device is not None:
                try:
                    device.stop()
                    device.close()
                except Exception:
                    # 연결 도중 실패한 BLE 클라이언트는 직접 끊어 준다
                    client = getattr(device, '_device', None)
                    if client is not None and hasattr(client, 'disconnect'):
                        try:
                            asyncio.get_event_loop().run_until_complete(client.disconnect())
                        except Exception:
                            pass
            try:
                godirect.quit()
            except Exception:
                pass


def demo_reader(hub, log, period_ms):
    """벨트 없이 UI를 확인하기 위한 가상 호흡 신호 (약 5초 주기)"""
    hub.set_status(connected=True, source='demo', device='Demo signal', message='데모 모드 (가상 호흡 신호)')
    start = time.time()
    while True:
        t = time.time()
        phase = (t - start) * 2 * math.pi / 5.0
        value = 2.0 + 1.5 * (0.5 - 0.5 * math.cos(phase)) + random.gauss(0, 0.03)
        log.force(t, value)
        hub.publish('force', {'t': t, 'force': value})
        time.sleep(period_ms / 1000)


def make_handler(hub, log):
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=STATIC_DIR, **kwargs)

        def log_message(self, fmt, *args):
            pass

        def translate_path(self, path):
            if path.startswith('/content/'):
                rel = path[len('/content/'):].split('?')[0]
                full = os.path.normpath(os.path.join(CONTENT_DIR, *rel.split('/')))
                if full.startswith(CONTENT_DIR):
                    return full
            return super().translate_path(path)

        def end_headers(self):
            if self.path.startswith('/content/'):
                self.send_header('Cache-Control', 'max-age=86400')
            super().end_headers()

        def do_GET(self):
            if self.path == '/stream':
                return self.stream()
            if self.path == '/status':
                return self.send_json(hub.status)
            if self.path == '/content-index':
                return self.send_json(content_index())
            return super().do_GET()

        def do_POST(self):
            if self.path == '/event':
                length = int(self.headers.get('Content-Length', 0))
                body = json.loads(self.rfile.read(length) or b'{}')
                log.event(body.get('event', ''), body.get('detail', {}))
                print(f"[UI] {body.get('event')} {body.get('detail', '')}")
                return self.send_json({'ok': True})
            self.send_error(404)

        def send_json(self, obj):
            data = json.dumps(obj, ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def stream(self):
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Connection', 'keep-alive')
            self.end_headers()
            q = hub.subscribe()
            try:
                self.wfile.write(f"event: status\ndata: {json.dumps(hub.status, ensure_ascii=False)}\n\n".encode())
                self.wfile.flush()
                while True:
                    try:
                        msg = q.get(timeout=10)
                    except queue.Empty:
                        msg = ': keep-alive\n\n'
                    self.wfile.write(msg.encode())
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass
            finally:
                hub.unsubscribe(q)

    return Handler


def main():
    parser = argparse.ArgumentParser(description='MindfulBreath GDX → Web UI bridge')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--sensor', type=int, default=1, help='GDX-RB 센서 번호 (1: Force N)')
    parser.add_argument('--period', type=int, default=50, help='샘플링 주기(ms)')
    parser.add_argument('--link', choices=['auto', 'usb', 'ble'], default='auto',
                        help='연결 방식: auto(USB 우선, 없으면 블루투스) / usb / ble')
    parser.add_argument('--demo', action='store_true', help='호흡벨트 없이 가상 신호 사용')
    args = parser.parse_args()

    hub = Hub()
    log = SessionLog('demo' if args.demo else 'gdx')
    if args.demo:
        target, targs = demo_reader, (hub, log, args.period)
    else:
        target, targs = gdx_reader, (hub, log, args.sensor, args.period,
                                     args.link in ('auto', 'usb'), args.link in ('auto', 'ble'))
    reader = threading.Thread(target=target, args=targs, daemon=True)
    reader.start()

    server = ThreadingHTTPServer(('127.0.0.1', args.port), make_handler(hub, log))
    server.daemon_threads = True
    print(f'MindfulBreath UI: http://localhost:{args.port}')
    print(f'Force log: {log.force_path}')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n종료합니다. 벨트 연결을 해제하는 중…')
        STOP.set()
        reader.join(timeout=10)


if __name__ == '__main__':
    main()
