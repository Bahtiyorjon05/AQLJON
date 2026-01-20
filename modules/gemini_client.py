import logging

from modules.config import Config

logger = logging.getLogger(__name__)

_USE_NEW = False
_genai_new = None
_genai_legacy = None
_client = None


def _load_library():
    global _USE_NEW, _genai_new, _genai_legacy
    if _genai_new or _genai_legacy:
        return
    try:
        from google import genai as genai_new
    except ImportError:
        genai_new = None
    if genai_new is not None:
        _genai_new = genai_new
        _USE_NEW = True
        return
    try:
        import google.generativeai as genai_legacy
    except ImportError as exc:
        raise ImportError("Missing Gemini SDK. Install google-genai.") from exc
    _genai_legacy = genai_legacy
    _USE_NEW = False


def _get_client():
    global _client
    _load_library()
    if _client is not None:
        return _client
    if _USE_NEW:
        _client = _genai_new.Client(api_key=Config.GEMINI_KEY)
    else:
        _genai_legacy.configure(api_key=Config.GEMINI_KEY)
        _client = _genai_legacy
    return _client


def _is_model_unavailable_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return (
        "not found for api version" in message
        or "not supported for generatecontent" in message
        or ("model" in message and "not found" in message)
    )


class GeminiModelAdapter:
    def __init__(self, client, model_name: str, fallback_name: str | None = None):
        self._client = client
        self._model_name = model_name
        self._fallback_name = fallback_name
        self._current_name = model_name

    def _maybe_fallback(self, exc: Exception) -> bool:
        if not self._fallback_name or self._current_name == self._fallback_name:
            return False
        if not _is_model_unavailable_error(exc):
            return False
        logger.warning(
            "Gemini model %s unavailable; falling back to %s",
            self._current_name,
            self._fallback_name,
        )
        self._current_name = self._fallback_name
        return True

    def generate_content(self, contents):
        try:
            return self._client.models.generate_content(
                model=self._current_name,
                contents=contents,
            )
        except Exception as exc:
            if self._maybe_fallback(exc):
                return self._client.models.generate_content(
                    model=self._current_name,
                    contents=contents,
                )
            raise


class LegacyModelAdapter:
    def __init__(self, genai_module, model_name: str, fallback_name: str | None = None):
        self._genai = genai_module
        self._model_name = model_name
        self._fallback_name = fallback_name
        self._current_name = model_name
        self._model = genai_module.GenerativeModel(model_name)

    def _maybe_fallback(self, exc: Exception) -> bool:
        if not self._fallback_name or self._current_name == self._fallback_name:
            return False
        if not _is_model_unavailable_error(exc):
            return False
        logger.warning(
            "Gemini model %s unavailable; falling back to %s",
            self._current_name,
            self._fallback_name,
        )
        self._current_name = self._fallback_name
        self._model = self._genai.GenerativeModel(self._current_name)
        return True

    def generate_content(self, contents):
        try:
            return self._model.generate_content(contents)
        except Exception as exc:
            if self._maybe_fallback(exc):
                return self._model.generate_content(contents)
            raise


def build_gemini_model():
    client = _get_client()
    if _USE_NEW:
        return GeminiModelAdapter(
            client,
            Config.GEMINI_MODEL,
            Config.GEMINI_MODEL_FALLBACK,
        )
    return LegacyModelAdapter(
        client,
        Config.GEMINI_MODEL,
        Config.GEMINI_MODEL_FALLBACK,
    )


def upload_file(file_path: str):
    client = _get_client()
    if _USE_NEW:
        return client.files.upload(file=file_path)
    return client.upload_file(file_path)


def get_file(file_name: str):
    client = _get_client()
    if _USE_NEW:
        return client.files.get(name=file_name)
    return client.get_file(file_name)


def get_file_state(file_obj):
    """Safely get file state string from various SDK versions"""
    state = getattr(file_obj, "state", None)
    if state is None:
        return None
    
    # Handle dictionary response
    if isinstance(state, dict):
        val = state.get("name") or state.get("state")
        return str(val).upper() if val else None
        
    # Handle string response
    if isinstance(state, str):
        return state.upper()
        
    # Handle Enum or Object (new SDK)
    # Convert to string (e.g. "FileState.ACTIVE" or "ACTIVE")
    state_str = str(state)
    
    # If it's an enum name like 'ACTIVE', accessing .name might work
    if hasattr(state, "name"):
        return state.name.upper()
        
    # Clean up "FileState." prefix if present
    if "." in state_str:
        return state_str.split(".")[-1].upper()
        
    return state_str.upper()
