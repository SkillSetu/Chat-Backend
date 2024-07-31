import os
from fastapi import HTTPException, UploadFile
from botocore.exceptions import ClientError
import boto3
import io
import gzip
from PIL import Image
import logging
from dotenv import load_dotenv

load_dotenv(override=True)

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

logger = logging.getLogger(__name__)

s3_client = boto3.client(
    "s3",
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name=os.getenv("AWS_REGION"),
)


def compress_file(file: UploadFile) -> io.BytesIO:
    try:
        compressed_file = io.BytesIO()
        with gzip.GzipFile(fileobj=compressed_file, mode="w") as f:
            if file.content_type.startswith("image"):
                image = Image.open(file.file)
                image.save(f, format="PNG")
            else:
                f.write(file.file.read())
        compressed_file.seek(0)
        return compressed_file
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to compress file")


def process_and_upload_file(file: UploadFile, chatid: str) -> dict:
    try:
        # Validate file size
        file.file.seek(0, 2)
        file_size = file.file.tell()
        file.file.seek(0)

        if file_size > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"File {file.filename} exceeds the maximum size limit of {MAX_FILE_SIZE / (1024 * 1024)} MB",
            )

        # Compress the file
        compressed_file = compress_file(file)

        # Generate file name and determine content type
        file_name = f"{chatid}/{file.filename}"
        content_type = (
            "application/gzip"
            if not file.content_type.startswith("image")
            else file.content_type
        )

        # Upload to S3
        s3_client.upload_fileobj(
            compressed_file,
            os.getenv("S3_BUCKET_NAME"),
            file_name,
            ExtraArgs={"ContentType": content_type},
        )

        # Generate the URL for the uploaded file
        url = f"https://{os.getenv('S3_BUCKET_NAME')}.s3.amazonaws.com/{file_name}"

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
