"""Custom exception hierarchy for udemy-dl.

All application-specific exceptions inherit from :class:`UdemyDLError` so
callers can catch the entire family with a single ``except`` clause when
needed.
"""

from __future__ import annotations 


class UdemyDLError (Exception ):
    """Base exception for all udemy-dl errors."""


class ConfigurationError (UdemyDLError ):
    """Raised when configuration is invalid or missing."""


class AuthenticationError (UdemyDLError ):
    """Raised when API authentication fails (401/403)."""


class APIError (UdemyDLError ):
    """Raised when an API request fails after exhausting retries.

    Attributes:
        status_code: HTTP status code of the last failed response, if available.
    """

    def __init__ (self ,message :str ,status_code :int |None =None )->None :
        super ().__init__ (message )
        self .status_code =status_code 


class CurriculumFetchError (APIError ):
    """Raised when course curriculum cannot be fully retrieved."""


class DownloadError (UdemyDLError ):
    """Raised when a video or material download fails."""


class FFmpegError (DownloadError ):
    """Raised when ffmpeg exits with a non-zero return code.

    Attributes:
        returncode: The exit code from the ffmpeg process.
    """

    def __init__ (self ,message :str ,returncode :int )->None :
        super ().__init__ (message )
        self .returncode =returncode 


class DependencyError (UdemyDLError ):
    """Raised when a required external tool (e.g. ffmpeg) is missing."""
