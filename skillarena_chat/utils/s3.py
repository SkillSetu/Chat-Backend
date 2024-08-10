import base64
import logging

import boto3
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from botocore.exceptions import ClientError
from fastapi import HTTPException, UploadFile

from skillarena_chat.config import config


logger = logging.getLogger(__name__)

s3_client = boto3.client(
    "s3",
    aws_access_key_id=config.AWS_ACCESS_KEY_ID,
    aws_secret_access_key=config.AWS_SECRET_ACCESS_KEY,
    region_name=config.AWS_REGION,
)

encryption_key = config.ENCRYPTION_KEY.encode("utf-8")


def encrypt_filename(filename):
    cipher = AES.new(encryption_key, AES.MODE_ECB)
    padded_filename = pad(filename.encode("utf-8"), AES.block_size)
    encrypted = cipher.encrypt(padded_filename)
    return base64.b64encode(encrypted).decode("utf-8")


def decrypt_filename(encrypted_filename):
    cipher = AES.new(encryption_key, AES.MODE_ECB)
    encrypted = base64.b64decode(encrypted_filename.encode("utf-8"))
    decrypted = cipher.decrypt(encrypted)
    return unpad(decrypted, AES.block_size).decode("utf-8")


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

        file_name = f"{chatid}/{file.filename}"
        content_type = file.content_type

        s3_client.upload_fileobj(
            file.file,
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
