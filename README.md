
# 🚆 Build Your First Shape for Rail!

Hi there!  
While searching for tools that generate shapes for public transport, I don't find any interesting options—so I decided to create this program myself. Currently, it generates shapes specifically for rail transport, but I plan to expand it to support other public transport modes in the future.

The generator isn't perfect yet and may produce errors, but I hope it will be continuously improved and refined over time.

---

## 🛠 Installation

This project consists of two separate components:
1. A modified version of OSRM tailored for rail transport.
2. A GTFS shape generator that reads GTFS files and overlays shapes onto them.

---

## 🚉 OSRM Lua Profile for Trains

To get started, install the following dependencies:

- Docker daemon  
- Osmium

More details: [railnova/osrm-train-profile](https://github.com/railnova/osrm-train-profile)

### 🔧 Setup Instructions
```bash
git clone https://github.com/railnova/osrm-train-profile.git
cd osrm-train-profile
make all
make serve
```
### 🧩 Shaper Maker Usage
```bash
git clone https://github.com/jotazet/gtfs-shaper-maker.git
cd gtfs-shaper-maker
```
### 🐍 Create and Activate a Virtual Environment
```bash
python -m venv env
source env/bin/activate
```
### 📦 Install Dependencies
```bash
pip install -r requirements.txt
```
### 🚀 Run the Program
```bash
python main.py gtfs-file-name.zip
```
## ⚠️ Notes
- This tool is still under development.
- Errors may occur, especially with complex GTFS datasets.
- Contributions, bug reports, and suggestions are welcome!