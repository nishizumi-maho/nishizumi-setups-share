# nishizumi-setups-share

This project provides a Python script for peer-to-peer sharing of iRacing setup files (`.sto`). Instead of using `libtorrent`, it relies on a lightweight DHT implementation (`kademlia`) and transfers files over HTTP with `aiohttp`. When available, `clamscan` checks files before sharing or after downloading. A minimal PyQt6 interface lets you browse your car folders and manage sharing.

## Requirements

- Python 3.12
- `kademlia` and `aiohttp`
- `clamav` (`clamscan` command) or Windows Defender
- PyQt6 (for the optional GUI)

Install dependencies (example using PowerShell):

```powershell
py -m pip install kademlia aiohttp PyQt6
# Optional: install ClamAV or ensure Windows Defender is available
```

## Usage

### Command line

To share your setups directory:

```powershell
py share_setup.py --dir C:\path\to\iracing\setups --share
```

The script starts a small HTTP server and announces itself on the DHT. Any `.sto` files found in the selected directory will be available to other peers.

To download a specific setup from a peer:

```powershell
py share_setup.py --dir C:\path\to\save --download 1.2.3.4:9000 CarName setup.sto
```

The downloaded file is scanned with `clamscan` when available.

While running, the script keeps serving your shared setups. Use `Ctrl+C` to stop sharing.

### Graphical interface

Launch the GUI and select your setups folder:

```powershell
py share_setup.py --gui
```

The window lists car folders from the chosen directory and allows sharing or downloading setups found on other peers.
