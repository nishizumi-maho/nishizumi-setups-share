# nishizumi-setups-share

This project provides a Python script for peer-to-peer sharing of iRacing setup files (`.sto`). It uses the BitTorrent DHT via `libtorrent` and runs `clamscan` to check files before sharing or after downloading. A minimal PyQt6 interface lets you browse your car folders, filter them and manage sharing.

## Requirements

- Python 3.12
- `libtorrent` Python bindings
- `clamav` (`clamscan` command)
- PyQt6 (for the optional GUI)

Install dependencies on Ubuntu:

```bash
pip install --user libtorrent PyQt6
sudo apt-get install clamav
```

## Usage

### Command line

To share your setups directory:

```bash
python3 share_setup.py --dir /path/to/iracing/setups
```

The script will ask for each car folder if you want to share the entire folder or create a subfolder named `share`. It will scan the folder with `clamscan` before creating a torrent and announcing it to the DHT. The generated magnet link is printed so other peers can download it.
Only `.sto` files are included in the torrent to avoid accidentally sharing other files.

To download setups from another peer using a magnet link:

```bash
python3 share_setup.py --dir /path/to/save/setups --download "magnet:?xt=..."
```

The downloaded data is scanned with `clamscan` for safety.

While running, the script keeps seeding your shared setups. Use `Ctrl+C` to stop sharing.

### Graphical interface

Launch the GUI and select your setups folder:

```bash
python3 share_setup.py --gui
```

The window lists car folders from the chosen directory and allows sharing or downloading setups via magnet links.
Use the filter box to quickly find a car by name. When sharing a car, the
interface asks whether to share the entire folder or create a `share` subfolder
inside it.
