import asyncio
import json
import os
import socket
import argparse
import subprocess
from typing import List
from pathlib import Path

from kademlia.network import Server
from aiohttp import web, ClientSession

try:
    from PyQt6.QtWidgets import (
        QApplication, QWidget, QVBoxLayout, QLabel, QPushButton,
        QListWidget, QLineEdit, QFileDialog, QMessageBox
    )
except Exception:
    QApplication = QWidget = QVBoxLayout = QLabel = QPushButton = QListWidget = QLineEdit = QFileDialog = QMessageBox = None


def scan_path(path: str) -> bool:
    """Recursively scan a path with clamscan if available."""
    try:
        result = subprocess.run(['clamscan', '-r', path], capture_output=True, text=True)
        return result.returncode == 0
    except FileNotFoundError:
        print('clamscan not found, skipping virus scan')
        return True


def setup_firewall(port: int):
    """Open the chosen port using Windows firewall."""
    if os.name == 'nt':
        subprocess.run([
            'netsh', 'advfirewall', 'firewall', 'add', 'rule',
            f'name=iRacingSetupShare{port}', 'dir=in', 'action=allow',
            'protocol=TCP', f'localport={port}'
        ], check=False)


class ShareServer:
    def __init__(self, directory: Path, port: int, dht_port: int, bootstrap: List[str]):
        self.directory = directory
        self.port = port
        self.dht_port = dht_port
        self.bootstrap = [tuple(b.split(':', 1)) for b in bootstrap if ':' in b]
        self.http_runner = None
        self.dht = Server()

    async def start(self):
        await self.dht.listen(self.dht_port)
        if self.bootstrap:
            await self.dht.bootstrap([(h, int(p)) for h, p in self.bootstrap])
        await self.register_peer()
        await self.start_http()

    async def register_peer(self):
        key = 'peers'
        addr = f'{self.get_ip()}:{self.port}'
        peers = []
        try:
            data = await self.dht.get(key)
            if data:
                peers = json.loads(data)
        except Exception:
            pass
        if addr not in peers:
            peers.append(addr)
            try:
                await self.dht.set(key, json.dumps(peers))
            except Exception:
                pass

    async def start_http(self):
        app = web.Application()
        app.add_routes([
            web.get('/list', self.handle_list),
            web.get('/download/{car}/{fname}', self.handle_download)
        ])
        self.http_runner = web.AppRunner(app)
        await self.http_runner.setup()
        site = web.TCPSite(self.http_runner, '0.0.0.0', self.port)
        await site.start()
        setup_firewall(self.port)

    async def handle_list(self, request):
        cars = {}
        for car in os.listdir(self.directory):
            car_path = self.directory / car
            if car_path.is_dir():
                cars[car] = [f.name for f in car_path.glob('*.sto')]
        return web.json_response(cars)

    async def handle_download(self, request):
        car = request.match_info['car']
        fname = request.match_info['fname']
        file_path = self.directory / car / fname
        if not file_path.is_file() or file_path.suffix != '.sto':
            raise web.HTTPNotFound()
        return web.FileResponse(file_path)

    async def stop(self):
        if self.http_runner:
            await self.http_runner.cleanup()
        self.dht.stop()

    @staticmethod
    def get_ip():
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(('8.8.8.8', 80))
            ip = s.getsockname()[0]
        except Exception:
            ip = '127.0.0.1'
        finally:
            s.close()
        return ip


async def fetch_peers(dht_port: int, bootstrap: List[str]) -> List[str]:
    node = Server()
    await node.listen(dht_port)
    if bootstrap:
        await node.bootstrap([(h, int(p)) for h, p in (b.split(':', 1) for b in bootstrap)])
    peers = []
    try:
        data = await node.get('peers')
        if data:
            peers = json.loads(data)
    except Exception:
        pass
    node.stop()
    return peers


async def list_available(car: str, peers: List[str]) -> List[str]:
    results = []
    async with ClientSession() as session:
        for peer in peers:
            try:
                async with session.get(f'http://{peer}/list') as resp:
                    data = await resp.json()
                    if car in data:
                        for fname in data[car]:
                            results.append((peer, fname))
            except Exception:
                continue
    return results


async def download_from_peer(peer: str, car: str, fname: str, dest_dir: Path):
    url = f'http://{peer}/download/{car}/{fname}'
    async with ClientSession() as session:
        async with session.get(url) as resp:
            resp.raise_for_status()
            dest_dir.mkdir(parents=True, exist_ok=True)
            out_path = dest_dir / fname
            with open(out_path, 'wb') as f:
                while True:
                    chunk = await resp.content.read(1024)
                    if not chunk:
                        break
                    f.write(chunk)
    return out_path


if QWidget is not None:
    class ShareWindow(QWidget):
        def __init__(self):
            super().__init__()
        self.setWindowTitle('iRacing Setup Share')
        self.dir = None
        self.port = 9000
        self.dht_port = 8468
        self.bootstrap = []
        self.server = None

        layout = QVBoxLayout(self)
        self.dir_label = QLabel('No directory selected')
        layout.addWidget(self.dir_label)
        btn_dir = QPushButton('Choose Setup Directory')
        btn_dir.clicked.connect(self.choose_dir)
        layout.addWidget(btn_dir)
        self.car_list = QListWidget()
        layout.addWidget(self.car_list)
        btn_share = QPushButton('Start Sharing')
        btn_share.clicked.connect(self.start_share)
        layout.addWidget(btn_share)
        layout.addWidget(QLabel('Car name for search:'))
        self.search_edit = QLineEdit()
        layout.addWidget(self.search_edit)
        btn_list = QPushButton('List available setups')
        btn_list.clicked.connect(self.list_setups)
        layout.addWidget(btn_list)
        self.available_list = QListWidget()
        layout.addWidget(self.available_list)
        btn_download = QPushButton('Download selected')
        btn_download.clicked.connect(self.download_selected)
        layout.addWidget(btn_download)
        self.status = QLabel('')
        layout.addWidget(self.status)

    def choose_dir(self):
        directory = QFileDialog.getExistingDirectory(self, 'Select Setup Directory')
        if directory:
            self.dir = Path(directory)
            self.dir_label.setText(directory)
            self.refresh_cars()

    def refresh_cars(self):
        self.car_list.clear()
        if not self.dir:
            return
        for car in os.listdir(self.dir):
            if (self.dir / car).is_dir():
                self.car_list.addItem(car)

    def start_share(self):
        if not self.dir:
            QMessageBox.warning(self, 'No directory', 'Select a setup directory first.')
            return
        if not scan_path(str(self.dir)):
            QMessageBox.warning(self, 'Virus detected', 'Share aborted.')
            return
        asyncio.create_task(self._start_server())
        self.status.setText('Sharing...')

    async def _start_server(self):
        self.server = ShareServer(self.dir, self.port, self.dht_port, self.bootstrap)
        await self.server.start()

    def gather_loop(self):
        loop = asyncio.get_event_loop()
        loop.run_until_complete(asyncio.sleep(0))

    def list_setups(self):
        car = self.search_edit.text().strip()
        if not car:
            QMessageBox.warning(self, 'No car name', 'Enter a car to search.')
            return
        asyncio.create_task(self._list_setups_async(car))

    async def _list_setups_async(self, car):
        peers = await fetch_peers(self.dht_port, self.bootstrap)
        results = await list_available(car, peers)
        self.available_list.clear()
        for peer, fname in results:
            self.available_list.addItem(f'{peer} - {fname}')

    def download_selected(self):
        items = self.available_list.selectedItems()
        if not items or not self.dir:
            QMessageBox.warning(self, 'No selection', 'Select a file and directory first.')
            return
        text = items[0].text()
        peer, fname = text.split(' - ', 1)
        car = self.search_edit.text().strip()
        asyncio.create_task(self._download_async(peer, car, fname))

        async def _download_async(self, peer, car, fname):
            out_path = await download_from_peer(peer, car, fname, self.dir / car)
            if scan_path(str(out_path)):
                self.status.setText(f'Downloaded {fname}')
            else:
                (self.dir / car / fname).unlink(missing_ok=True)
                QMessageBox.warning(self, 'Virus detected', 'File removed.')


async def cli_main(args):
    directory = Path(args.dir).resolve()
    if args.share:
        server = ShareServer(directory, args.port, args.dht_port, args.bootstrap)
        if not scan_path(str(directory)):
            print('Virus detected, aborting share')
            return
        await server.start()
        print('Sharing. Press Ctrl+C to stop.')
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            await server.stop()
    elif args.list:
        peers = await fetch_peers(args.dht_port, args.bootstrap)
        results = await list_available(args.list, peers)
        for peer, fname in results:
            print(f'{peer} - {fname}')
    elif args.download:
        peer, car, fname = args.download
        out_dir = directory / car
        out_path = await download_from_peer(peer, car, fname, out_dir)
        if scan_path(str(out_path)):
            print(f'Downloaded {fname} to {out_dir}')
        else:
            out_path.unlink(missing_ok=True)
            print('Virus detected, file removed')


def main():
    parser = argparse.ArgumentParser(description='Share iRacing setups via simple P2P')
    parser.add_argument('--dir', help='Path to iRacing setups directory')
    parser.add_argument('--share', action='store_true', help='Share setups from the directory')
    parser.add_argument('--list', metavar='CAR', help='List available setups for CAR')
    parser.add_argument('--download', nargs=3, metavar=('PEER', 'CAR', 'FILE'),
                        help='Download FILE of CAR from PEER (host:port)')
    parser.add_argument('--gui', action='store_true', help='Start the graphical interface')
    parser.add_argument('--port', type=int, default=9000, help='HTTP server port')
    parser.add_argument('--dht-port', type=int, default=8468, help='Port for the DHT node')
    parser.add_argument('--bootstrap', nargs='*', default=[], help='Bootstrap nodes host:port')
    args = parser.parse_args()

    if args.gui or not args.dir:
        if QApplication is None or ShareWindow is None:
            print('PyQt6 is not available; GUI cannot be started.')
            return
        app = QApplication([])
        win = ShareWindow()
        loop = asyncio.get_event_loop()
        timer = win.startTimer(100)
        def on_timer():
            loop.call_soon(loop.stop)
            loop.run_forever()
        win.timerEvent = lambda event: on_timer()
        win.show()
        app.exec()
        return

    asyncio.run(cli_main(args))


if __name__ == '__main__':
    main()
