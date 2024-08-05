import io
import logging

import boto3
from PIL import Image
from PyPDF2 import PdfReader, PdfWriter
from botocore.exceptions import ClientError
from fastapi import HTTPException, UploadFile

from ..config import config


logger = logging.getLogger(__name__)

s3_client = boto3.client(
    "s3",
    aws_access_key_id=config.AWS_ACCESS_KEY_ID,
    aws_secret_access_key=config.AWS_SECRET_ACCESS_KEY,
    region_name=config.AWS_REGION,
)


def compress_image(file: UploadFile) -> io.BytesIO:
    """Compress an image file."""
    image = Image.open(file.file)

    # Convert to RGB if image is in RGBA mode
    if image.mode == "RGBA":
        image = image.convert("RGB")

    optimized_file = io.BytesIO()

    # Save with optimal settings
    image.save(
        optimized_file,
        format=image.format,
        optimize=True,
        quality=85,  # Adjust this value to balance quality and size
        progressive=True,
    )

    optimized_file.seek(0)
    return optimized_file


def compress_pdf(file: UploadFile) -> io.BytesIO:
    """Compress a PDF file."""
    reader = PdfReader(file.file)
    writer = PdfWriter()

    for page in reader.pages:
        writer.add_page(page)

    # Use compression, but not too aggressively
    writer.add_metadata(reader.metadata)

    output = io.BytesIO()
    writer.write(output)
    output.seek(0)
    return output


def compress_file(file: UploadFile) -> io.BytesIO:
    """Compress the given file without losing quality.

    Args:
        file (UploadFile): The UploadFile object to compress.

    Raises:
        HTTPException: If file processing fails.

    Returns:
        io.BytesIO: A BytesIO object containing the compressed file data.
    """

    try:
        if file.content_type.startswith("image"):
            return compress_image(file)
        elif file.content_type == "application/pdf":
            return compress_pdf(file)
        else:
            file.file.seek(0)
            return io.BytesIO(file.file.read())

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process file: {str(e)}")


def process_and_upload_file(file: UploadFile, chatid: str) -> dict:
    """Process and upload the given file to S3.

    Args:
        file (UploadFile): The UploadFile object to process and upload.
        chatid (str): The chat ID.

    Raises:
        HTTPException: error uploading file to S3
        HTTPException: file exceeds the maximum size limit
        HTTPException: unexpected error processing file

    Returns:
        dict: A dictionary containing the original file name, stored file name, and URL.
    """

    try:
        file.file.seek(0, 2)
        file_size = file.file.tell()
        file.file.seek(0)

        if file_size > config.MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"File {file.filename} exceeds the maximum size limit of {config.MAX_FILE_SIZE / (1024 * 1024)} MB",
            )

        processed_file = compress_file(file)

        file_name = f"{chatid}/{file.filename}"
        content_type = file.content_type

        s3_client.upload_fileobj(
            processed_file,
            config.S3_BUCKET_NAME,
            file_name,
            ExtraArgs={"ContentType": content_type},
        )

        url = f"https://{config.S3_BUCKET_NAME}.s3.amazonaws.com/{file_name}"

        return {
            "original_file_name": file.filename,
            "stored_file_name": file_name,
            "url": url,
        }

    except ClientError as e:
        logger.error(f"Error uploading file to S3: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to upload file")

    except Exception as e:
        logger.error(f"Unexpected error processing file: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to process file")
