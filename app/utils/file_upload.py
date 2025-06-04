from fastapi import UploadFile
import os
import uuid

# Configuration for upload directory (create if it doesn't exist)
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

async def save_upload_file(upload_file: UploadFile) -> str:
    """
    Saves an uploaded file to the local file system and returns its path.
    
    Args:
        upload_file: The UploadFile object received from the request.
        
    Returns:
        The path where the file was saved.
        
    Raises:
        Exception: If file saving fails.
    """
    try:
        file_extension = os.path.splitext(upload_file.filename)[1]
        file_name = f"{uuid.uuid4()}{file_extension}"
        file_path = os.path.join(UPLOAD_DIR, file_name)

        # Ensure directory exists
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        with open(file_path, "wb") as f:
            f.write(await upload_file.read())
            
        return file_path
        
    except Exception as e:
        # You might want more specific error handling or logging here
        raise e 