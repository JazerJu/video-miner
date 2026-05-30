from rest_framework.authtoken.models import Token


class TokenAuthenticationMiddleware:
    """
    Middleware to authenticate requests using API Token.
    
    Token is passed via Authorization header:
        Authorization: Bearer <token>
    
    If valid token is found, sets request.user to the token's user
    and skips CSRF validation.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        
        if auth_header.startswith('Bearer '):
            token_key = auth_header[7:].strip()
            
            if token_key:
                try:
                    token = Token.objects.select_related('user').get(key=token_key)
                    request.user = token.user
                    request._dont_enforce_csrf_checks = True
                except Token.DoesNotExist:
                    pass

        response = self.get_response(request)
        return response
