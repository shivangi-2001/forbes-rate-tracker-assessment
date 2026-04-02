from django.conf import settings
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
 
 
class _ServiceUser:
    """Minimal user-like object DRF needs for IsAuthenticated to work."""
    is_authenticated = True
    is_active = True
 
 
class BearerTokenAuthentication(BaseAuthentication):
    """Simple static bearer token auth for the ingest endpoint."""
 
    def authenticate(self, request):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return None
 
        token = auth_header.split(" ", 1)[1].strip()
        if token != settings.INGEST_API_KEY:
            raise AuthenticationFailed("Invalid or expired token.")
 
        return (_ServiceUser(), token)