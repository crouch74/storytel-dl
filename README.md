# Storytel Downloader (Python Port)

A CLI tool for downloading audiobooks and ebooks from Storytel, organizing them in an Audiobookshelf-friendly structure.

## ✨ Features

- 🎧 **Audiobook Download**: Downloads audiobooks as MP3 files.
- 📚 **Ebook Download**: Downloads ebooks as EPUB files.
- 📁 **Organized Structure**: Saves files in `<Author>/<Title>/` structure.
- 📘 **Metadata Generation**: Creates `metadata.json` compatible with Audiobookshelf.
- 🔐 **Secure Auth**: Encrypts passwords for API calls and stores credentials securely in `.env`.
- 📊 **Progress Tracking**: Uses `tqdm` for overall and per-file progress bars.
- 🛠️ **Interactive Mode**: Guided setup for first-time users.

## 🚀 Getting Started

### Prerequisites

- Python 3.8+
- Active Storytel account

### Installation

1. **Clone the repository** (or navigate to the project directory).
2. **Run the setup script**:
   ```bash
   chmod +x setup.sh
   ./setup.sh
   ```
3. **Activate the virtual environment**:
   ```bash
   source .venv/bin/activate
   ```

## 📖 Usage

### Interactive Mode (Recommended)

Run the tool without arguments or with `--interactive` to be guided through the download process:

```bash
python -m src.main --interactive
```

### Command Line Arguments

```bash
python -m src.main [OPTIONS]

Options:
  --mode {audio,ebook,both}  Download mode (default: both)
  --input PATH               Path to text file with Storytel URLs (default: ../audiobook_urls.txt)
  --out PATH                 Library output root (default: ./library)
  --debug                    Enable debug level logging
  --help                     Show this help message
```

### URL Format

The input text file should contain one Storytel book URL per line.
Example: `https://www.storytel.com/se/sv/books/title-123456`

## 📂 Output Structure

The tool organizes your library automatically:

```text
library/
  └── Author/
      └── Book Title/
          ├── audio.mp3
          ├── ebook.epub
          └── metadata.json
```

## 🔐 Credentials

Credentials are loaded from the `.env` file. If missing, the tool will prompt you securely (using `getpass` for the password) and save them for future use.

**Important**: Your password is encrypted before being sent to the Storytel API using the same logic as the official apps.

## 📝 Logging

The tool uses structured logging with timestamps and emojis:
- 🔐 Auth
- 📘 Metadata/Processing
- 🎧 Audio
- 📚 Ebook
- 📥 Download
- ✅ Success
- ⚠️ Warning
- ❌ Error
