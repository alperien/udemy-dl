from __future__ import annotations


class UdemyDLError(Exception):
    pass


class ConfigurationError(UdemyDLError):
    pass


class AuthenticationError(UdemyDLError):
    pass


class APIError(UdemyDLError):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class CurriculumFetchError(APIError):
    pass


class DownloadError(UdemyDLError):
    pass


class FFmpegError(DownloadError):
    def __init__(self, message: str, returncode: int) -> None:
        super().__init__(message)
        self.returncode = returncode


class DependencyError(UdemyDLError):
    pass
