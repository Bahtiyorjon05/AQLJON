"""
Retry utilities with exponential backoff for API calls
Based on 2025 best practices using tenacity library
"""
import asyncio
import logging
import aiohttp
from tenacity import (
    retry,
    wait_exponential,
    stop_after_attempt,
    retry_if_exception_type,
    before_sleep_log
)
from google.api_core import exceptions as google_exceptions

logger = logging.getLogger(__name__)

# Define retry decorator for Gemini API calls
retry_on_api_error = retry(
    wait=wait_exponential(multiplier=1, min=1, max=10),
    stop=stop_after_attempt(3),
    retry=retry_if_exception_type((
        google_exceptions.ResourceExhausted,
        google_exceptions.ServiceUnavailable,
        google_exceptions.InternalServerError,
        ConnectionError,
        TimeoutError
    )),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True
)

@retry_on_api_error
async def generate_content_with_retry(model, messages, timeout=240):
    """
    Generate content with automatic retry on failure

    Args:
        model: Gemini model instance
        messages: Messages to send to the model
        timeout: Timeout in seconds

    Returns:
        Generated response
    """
    try:
        response = await asyncio.wait_for(
            asyncio.to_thread(lambda: model.generate_content(messages)),
            timeout=timeout
        )
        return response
    except asyncio.TimeoutError:
        logger.error(f"Gemini API timeout after {timeout} seconds")
        raise
    except Exception as e:
        logger.error(f"Gemini API error: {e}")
        raise

@retry_on_api_error
def generate_content_with_retry_sync(model, messages):
    """
    Synchronous version: Generate content with automatic retry on failure

    Args:
        model: Gemini model instance
        messages: Messages to send to the model

    Returns:
        Generated response
    """
    try:
        response = model.generate_content(messages)
        return response
    except Exception as e:
        logger.error(f"Gemini API error: {e}")
        raise

@retry_on_api_error
async def upload_file_with_retry(file_path, timeout=90):
    """
    Upload file to Gemini with automatic retry

    Args:
        file_path: Path to file to upload
        timeout: Timeout in seconds

    Returns:
        Uploaded file object
    """
    import google.generativeai as genai

    try:
        uploaded = await asyncio.to_thread(lambda: genai.upload_file(file_path))
        return uploaded
    except Exception as e:
        logger.error(f"File upload error: {e}")
        raise

async def wait_for_file_active(uploaded_file, timeout=30):
    """
    Wait for uploaded file to become ACTIVE with retry logic

    Args:
        uploaded_file: Uploaded file object
        timeout: Timeout in seconds

    Returns:
        Active file object
    """
    import google.generativeai as genai
    import time

    interval = 2
    elapsed = 0

    while uploaded_file.state.name != "ACTIVE" and elapsed < timeout:
        if uploaded_file.state.name == "FAILED":
            raise Exception(f"File processing failed: {uploaded_file.state}")

        await asyncio.sleep(interval)
        elapsed += interval

        # Refresh file state
        uploaded_file = await asyncio.to_thread(
            lambda: genai.get_file(uploaded_file.name)
        )

    if uploaded_file.state.name != "ACTIVE":
        raise Exception(f"File processing timeout. Final state: {uploaded_file.state.name}")

    return uploaded_file

# HTTP retry decorator for external APIs (Nominatim, Aladhan, Overpass)
http_retry_decorator = retry(
    wait=wait_exponential(multiplier=1, min=1, max=10),
    stop=stop_after_attempt(3),
    retry=retry_if_exception_type((
        aiohttp.ClientError,
        asyncio.TimeoutError,
        ConnectionError
    )),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True
)

@http_retry_decorator
async def http_get_with_retry(url: str, params: dict = None, headers: dict = None, timeout: int = 30):
    """
    HTTP GET request with automatic retry on failure

    Args:
        url: URL to fetch
        params: Query parameters
        headers: HTTP headers
        timeout: Timeout in seconds

    Returns:
        Response data as JSON dict or None on error
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                params=params,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=timeout)
            ) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.warning(f"HTTP GET failed with status {response.status}: {url}")
                    return None
    except asyncio.TimeoutError:
        logger.error(f"HTTP GET timeout after {timeout} seconds: {url}")
        raise
    except Exception as e:
        logger.error(f"HTTP GET error: {e}")
        raise

@http_retry_decorator
async def http_post_with_retry(url: str, data: dict = None, params: dict = None, headers: dict = None, timeout: int = 30):
    """
    HTTP POST request with automatic retry on failure

    Args:
        url: URL to post to
        data: POST data
        params: Query parameters
        headers: HTTP headers
        timeout: Timeout in seconds

    Returns:
        Response data as JSON dict or None on error
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                data=data,
                params=params,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=timeout)
            ) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.warning(f"HTTP POST failed with status {response.status}: {url}")
                    return None
    except asyncio.TimeoutError:
        logger.error(f"HTTP POST timeout after {timeout} seconds: {url}")
        raise
    except Exception as e:
        logger.error(f"HTTP POST error: {e}")
        raise
