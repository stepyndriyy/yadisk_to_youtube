#!/usr/bin/env python3
"""
Yandex Disk to YouTube Video Transfer Script

Downloads .mov videos from a Yandex Disk public folder and uploads them to YouTube.
Processes videos one at a time to manage storage efficiently.
"""

import os
import sys
import time
import logging
import json
from pathlib import Path
from typing import List, Dict, Optional
from urllib.parse import urlparse, parse_qs

import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('transfer.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# YouTube API settings
SCOPES = ['https://www.googleapis.com/auth/youtube.upload']
YOUTUBE_API_SERVICE_NAME = 'youtube'
YOUTUBE_API_VERSION = 'v3'

# Configuration
YANDEX_DISK_PUBLIC_KEY = os.getenv('YANDEX_DISK_PUBLIC_KEY', 'https://disk.yandex.ru/d/Y1yHasRikR9qBQ')
YANDEX_OAUTH_TOKEN = os.getenv('YANDEX_OAUTH_TOKEN', '')
YOUTUBE_CLIENT_SECRETS_FILE = os.getenv('YOUTUBE_CLIENT_SECRETS_FILE', 'client_secret.json')
YOUTUBE_TOKEN_FILE = 'youtube_token.json'
UPLOADED_VIDEOS_LOG = 'uploaded_videos.json'


class YandexDiskClient:
    """Client for accessing Yandex Disk files."""
    
    def __init__(self, public_key: str, oauth_token: Optional[str] = None):
        self.public_key = public_key
        self.oauth_token = oauth_token
        self.base_url = 'https://cloud-api.yandex.net/v1/disk'
        
    def _get_headers(self) -> Dict[str, str]:
        """Get headers for API requests."""
        headers = {}
        if self.oauth_token:
            headers['Authorization'] = f'OAuth {self.oauth_token}'
        return headers
    
    def _extract_public_key(self) -> str:
        """Extract public key from Yandex Disk URL."""
        # Extract the key from URL like https://disk.yandex.ru/d/Y1yHasRikR9qBQ
        parsed = urlparse(self.public_key)
        if parsed.path.startswith('/d/'):
            return parsed.path[3:]  # Remove '/d/'
        return self.public_key
    
    def list_files(self) -> List[Dict]:
        """
        List all files in the public folder.
        Returns list of file dictionaries with 'name', 'path', 'size', etc.
        """
        public_key = self._extract_public_key()
        url = f'{self.base_url}/public/resources'
        params = {'public_key': public_key}
        headers = self._get_headers()
        
        try:
            response = requests.get(url, params=params, headers=headers, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            files = []
            if '_embedded' in data and 'items' in data['_embedded']:
                for item in data['_embedded']['items']:
                    if item.get('type') == 'file':
                        files.append(item)
            
            logger.info(f"Found {len(files)} files in Yandex Disk folder")
            return files
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error listing files from Yandex Disk: {e}")
            raise
    
    def get_download_link(self, file_path: str) -> str:
        """
        Get download link for a specific file.
        
        Args:
            file_path: Path to the file in Yandex Disk
            
        Returns:
            Direct download URL
        """
        public_key = self._extract_public_key()
        url = f'{self.base_url}/public/resources/download'
        params = {
            'public_key': public_key,
            'path': file_path
        }
        headers = self._get_headers()
        
        try:
            response = requests.get(url, params=params, headers=headers, timeout=30)
            response.raise_for_status()
            data = response.json()
            return data['href']
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting download link for {file_path}: {e}")
            raise
    
    def download_file(self, download_url: str, local_path: str) -> bool:
        """
        Download a file from Yandex Disk.
        
        Args:
            download_url: Direct download URL
            local_path: Local file path to save to
            
        Returns:
            True if successful, False otherwise
        """
        max_retries = 3
        retry_delay = 5
        
        for attempt in range(max_retries):
            try:
                logger.info(f"Downloading to {local_path} (attempt {attempt + 1}/{max_retries})...")
                
                response = requests.get(download_url, stream=True, timeout=300)
                response.raise_for_status()
                
                total_size = int(response.headers.get('content-length', 0))
                downloaded = 0
                
                os.makedirs(os.path.dirname(local_path) if os.path.dirname(local_path) else '.', exist_ok=True)
                
                with open(local_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total_size > 0:
                                percent = (downloaded / total_size) * 100
                                if downloaded % (10 * 1024 * 1024) == 0:  # Log every 10MB
                                    logger.info(f"Downloaded {downloaded / (1024*1024):.1f} MB / {total_size / (1024*1024):.1f} MB ({percent:.1f}%)")
                
                logger.info(f"Successfully downloaded {local_path} ({downloaded / (1024*1024):.1f} MB)")
                return True
                
            except requests.exceptions.RequestException as e:
                logger.warning(f"Download attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (attempt + 1))
                else:
                    logger.error(f"Failed to download file after {max_retries} attempts")
                    return False
        
        return False


class YouTubeUploader:
    """Client for uploading videos to YouTube."""
    
    def __init__(self, client_secrets_file: str):
        self.client_secrets_file = client_secrets_file
        self.youtube = None
        self._authenticate()
    
    def _authenticate(self):
        """Authenticate with YouTube API and build service object."""
        creds = None
        
        # Try to load existing credentials
        if os.path.exists(YOUTUBE_TOKEN_FILE):
            try:
                creds = Credentials.from_authorized_user_file(YOUTUBE_TOKEN_FILE, SCOPES)
            except Exception as e:
                logger.warning(f"Could not load existing credentials: {e}")
        
        # If there are no valid credentials, get new ones
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as e:
                    logger.warning(f"Could not refresh credentials: {e}")
                    creds = None
            
            if not creds:
                if not os.path.exists(self.client_secrets_file):
                    logger.error(f"Client secrets file not found: {self.client_secrets_file}")
                    logger.error("Please download client_secret.json from Google Cloud Console")
                    sys.exit(1)
                
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.client_secrets_file, SCOPES)
                creds = flow.run_local_server(port=0)
            
            # Save credentials for next run
            with open(YOUTUBE_TOKEN_FILE, 'w') as token:
                token.write(creds.to_json())
        
        self.youtube = build(YOUTUBE_API_SERVICE_NAME, YOUTUBE_API_VERSION, credentials=creds)
        logger.info("Successfully authenticated with YouTube API")
    
    def upload_video(self, file_path: str, title: Optional[str] = None) -> Optional[str]:
        """
        Upload a video to YouTube.
        
        Args:
            file_path: Path to the video file
            title: Video title (defaults to filename without extension)
            
        Returns:
            YouTube video ID if successful, None otherwise
        """
        if not title:
            title = Path(file_path).stem
        
        max_retries = 3
        retry_delay = 10
        
        for attempt in range(max_retries):
            try:
                logger.info(f"Uploading {file_path} to YouTube (attempt {attempt + 1}/{max_retries})...")
                
                body = {
                    'snippet': {
                        'title': title,
                        'description': f'Uploaded from Yandex Disk: {Path(file_path).name}',
                        'tags': ['Yandex Disk', 'API Upload'],
                        'categoryId': '22'  # People & Blogs
                    },
                    'status': {
                        'privacyStatus': 'public'
                    }
                }
                
                media = MediaFileUpload(
                    file_path,
                    chunksize=-1,
                    resumable=True,
                    mimetype='video/quicktime'
                )
                
                insert_request = self.youtube.videos().insert(
                    part=','.join(body.keys()),
                    body=body,
                    media_body=media
                )
                
                response = self._resumable_upload(insert_request)
                
                video_id = response['id']
                logger.info(f"Successfully uploaded video: {title} (ID: {video_id})")
                return video_id
                
            except HttpError as e:
                error_content = json.loads(e.content.decode('utf-8'))
                error_reason = error_content.get('error', {}).get('errors', [{}])[0].get('reason', 'unknown')
                
                if error_reason == 'quotaExceeded':
                    logger.error("YouTube API quota exceeded. Please try again later.")
                    sys.exit(1)
                elif error_reason == 'rateLimitExceeded':
                    logger.warning(f"Rate limit exceeded. Waiting {retry_delay * (attempt + 1)} seconds...")
                    if attempt < max_retries - 1:
                        time.sleep(retry_delay * (attempt + 1))
                        continue
                else:
                    logger.error(f"YouTube API error: {e}")
                    if attempt < max_retries - 1:
                        time.sleep(retry_delay * (attempt + 1))
                        continue
                    return None
                    
            except Exception as e:
                logger.error(f"Unexpected error uploading video: {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (attempt + 1))
                    continue
                return None
        
        return None
    
    def _resumable_upload(self, insert_request):
        """Execute a resumable upload."""
        response = None
        error = None
        retry = 0
        
        while response is None:
            try:
                status, response = insert_request.next_chunk()
                if response is not None:
                    if 'id' in response:
                        return response
                    else:
                        raise Exception(f"The upload failed with an unexpected response: {response}")
            except HttpError as e:
                if e.resp.status in [500, 502, 503, 504]:
                    error = f"A retriable HTTP error {e.resp.status} occurred:\n{e.content}"
                else:
                    raise
            except Exception as e:
                error = f"A retriable error occurred: {e}"
            
            if error is not None:
                logger.warning(error)
                retry += 1
                if retry > 3:
                    raise Exception(f"No longer attempting to retry. {error}")
                
                max_sleep = 2 ** retry
                sleep_seconds = min(max_sleep, 60)
                logger.info(f"Sleeping {sleep_seconds} seconds and then retrying...")
                time.sleep(sleep_seconds)


def load_uploaded_videos() -> set:
    """Load set of already uploaded video filenames."""
    if os.path.exists(UPLOADED_VIDEOS_LOG):
        try:
            with open(UPLOADED_VIDEOS_LOG, 'r') as f:
                data = json.load(f)
                return set(data.get('uploaded_files', []))
        except Exception as e:
            logger.warning(f"Could not load uploaded videos log: {e}")
    return set()


def save_uploaded_video(filename: str, video_id: str):
    """Save uploaded video info to log file."""
    data = {'uploaded_files': [], 'videos': {}}
    
    if os.path.exists(UPLOADED_VIDEOS_LOG):
        try:
            with open(UPLOADED_VIDEOS_LOG, 'r') as f:
                data = json.load(f)
        except Exception:
            pass
    
    if 'uploaded_files' not in data:
        data['uploaded_files'] = []
    if 'videos' not in data:
        data['videos'] = {}
    
    data['uploaded_files'].append(filename)
    data['videos'][filename] = {
        'video_id': video_id,
        'uploaded_at': time.strftime('%Y-%m-%d %H:%M:%S')
    }
    
    with open(UPLOADED_VIDEOS_LOG, 'w') as f:
        json.dump(data, f, indent=2)


def main():
    """Main function to orchestrate the transfer process."""
    logger.info("Starting Yandex Disk to YouTube transfer")
    
    # Initialize clients
    try:
        yandex_client = YandexDiskClient(YANDEX_DISK_PUBLIC_KEY, YANDEX_OAUTH_TOKEN)
        youtube_uploader = YouTubeUploader(YOUTUBE_CLIENT_SECRETS_FILE)
    except Exception as e:
        logger.error(f"Failed to initialize clients: {e}")
        sys.exit(1)
    
    # Load already uploaded videos
    uploaded_files = load_uploaded_videos()
    logger.info(f"Found {len(uploaded_files)} already uploaded videos")
    
    # List files from Yandex Disk
    try:
        files = yandex_client.list_files()
    except Exception as e:
        logger.error(f"Failed to list files from Yandex Disk: {e}")
        sys.exit(1)
    
    # Filter .mov files
    mov_files = [f for f in files if f['name'].lower().endswith('.mov')]
    logger.info(f"Found {len(mov_files)} .mov files to process")
    
    if not mov_files:
        logger.info("No .mov files found. Exiting.")
        return
    
    # Process each video
    successful_uploads = 0
    failed_uploads = 0
    
    for file_info in mov_files:
        filename = file_info['name']
        file_path = file_info['path']
        
        # Skip if already uploaded
        if filename in uploaded_files:
            logger.info(f"Skipping {filename} (already uploaded)")
            continue
        
        logger.info(f"\n{'='*60}")
        logger.info(f"Processing: {filename}")
        logger.info(f"{'='*60}")
        
        # Get download link
        try:
            download_url = yandex_client.get_download_link(file_path)
        except Exception as e:
            logger.error(f"Failed to get download link for {filename}: {e}")
            failed_uploads += 1
            continue
        
        # Download file
        local_path = os.path.join(os.getcwd(), filename)
        if not yandex_client.download_file(download_url, local_path):
            logger.error(f"Failed to download {filename}")
            failed_uploads += 1
            continue
        
        # Upload to YouTube
        video_id = youtube_uploader.upload_video(local_path, title=Path(filename).stem)
        
        if video_id:
            # Save upload record
            save_uploaded_video(filename, video_id)
            successful_uploads += 1
            
            # Delete local file
            try:
                os.remove(local_path)
                logger.info(f"Deleted local file: {local_path}")
            except Exception as e:
                logger.warning(f"Could not delete local file {local_path}: {e}")
        else:
            logger.error(f"Failed to upload {filename} to YouTube")
            failed_uploads += 1
            # Keep the file for manual retry
    
    # Summary
    logger.info(f"\n{'='*60}")
    logger.info("Transfer complete!")
    logger.info(f"Successful uploads: {successful_uploads}")
    logger.info(f"Failed uploads: {failed_uploads}")
    logger.info(f"{'='*60}")


if __name__ == '__main__':
    main()

