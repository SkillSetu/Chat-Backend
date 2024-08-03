import gzip
import io
import logging
import os

import boto3
from PIL import Image
from botocore.exceptions import ClientError
from dotenv import load_dotenv
from fastapi import HTTPException, UploadFile


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
    """Compress the given file.

    Args:
        file (UploadFile): The UploadFile object to compress.

    Raises:
        HTTPException: The file exceeds the maximum size limit.

    Returns:
        io.BytesIO: A BytesIO object containing the compressed file data.
    """

    try:
        if file.content_type.startswith("image"):
            image = Image.open(file.file)

            optimized_file = io.BytesIO()
            image.save(optimized_file, format=image.format, optimize=True)
            optimized_file.seek(0)

            return optimized_file

        else:
            compressed_file = io.BytesIO()

            with gzip.GzipFile(fileobj=compressed_file, mode="w") as f:
                file.file.seek(0)
                f.write(file.file.read())

            compressed_file.seek(0)

            return compressed_file

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

        if file_size > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"File {file.filename} exceeds the maximum size limit of {MAX_FILE_SIZE / (1024 * 1024)} MB",
            )

        processed_file = compress_file(file)

        file_name = f"{chatid}/{file.filename}"
        content_type = file.content_type

        s3_client.upload_fileobj(
            processed_file,
            os.getenv("S3_BUCKET_NAME"),
            file_name,
            ExtraArgs={"ContentType": content_type},
        )

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
