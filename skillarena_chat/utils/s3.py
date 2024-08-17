import base64
import logging
from typing import List

import boto3
from Crypto.Cipher import AES
from Crypto.Hash import SHA256
from Crypto.Util.Padding import pad, unpad
from botocore.exceptions import ClientError
from fastapi import HTTPException, UploadFile
from base64 import b64decode

from skillarena_chat.config import config


logger = logging.getLogger(__name__)

s3_client = boto3.client(
    "s3",
    aws_access_key_id=config.AWS_ACCESS_KEY_ID,
    aws_secret_access_key=config.AWS_SECRET_ACCESS_KEY,
    region_name=config.AWS_REGION,
)


def get_encryption_key():
    return SHA256.new(config.ENCRYPTION_KEY.encode("utf-8")).digest()


def encrypt_filename(filename):
    cipher = AES.new(get_encryption_key(), AES.MODE_ECB)
    padded_filename = pad(filename.encode("utf-8"), AES.block_size)
    encrypted = cipher.encrypt(padded_filename)
    return base64.b64encode(encrypted).decode("utf-8")


def decrypt_filename(encrypted_filename: str) -> str:
    secret_key = config.ENCRYPTION_KEY
    iv = "1020304050607080"
    ciphertext = b64decode(encrypted_filename)
    derived_key = b64decode(secret_key)
    cipher = AES.new(derived_key, AES.MODE_CBC, iv.encode("utf-8"))
    decrypted_data = cipher.decrypt(ciphertext)
    return unpad(decrypted_data, 16).decode("utf-8")


def get_public_url(encrypted_filename):
    decrypted_filename = decrypt_filename(encrypted_filename)
    return f"https://{config.S3_BUCKET_NAME}.s3.amazonaws.com/{decrypted_filename}"


def generate_presigned_urls(file_names: List[str]) -> List[str]:
    data = []
    for file_name in file_names:
        decrypted_filename = decrypt_filename(file_name)
        presigned_url = s3_client.generate_presigned_url(
            ClientMethod="get_object",
            Params={
                "Bucket": config.S3_BUCKET_NAME,
                "Key": decrypted_filename,
            },
        )
        data.append(presigned_url)

    return data


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
        encrypted_url = encrypt_filename(file_name)

        s3_client.upload_fileobj(
            file.file,
            config.S3_BUCKET_NAME,
            file_name,
            ExtraArgs={"ContentType": content_type},
        )

        return {
            "original_file_name": file.filename,
            "stored_file_name": file_name,
            "url": encrypted_url,
        }

    except ClientError as e:
        logger.error(f"Error uploading file to S3: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to upload file")

    except Exception as e:
        logger.error(f"Unexpected error processing file: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to process file")
