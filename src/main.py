import os
from dotenv import load_dotenv
import re
import json
import requests
from office365.graph_client import GraphClient
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from azure.storage.blob import BlobServiceClient
import logging
from logging.handlers import RotatingFileHandler
from concurrent.futures import ThreadPoolExecutor
import concurrent.futures
import time
from azure.core.exceptions import ResourceExistsError, HttpResponseError
from enum import Enum
from collections import Counter
from threading import Lock
from datetime import datetime, timedelta, timezone
from azure.identity import ManagedIdentityCredential, DefaultAzureCredential

# Configure Logging
def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)  # Capture all levels

    # Avoid adding handlers multiple times
    if not logger.handlers:
        # Create handlers
        c_handler = logging.StreamHandler()  # Console handler
        log_file = os.path.join(os.path.dirname(__file__), 'download_upload.log')
        f_handler = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=5)  # File handler with rotation

        c_handler.setLevel(logging.INFO)  # Console handler set to INFO
        f_handler.setLevel(logging.DEBUG)  # File handler set to DEBUG

        # Create formatters and add to handlers
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s')
        c_handler.setFormatter(formatter)
        f_handler.setFormatter(formatter)

        # Add handlers to the root logger
        logger.addHandler(c_handler)
        logger.addHandler(f_handler)

    return logger

logger = setup_logging()
logger.debug("Logging is configured and script has started.")

# Load environment variables from the .env file if present
load_dotenv()

# Retrieve values from environment variables
# TENANT, CLIENT_ID, CLIENT_SECRET, AZURE_CONNECTION_STRING are no longer needed
AZURE_BLOB_CONTAINER_NAME = os.getenv("AZURE_BLOB_CONTAINER_NAME")
AZURE_STORAGE_ACCOUNT_NAME = os.getenv("AZURE_STORAGE_ACCOUNT_NAME")
FOLDER_PATH = os.getenv("FOLDER_PATH")
SITE_URL = os.getenv("SITE_URL")
FILENAME_PATTERNS_JSON = os.getenv("FILENAME_PATTERNS")  # Expecting a JSON string

# Validate environment variables
def validate_environment_variables():
    required_vars = {
        "AZURE_BLOB_CONTAINER_NAME": AZURE_BLOB_CONTAINER_NAME,
        "AZURE_STORAGE_ACCOUNT_NAME": AZURE_STORAGE_ACCOUNT_NAME,
        "FILENAME_PATTERNS": FILENAME_PATTERNS_JSON,
        "SITE_URL": SITE_URL,
        "FOLDER_PATH": FOLDER_PATH
    }

    missing_vars = [var for var, value in required_vars.items() if not value]
    if missing_vars:
        logger.critical(f"Missing required environment variables: {', '.join(missing_vars)}")
        raise EnvironmentError(f"Missing required environment variables: {', '.join(missing_vars)}")

validate_environment_variables()

# Parse filename_patterns from JSON
try:
    filename_patterns_data = json.loads(FILENAME_PATTERNS_JSON)
    filename_patterns = []
    for item in filename_patterns_data:
        pattern = item.get("pattern")
        target_folder = item.get("target_folder")
        if not pattern or not target_folder:
            logger.warning(f"Invalid pattern item: {item}. Skipping.")
            continue
        try:
            compiled_pattern = re.compile(pattern)
            filename_patterns.append((compiled_pattern, target_folder))
        except re.error as e:
            logger.error(f"Invalid regex pattern '{pattern}': {e}. Skipping.")
except json.JSONDecodeError as e:
    logger.critical(f"Failed to parse FILENAME_PATTERNS as JSON: {e}")
    raise
except Exception as e:
    logger.critical(f"Unexpected error parsing FILENAME_PATTERNS: {e}")
    raise

logger.debug(f"Parsed filename_patterns: {filename_patterns}")

# Define an enumeration for upload statuses
class UploadStatus(Enum):
    UPLOADED = 'uploaded'
    SKIPPED = 'skipped'
    FAILED = 'failed'

def acquire_token():
    try:
        credential = ManagedIdentityCredential()
        token = credential.get_token("https://graph.microsoft.com/.default")
        access_token = token.token
        logger.debug("Successfully acquired access token via Managed Identity.")
        return {"access_token": access_token}
    except Exception as e:
        logger.exception("Exception occurred while acquiring token via Managed Identity.")
        raise e

def create_session_with_retries(total_retries=3, backoff_factor=1, status_forcelist=(500, 502, 504)):
    try:
        session = requests.Session()
        retry = Retry(
            total=total_retries,
            read=total_retries,
            connect=total_retries,
            backoff_factor=backoff_factor,
            status_forcelist=status_forcelist,
            allowed_methods=["HEAD", "GET", "OPTIONS"]
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        logger.debug("HTTP session with retry logic created.")
        return session
    except Exception as e:
        logger.exception("Exception occurred while creating HTTP session.")
        raise e

def connect_to_azure_blob():
    try:
        # Initialize DefaultAzureCredential (includes ManagedIdentityCredential)
        credential = DefaultAzureCredential()

        # Construct the Blob service URL
        blob_service_url = f"https://{AZURE_STORAGE_ACCOUNT_NAME}.blob.core.windows.net/"

        # Create BlobServiceClient with Managed Identity credential
        blob_service_client = BlobServiceClient(
            account_url=blob_service_url,
            credential=credential
        )

        # Get ContainerClient
        container_client = blob_service_client.get_container_client(AZURE_BLOB_CONTAINER_NAME)

        # Create container if it doesn't exist
        try:
            container_client.create_container()
            logger.info(f"Created Azure Blob container: {AZURE_BLOB_CONTAINER_NAME}")
        except ResourceExistsError:
            logger.info(f"Connected to existing Azure Blob container: {AZURE_BLOB_CONTAINER_NAME}")

        return container_client
    except Exception as e:
        logger.exception("Failed to connect to Azure Blob Storage.")
        raise e

def upload_stream_to_blob(response_stream, blob_name, container_client, target_folder, overwrite=False, retries=3):
    blob_path = f"{target_folder}/{blob_name}"
    blob_client = container_client.get_blob_client(blob_path)

    try:
        if blob_client.exists():
            if not overwrite:
                logger.info(f"Blob '{blob_path}' already exists. Skipping upload.")
                return UploadStatus.SKIPPED  # Indicate that the upload was skipped
            else:
                logger.info(f"Blob '{blob_path}' exists and will be overwritten.")
    except HttpResponseError as e:
        logger.error(f"Failed to check existence of blob '{blob_path}': {e}")
        # Decide whether to proceed with upload or abort
        # For now, we'll proceed with upload

    for attempt in range(retries):
        try:
            # Upload the stream directly to Azure Blob
            blob_client.upload_blob(response_stream, overwrite=overwrite)
            action = "Overwritten" if overwrite else "Uploaded"
            logger.info(f"{action} blob: {blob_path}")
            return UploadStatus.UPLOADED  # Indicate a successful upload
        except ResourceExistsError:
            logger.error(f"Blob '{blob_path}' already exists and overwrite is disabled.")
            return UploadStatus.SKIPPED  # Indicate that the upload was skipped due to existing blob
        except HttpResponseError as e:
            if e.error_code == "BlobOperationNotSupportedForBlobCreatedBySftp":
                logger.error(f"Operation not supported for blob '{blob_path}': {e}")
                return UploadStatus.FAILED  # Indicate a failure that cannot be retried
            else:
                logger.error(f"Attempt {attempt + 1} - HTTP error during upload of '{blob_path}': {e}")
        except Exception as e:
            logger.error(f"Attempt {attempt + 1} - Unexpected error during upload of '{blob_path}': {e}")

        if attempt < retries - 1:
            wait_time = 2 ** attempt
            logger.info(f"Retrying upload in {wait_time} seconds...")
            time.sleep(wait_time)  # Exponential backoff
        else:
            logger.error(f"All retry attempts failed for '{blob_path}'.")

    return UploadStatus.FAILED  # Indicate that the upload failed after retries

def download_and_upload_pdf(drive_item, container_client, target_folder, session, overwrite=False):
    download_url = drive_item.properties.get("@microsoft.graph.downloadUrl", None)
    if download_url:
        try:
            logger.debug(f"Starting download for: {drive_item.name}")
            with session.get(download_url, stream=True, timeout=30) as response:
                response.raise_for_status()
                # Upload directly to Azure Blob
                upload_status = upload_stream_to_blob(response.raw, drive_item.name, container_client, target_folder, overwrite=overwrite)
            if upload_status == UploadStatus.UPLOADED:
                action = "Overwritten and uploaded" if overwrite else "Uploaded"
                logger.info(f"Successfully {action}: {drive_item.name}")
                return UploadStatus.UPLOADED
            elif upload_status == UploadStatus.SKIPPED:
                logger.info(f"Upload skipped as blob already exists and overwrite was not needed: {drive_item.name}")
                return UploadStatus.SKIPPED
            else:
                logger.error(f"Failed to upload: {drive_item.name}")
                return UploadStatus.FAILED
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to download {drive_item.name}: {e}")
            return UploadStatus.FAILED
    else:
        logger.warning(f"No downloadUrl found for {drive_item.name}, cannot download.")
        return UploadStatus.FAILED

def traverse_folders(folder_item, patterns, max_files, session, container_client, executor, futures, pre_skipped, pre_skipped_lock):
    if max_files <= 0:
        return 0

    folder_name = folder_item.name if folder_item.name else "(No Name)"
    logger.info(f"Entering folder: {folder_name}")

    try:
        children = folder_item.children.get().execute_query()
        logger.debug(f"Retrieved {len(children)} items from folder: {folder_name}")
    except Exception as e:
        logger.error(f"Failed to retrieve children for folder {folder_name}: {e}")
        return 0

    files_processed = 0

    for item in children:
        if files_processed >= max_files:
            logger.debug("Maximum file download limit reached.")
            break

        is_file = (item.file is not None)
        is_folder = (item.folder is not None)
        child_count = item.folder.childCount if (item.folder and item.folder.childCount is not None) else 0

        logger.info(f"Found item: {item.name} | IsFile: {is_file}, IsFolder: {is_folder}, ChildCount: {child_count}")

        if is_folder and child_count > 0:
            logger.info(f"Found subfolder: {item.name}")
            downloaded_in_subfolder = traverse_folders(
                item, patterns, max_files - files_processed, session, container_client, executor, futures, pre_skipped, pre_skipped_lock
            )
            files_processed += downloaded_in_subfolder
        elif is_file:
            for pattern, target_folder in patterns:
                if pattern.match(item.name):
                    blob_path = f"{target_folder}/{item.name}"
                    blob_client = container_client.get_blob_client(blob_path)

                    # Retrieve the last modified date of the SharePoint file
                    last_modified = item.properties.get("lastModifiedDateTime", None)
                    source_last_modified = None  # Initialize source last modified

                    if last_modified:
                        try:
                            if isinstance(last_modified, str):
                                # Parse string to datetime
                                source_last_modified = datetime.strptime(last_modified, "%Y-%m-%dT%H:%M:%SZ")
                                source_last_modified = source_last_modified.replace(tzinfo=timezone.utc)
                            elif isinstance(last_modified, datetime):
                                # Ensure datetime object is timezone-aware and in UTC
                                if last_modified.tzinfo is None:
                                    source_last_modified = last_modified.replace(tzinfo=timezone.utc)
                                else:
                                    source_last_modified = last_modified.astimezone(timezone.utc)
                            else:
                                logger.warning(f"Unexpected type for lastModifiedDateTime: {type(last_modified)} for {item.name}")
                                source_last_modified = None

                            logger.debug(f"File '{item.name}' last modified on {source_last_modified} UTC.")
                        except Exception as e:
                            logger.error(f"Error processing lastModifiedDateTime for {item.name}: {e}")
                            source_last_modified = None
                    else:
                        logger.warning(f"No lastModifiedDateTime found for {item.name}. Cannot determine if overwrite is needed.")

                    try:
                        blob_exists = blob_client.exists()
                    except HttpResponseError as e:
                        logger.error(f"Failed to check existence of blob '{blob_path}': {e}")
                        # Decide whether to proceed with upload or skip
                        # For now, we'll proceed with upload
                        blob_exists = False

                    overwrite = False  # Default to not overwrite

                    if blob_exists:
                        try:
                            blob_properties = blob_client.get_blob_properties()
                            blob_last_modified = blob_properties.last_modified  # This is timezone-aware
                            logger.debug(f"Blob '{blob_path}' last modified on {blob_last_modified} UTC.")

                            if source_last_modified:
                                if source_last_modified > blob_last_modified:
                                    overwrite = True
                                    logger.info(f"Source file '{item.name}' is newer than blob '{blob_path}'. It will be overwritten.")
                                else:
                                    logger.info(f"Source file '{item.name}' is not newer than blob '{blob_path}'. Skipping upload.")
                                    with pre_skipped_lock:
                                        pre_skipped[0] += 1
                                    files_processed += 1
                                    break  # Skip to next item
                            else:
                                logger.warning(f"Cannot determine if source file '{item.name}' is newer. Skipping upload.")
                                with pre_skipped_lock:
                                    pre_skipped[0] += 1
                                files_processed += 1
                                break  # Skip to next item
                        except Exception as e:
                            logger.error(f"Error retrieving blob properties for '{blob_path}': {e}")
                            # Decide whether to proceed with upload or skip
                            # For now, we'll skip to avoid potential overwrites
                            with pre_skipped_lock:
                                pre_skipped[0] += 1
                            files_processed += 1
                            break  # Skip to next item
                    else:
                        overwrite = False
                        logger.info(f"Blob '{blob_path}' does not exist. Scheduling upload for: {item.name}")

                    # Schedule the download and upload asynchronously
                    future = executor.submit(
                        download_and_upload_pdf,
                        item,
                        container_client,
                        target_folder,
                        session,
                        overwrite  # Pass the overwrite flag
                    )
                    futures.append(future)
                    files_processed += 1
                    logger.debug(f"Scheduled download and upload for: {item.name}")
                    break  # Stop checking other patterns once matched
        else:
            if is_folder:
                logger.info(f"Empty folder or no childCount: {item.name}, skipping...")
            else:
                logger.info(f"Item {item.name} is neither a file nor a folder with children. Skipping...")

    return files_processed

def main():
    try:
        logger.info("Script started.")
        # Acquire token and initialize GraphClient
        token = acquire_token()
        client = GraphClient(acquire_token)  # Ensure that GraphClient is initialized correctly with the token
        logger.info("Acquired access token and initialized GraphClient.")

        # Connect to Azure Blob Storage
        container_client = connect_to_azure_blob()

        # Access SharePoint site and drive
        logger.info(f"Accessing SharePoint site: {SITE_URL}")
        site = client.sites.get_by_url(SITE_URL).get().execute_query()
        drive = site.drive.get().execute_query()
        logger.info("Accessed SharePoint site and drive.")

        # Specify the folder path in SharePoint
        logger.info(f"Accessing SharePoint folder: {FOLDER_PATH}")
        folder_item = drive.root.get_by_path(FOLDER_PATH).execute_query()

        # Define maximum number of files to download and upload
        max_files_to_download = 10
        logger.info(f"Maximum files to download and upload set to: {max_files_to_download}")

        # Create a session with retry logic
        session = create_session_with_retries()

        # Initialize counters for pre-skipped files
        pre_skipped = [0]  # Using list for mutability
        pre_skipped_lock = Lock()

        # List to collect all Future objects
        futures = []

        # Use ThreadPoolExecutor for concurrent downloads and uploads
        with ThreadPoolExecutor(max_workers=5) as executor:
            total_processed = traverse_folders(
                folder_item,
                filename_patterns,
                max_files_to_download,
                session,
                container_client,
                executor,
                futures,
                pre_skipped,
                pre_skipped_lock
            )
            logger.info(f"Total files scheduled or skipped: {total_processed}")

            # Shutdown the executor and wait for all tasks to complete
            executor.shutdown(wait=True)
            logger.info("All downloads and uploads completed.")

            # Collect results from all futures
            results = []
            for future in concurrent.futures.as_completed(futures):
                try:
                    status = future.result()
                    results.append(status)
                except Exception as e:
                    logger.error(f"Exception in future: {e}")
                    results.append(UploadStatus.FAILED)

            # Aggregate the results using Counter
            counts = Counter(results)

            # Calculate total skipped files (pre-skipped + upload skipped)
            total_skipped = pre_skipped[0] + counts.get(UploadStatus.SKIPPED, 0)
            total_uploaded = counts.get(UploadStatus.UPLOADED, 0)
            total_failed = counts.get(UploadStatus.FAILED, 0)

            # Log the final counts
            logger.info(f"Files uploaded: {total_uploaded}")
            logger.info(f"Files skipped: {total_skipped}")
            logger.info(f"Files failed: {total_failed}")

            logger.info(f"Process completed. Total files processed (uploaded/skipped/failed): {total_uploaded}/{total_skipped}/{total_failed}")

    except Exception as e:
        logger.exception("An unexpected error occurred during the process.")
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()

