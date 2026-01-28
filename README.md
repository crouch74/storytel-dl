# Storytel Downloader (Python Port)

A CLI tool for downloading audiobooks and ebooks from Storytel, organizing them in an Audiobookshelf-friendly structure.

## ✨ Features

- 🎧 **Audiobook Download**: Downloads audiobooks and converts them to M4B with chapters.
- ⚡ **Fast Conversion**: Near-instant M4B conversion using `--fast-copy` (stream copy).
- 📚 **Ebook Download**: Downloads ebooks as EPUB files.
- 🖼️ **Cover Art**: Automatically downloads the book cover as `cover.jpg`.
- 📁 **Organized Structure**: Saves files using book titles in `<Author>/<Title>/` structure.
- ⏭️ **Smart Skip**: Automatically skips already downloaded files (m4b/epub/jpg).
- 🔄 **Auto-Resume**: Automatically converts existing MP3 downloads to M4B if the M4B is missing.
- 📘 **Metadata Generation**: Creates `metadata.json` compatible with Audiobookshelf.
- 🔐 **Secure Auth**: Encrypts passwords for API calls and stores credentials securely in `.env`.
- 📊 **Progress Tracking**: Uses `tqdm` for overall and per-file progress bars.
- 🛠️ **Interactive Mode**: Guided setup for first-time users.
- 🐞 **Debugger Support**: Pre-configured VS Code launch profiles.
- 🐳 **Docker Support**: Runs in a container with all dependencies included.

## 🚀 Getting Started

### 🐳 Docker (Recommended)

The easiest way to run the tool without Worrying about dependencies (like `ffmpeg`) is using Docker:

1. **Run the setup script**:
   ```bash
   chmod +x run.sh
   ./run.sh --interactive
   ```

### 🐍 Local Installation (Manual)

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
  --mode {audio,ebook,both,fix-chapters}  Download mode (default: both)
  --input PATH                            Path to text file with Storytel URLs (default: ../audiobook_urls.txt)
  --out PATH                              Library output root (default: ./library)
  --debug                                 Enable debug level logging
  --help                                  Show this help message
```

### 🛠️ Repairing Existing Downloads

If you have books that were downloaded with missing chapter titles (e.g., "Chapter None"), you can fix them using the repair mode:

```bash
python -m src.main --mode fix-chapters
```

- **Fully Local**: Works without an internet connection or Storytel login.
- **Repair Utility**: Scans your files and replaces empty or "None" chapter titles with generic "Chapter N" labels.
- **Lossless**: Uses stream copying (metadata update only), ensuring no quality loss.
- **Recursive**: Scans all subdirectories in your `--out` path (default: `./library`).
- **Fast**: Processes each book in seconds.

### URL Format

The input text file should contain one Storytel book URL per line.
Example: `https://www.storytel.com/se/sv/books/title-123456`

## 📂 Output Structure

The tool organizes your library automatically:

```text
library/
  └── Author/
      └── Book Title/
          ├── Book Title.m4b (with chapters)
          ├── Book Title.epub
          ├── cover.jpg
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
- 🖼️ Cover
- 📥 Download
- ⏭️ Skip/Resume
- ⚙️ Processing/Conversion
- ✅ Success
- ⚠️ Warning
- ❌ Error
