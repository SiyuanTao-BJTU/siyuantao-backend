from fastapi import APIRouter, UploadFile, File, HTTPException, status
from typing import List
import os

router = APIRouter()

# Configuration for upload directory (create if it doesn't exist)
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Import the file upload utility
from ..utils.file_upload import save_upload_file, UPLOAD_DIR # Import UPLOAD_DIR to construct the URL

@router.post("/upload/image")
async def upload_image(file: UploadFile = File(...)):
    """
    Uploads an image file.
    
    Args:
        file: The image file to upload.
    
    Returns:
        A dictionary containing the URL or path of the uploaded image.
    
    Raises:
        HTTPException: If the file type is not allowed or upload fails.
    """
    # Basic file type check (you might want a more robust check)
    allowed_types = ["image/jpeg", "image/png", "image/gif", "image/webp"]
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file type. Only JPEG, PNG, GIF, and WEBP are allowed."
        )
    
    try:
        # Use the utility function to save the file
        file_path = await save_upload_file(file)
        
        # Construct the URL based on the UPLOAD_DIR and filename
        file_name = os.path.basename(file_path)
        image_url = f"/{UPLOAD_DIR}/{file_name}"
        
        return {"filename": file_name, "url": image_url}
        
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to upload image: {e}")

# Need to import uuid 