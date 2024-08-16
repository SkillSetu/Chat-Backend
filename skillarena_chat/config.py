import os

from dotenv import load_dotenv


load_dotenv(override=True)


class ConfigError(Exception):
    """Custom exception for configuration errors."""

    pass


class Config:
    required_vars = [
        "MONGO_URI",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_REGION",
        "S3_BUCKET_NAME",
        "ACCESS_TOKEN_SECRET",
    ]

    def __init__(self):
        self.MONGO_URI = os.getenv("MONGO_URI")
        self.AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
        self.AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
        self.AWS_REGION = os.getenv("AWS_REGION")
        self.S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")
        self.ACCESS_TOKEN_SECRET = os.getenv("ACCESS_TOKEN_SECRET")
        self.ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")
        self.ALGORITHM = "HS256"
        self.ACCESS_TOKEN_EXPIRE_MINUTES = 30
        self.MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

        self.check_required_vars()

    def check_required_vars(self):
        """Check if all required variables are set."""
        missing_vars = [var for var in self.required_vars if getattr(self, var) is None]
        if missing_vars:
            raise ConfigError(
                f"Missing required environment variables: {', '.join(missing_vars)}"
            )


config = Config()
