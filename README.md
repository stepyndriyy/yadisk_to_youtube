# Yandex Disk to YouTube Video Transfer

This Python script downloads `.mov` videos from a Yandex Disk public folder and uploads them to YouTube as public videos. Videos are processed one at a time (download → upload → delete) to efficiently manage storage space.

## Features

- Downloads videos from Yandex Disk public folders
- Uploads videos to YouTube as public videos
- Processes videos one at a time to minimize storage usage
- Tracks uploaded videos to avoid duplicates
- Handles errors with retry logic
- Resumable uploads for large files
- Comprehensive logging

## Prerequisites

- Python 3.7 or higher
- Access to the Yandex Disk public folder
- Google Cloud account with YouTube Data API enabled
- At least 40GB free storage (for temporary downloads)

## Installation

1. Clone or download this repository

2. Install required Python packages:
```bash
pip install -r requirements.txt
```

## Setting Up Credentials

### YouTube API Credentials (Required)

1. **Create a Google Cloud Project:**
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Click "Create Project" and provide a project name
   - Wait for the project to be created

2. **Enable YouTube Data API v3:**
   - In the project dashboard, go to "APIs & Services" > "Library"
   - Search for "YouTube Data API v3"
   - Click on it and click "Enable"

3. **Configure OAuth Consent Screen:**
   - Go to "APIs & Services" > "OAuth consent screen"
   - Select "External" (unless you have a Google Workspace account)
   - Fill in the required information:
     - App name: Your application name (e.g., "Video Transfer")
     - User support email: Your email address
     - Developer contact information: Your email address
   - Click "Save and Continue"
   - On the "Scopes" page, click "Add or Remove Scopes"
   - Search for and add: `https://www.googleapis.com/auth/youtube.upload`
   - Click "Update" then "Save and Continue"
   - On the "Test users" page, add your Google account email if testing
   - Click "Save and Continue" through the remaining pages

4. **Create OAuth Client ID:**
   - Go to "APIs & Services" > "Credentials"
   - Click "Create Credentials" > "OAuth client ID"
   - Select "Desktop app" as the application type
   - Give it a name (e.g., "Video Transfer Client")
   - Click "Create"
   - Click "Download" to download the `client_secret.json` file
   - Save this file in the same directory as `transfer.py`

### Yandex Disk Credentials (Optional)

The script will first attempt to access the public folder directly. If that fails, you may need an OAuth token.

1. **Register Your Application:**
   - Go to [Yandex OAuth page](https://oauth.yandex.ru/client/new)
   - Log in with your Yandex account
   - Fill in the required details:
     - **Application name:** Choose a descriptive name (e.g., "Video Transfer")
     - **Platforms:** Select "Web services"
     - **Callback URI:** Enter `https://oauth.yandex.ru/verification_code`
   - In the "Access rights" section, add:
     - `Yandex.Disk: Read only` (or `Yandex.Disk: Full access` if needed)
   - Click "Create"

2. **Get OAuth Token:**
   - After registration, note your **Client ID**
   - Construct the authorization URL:
     ```
     https://oauth.yandex.ru/authorize?response_type=token&client_id=YOUR_CLIENT_ID
     ```
     Replace `YOUR_CLIENT_ID` with your actual Client ID
   - Open this URL in your browser
   - Authorize the application
   - After authorization, you'll be redirected to a page with the token in the URL
   - Copy the `access_token` value from the URL fragment (the part after `#`)

## Configuration

Create a `.env` file in the project directory (or set environment variables):

```bash
# Yandex Disk Configuration
YANDEX_DISK_PUBLIC_KEY=https://disk.yandex.ru/d/Y1yHasRikR9qBQ
YANDEX_OAUTH_TOKEN=your_yandex_token_here  # Optional

# YouTube Configuration
YOUTUBE_CLIENT_SECRETS_FILE=client_secret.json
```

If you don't create a `.env` file, the script will use default values:
- `YANDEX_DISK_PUBLIC_KEY`: Uses the URL from the example
- `YOUTUBE_CLIENT_SECRETS_FILE`: Looks for `client_secret.json` in the current directory

## Usage

1. Make sure `client_secret.json` is in the project directory
2. (Optional) Create `.env` file with your configuration
3. Run the script:
```bash
python transfer.py
```

The script will:
1. Authenticate with YouTube (will open browser on first run)
2. List all `.mov` files in the Yandex Disk folder
3. For each video:
   - Download it to local storage
   - Upload it to YouTube as a public video
   - Delete the local file after successful upload
   - Log the upload in `uploaded_videos.json`

## Files Created

- `transfer.log` - Detailed log of all operations
- `youtube_token.json` - Saved YouTube OAuth token (created automatically)
- `uploaded_videos.json` - Tracks which videos have been uploaded

## Troubleshooting

### "Client secrets file not found"
- Make sure `client_secret.json` is in the same directory as `transfer.py`
- Or set the `YOUTUBE_CLIENT_SECRETS_FILE` environment variable with the correct path

### "Failed to list files from Yandex Disk"
- The public folder might require authentication
- Set `YANDEX_OAUTH_TOKEN` in your `.env` file
- Make sure the public folder URL is correct

### "YouTube API quota exceeded"
- YouTube has daily quotas for API usage
- Wait 24 hours and try again
- Consider processing videos in smaller batches

### "Rate limit exceeded"
- The script will automatically retry with exponential backoff
- If it continues to fail, wait a few minutes and try again

### Videos not uploading
- Check `transfer.log` for detailed error messages
- Ensure videos are valid `.mov` files
- Check your internet connection
- Verify YouTube API quota hasn't been exceeded

## Notes

- Videos are uploaded as **public** by default
- Video titles are set to the filename (without extension)
- The script skips videos that have already been uploaded (tracked in `uploaded_videos.json`)
- If upload fails, the local file is kept for manual retry
- Large videos may take significant time to upload
- The script requires internet connectivity throughout execution

## Remote Machine Usage

This script is designed to run on remote machines:

1. Transfer all files to the remote machine:
   - `transfer.py`
   - `requirements.txt`
   - `client_secret.json`
   - `.env` (optional)

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. On first run, YouTube authentication will open a browser. If you're SSH'd into a remote machine:
   - You can use port forwarding: `ssh -L 8080:localhost:8080 user@remote`
   - Or use `run_local_server` with `port=8080` and manually set up port forwarding
   - Or copy the authorization URL and complete it on your local machine, then copy the token

4. After first authentication, `youtube_token.json` will be saved and reused

## License

This script is provided as-is for personal use.

