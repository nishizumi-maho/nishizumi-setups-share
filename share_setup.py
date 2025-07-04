import os
import argparse
import libtorrent as lt
import time
import subprocess
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel, QPushButton,
    QListWidget, QLineEdit, QFileDialog, QMessageBox, QCheckBox
)


def setup_firewall():
    """Try to open the torrent ports using ufw."""
    try:
        subprocess.run(['ufw', 'allow', '6881:6891/tcp'], check=False)
        subprocess.run(['ufw', 'allow', '6881:6891/udp'], check=False)
    except FileNotFoundError:
        print('ufw not installed, skipping firewall rules')



def scan_path(path: str) -> bool:
    """Recursively scan a path with clamscan."""
    try:
        result = subprocess.run(['clamscan', '-r', path], capture_output=True, text=True)
        return result.returncode == 0
    except FileNotFoundError:
        print("clamscan not found. skipping scan")
        return True


def create_torrent(folder):
    fs = lt.file_storage()

    def include(path):
        return path.lower().endswith('.sto')

    lt.add_files(fs, folder, include)
    if fs.num_files() == 0:
        raise RuntimeError('no .sto files found in ' + folder)
    t = lt.create_torrent(fs)
    t.add_tracker('udp://tracker.openbittorrent.com:80/announce')
    t.set_creator('iRacing setup sharer')
    lt.set_piece_hashes(t, os.path.dirname(folder))
    torrent = t.generate()
    torrent_path = os.path.join(folder, 'share.torrent')
    with open(torrent_path, 'wb') as f:
        f.write(lt.bencode(torrent))
    return torrent_path


def share_folder(ses, folder):
    torrent_path = create_torrent(folder)
    info = lt.torrent_info(torrent_path)
    h = ses.add_torrent({'ti': info, 'save_path': folder})
    magnet = lt.make_magnet_uri(info)
    print(f"Sharing {folder}\nMagnet: {magnet}")
    return h


def download_magnet(ses, magnet, out_dir):
    params = {'save_path': out_dir, 'storage_mode': lt.storage_mode_t.storage_mode_sparse}
    handle = lt.add_magnet_uri(ses, magnet, params)
    print('Downloading metadata...')
    while not handle.has_metadata():
        time.sleep(1)
    info = handle.get_torrent_info()
    print('Starting download...')
    while handle.status().state != lt.torrent_status.seeding:
        s = handle.status()
        print(f"{s.progress*100:.2f}% complete\r", end='')
        time.sleep(1)
    print('\nDownload complete')


class ShareWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('iRacing Setup Share')

        self.ses = lt.session()
        self.ses.listen_on(6881, 6891)
        self.ses.add_dht_router('router.bittorrent.com', 6881)
        self.ses.start_dht()
        setup_firewall()

        self.dir = None

        layout = QVBoxLayout(self)
        self.dir_label = QLabel('No directory selected')
        layout.addWidget(self.dir_label)

        btn_dir = QPushButton('Choose Setup Directory')
        btn_dir.clicked.connect(self.choose_dir)
        layout.addWidget(btn_dir)

        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText('Filter cars')
        self.filter_edit.textChanged.connect(self.refresh_cars)
        layout.addWidget(self.filter_edit)

        self.car_list = QListWidget()
        layout.addWidget(self.car_list)

        btn_share = QPushButton('Share Selected Car')
        btn_share.clicked.connect(self.share_selected)
        layout.addWidget(btn_share)

        layout.addWidget(QLabel('Magnet link to download:'))
        self.magnet_edit = QLineEdit()
        layout.addWidget(self.magnet_edit)
        btn_download = QPushButton('Download Magnet')
        btn_download.clicked.connect(self.download_selected)
        layout.addWidget(btn_download)

        self.status = QLabel('')
        layout.addWidget(self.status)

    def choose_dir(self):
        directory = QFileDialog.getExistingDirectory(self, 'Select Setup Directory')
        if directory:
            self.dir = directory
            self.dir_label.setText(directory)
            self.refresh_cars()

    def refresh_cars(self):
        self.car_list.clear()
        if not self.dir:
            return
        flt = self.filter_edit.text().lower()
        for car in sorted(os.listdir(self.dir)):
            car_path = os.path.join(self.dir, car)
            if os.path.isdir(car_path):
                if flt and flt not in car.lower():
                    continue
                self.car_list.addItem(car)

    def share_selected(self):
        if not self.dir:
            QMessageBox.warning(self, 'No directory', 'Select a setup directory first.')
            return
        items = self.car_list.selectedItems()
        if not items:
            QMessageBox.warning(self, 'No selection', 'Choose a car to share.')
            return
        car = items[0].text()
        path = os.path.join(self.dir, car)
        share_entire = QMessageBox.question(
            self,
            'Share folder',
            f'Share entire folder for {car}?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if share_entire == QMessageBox.StandardButton.Yes:
            folder = path
        else:
            folder = os.path.join(path, 'share')
            os.makedirs(folder, exist_ok=True)
        if scan_path(folder):
            try:
                handle = share_folder(self.ses, folder)
            except RuntimeError as e:
                QMessageBox.warning(self, 'No setups', str(e))
                return
            magnet = lt.make_magnet_uri(handle.get_torrent_info())
            self.status.setText(f'Sharing {car}: {magnet}')
        else:
            QMessageBox.warning(self, 'Virus detected', 'Share aborted.')

    def download_selected(self):
        if not self.dir:
            QMessageBox.warning(self, 'No directory', 'Select a setup directory first.')
            return
        magnet = self.magnet_edit.text().strip()
        if not magnet:
            QMessageBox.warning(self, 'No magnet', 'Enter a magnet link.')
            return
        if scan_path(self.dir):
            download_magnet(self.ses, magnet, self.dir)
            scan_path(self.dir)
        else:
            QMessageBox.warning(self, 'Virus detected', 'Download aborted.')




def main():
    parser = argparse.ArgumentParser(description='Share iRacing setup files over DHT')
    parser.add_argument('--dir', help='Path to iRacing setups directory')
    parser.add_argument('--download', help='Magnet link to download')
    parser.add_argument('--gui', action='store_true', help='Start graphical interface')
    args = parser.parse_args()

    if args.gui or not args.dir:
        app = QApplication([])
        win = ShareWindow()
        win.show()
        app.exec()
        return

    ses = lt.session()
    ses.listen_on(6881, 6891)
    ses.add_dht_router("router.bittorrent.com", 6881)
    ses.start_dht()
    setup_firewall()

    if args.download:
        if scan_path(args.dir):
            download_magnet(ses, args.download, args.dir)
            scan_path(args.dir)
        else:
            print('Download aborted due to virus detection')
        return

    for car in os.listdir(args.dir):
        car_path = os.path.join(args.dir, car)
        if not os.path.isdir(car_path):
            continue
        share_path = input(f"Share entire folder for {car}? (y/n)")
        if share_path.lower().startswith('y'):
            folder = car_path
        else:
            folder = os.path.join(car_path, 'share')
            os.makedirs(folder, exist_ok=True)
        if scan_path(folder):
            share_folder(ses, folder)
        else:
            print(f"Virus found in {folder}, skipping")

    print('Press Ctrl+C to exit and stop sharing')
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
